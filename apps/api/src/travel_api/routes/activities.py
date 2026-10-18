from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from ..db import Database
from ..errors import ApiError
from ..ids import new_id
from ..models import (
    SCHEMA_VERSION,
    Activity,
    ActivityList,
    ActivityStatus,
    AddActivityRequest,
    MoveActivityRequest,
    Trip,
    UpdateActivityRequest,
    utc_now,
)
from ..repository import activities as activity_repo
from ..scheduling import (
    default_status,
    move_schedule,
    resolve_schedule,
    sort_key_flat,
    status_after_reschedule,
)
from .deps import (
    ETAG_HEADER,
    ActivityId,
    IfMatch,
    TripId,
    activity_not_found,
    activity_response,
    activity_write_failed,
    concurrent_change,
    etag,
    get_db,
    load_trip,
    parse_if_match,
    problems,
    stale,
    traveler_not_found,
)

router = APIRouter(prefix="/trips/{tripId}/activities", tags=["Activities"])

Db = Annotated[Database, Depends(get_db)]


def _check_travelers(ids: list[str], trip: Trip) -> list[str]:
    """Deduplicate traveler IDs and make sure each one is on the trip."""
    known = {t.id for t in trip.travelers}
    errors = [
        {
            "path": f"body.travelerIds.{i}",
            "message": (
                f"traveler {tid} is not on trip {trip.id} (travelers on this trip: "
                f"{', '.join(sorted(known)) or 'none'}); add them with add_traveler first"
            ),
        }
        for i, tid in enumerate(ids)
        if tid not in known
    ]
    if errors:
        raise ApiError(422, "; ".join(e["message"] for e in errors), errors=errors)
    return list(dict.fromkeys(ids))


@router.get(
    "",
    operation_id="list_activities",
    summary="List a trip's activities",
    description=(
        "All activities of the trip, optionally filtered. Sorted by date and start time, "
        "with unscheduled activities last."
    ),
    response_model=ActivityList,
    responses=problems(401, 404, 422),
)
async def list_activities(
    trip_id: TripId,
    db: Db,
    date: Annotated[
        str | None,
        Query(
            pattern=r"^\d{4}-\d{2}-\d{2}$",
            description="Only activities on this day (YYYY-MM-DD, trip timezone).",
        ),
    ] = None,
    unscheduled: Annotated[
        bool | None,
        Query(description="`true`: only activities with no date. `false`: only scheduled ones."),
    ] = None,
    traveler_id: Annotated[
        str | None, Query(alias="travelerId", description="Only activities with this traveler.")
    ] = None,
    status_: Annotated[
        ActivityStatus | None,
        Query(alias="status", description="Only activities with this status."),
    ] = None,
) -> ActivityList:
    trip = await load_trip(db, trip_id)
    query: dict[str, Any] = {}
    if date is not None and unscheduled:
        raise ApiError(
            422,
            "date and unscheduled=true cannot be combined: an activity on a date is scheduled.",
            errors=[{"path": "query.unscheduled", "message": "conflicts with query.date"}],
        )
    if date is not None:
        query["schedule.date"] = date
    elif unscheduled is not None:
        query["schedule.date"] = None if unscheduled else {"$ne": None}
    if traveler_id is not None:
        if not any(t.id == traveler_id for t in trip.travelers):
            raise traveler_not_found(trip, traveler_id)
        query["travelerIds"] = traveler_id
    if status_ is not None:
        query["status"] = status_
    activities = await activity_repo.find(db, trip_id, query)
    return ActivityList(activities=sorted(activities, key=sort_key_flat))


@router.post(
    "",
    operation_id="add_activity",
    summary="Add an activity",
    description=(
        "Creates an activity. Without `schedule` it is an unscheduled idea; with only "
        "`schedule.date` it is all-day; with `schedule.startAt` it is timed and its date is "
        "derived from startAt in the trip's timezone. Dates must fall within the trip."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=Activity,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 404, 422)},
)
async def add_activity(
    trip_id: TripId, body: AddActivityRequest, response: Response, db: Db
) -> Activity:
    trip = await load_trip(db, trip_id)
    schedule = resolve_schedule(body.schedule, trip, "body.schedule")
    now = utc_now()
    activity = Activity(
        schema_version=SCHEMA_VERSION,
        id=new_id("act"),
        trip_id=trip_id,
        title=body.title,
        status=body.status or default_status(schedule),
        schedule=schedule,
        location=body.location,
        notes=body.notes,
        traveler_ids=_check_travelers(body.traveler_ids, trip),
        created_at=now,
        updated_at=now,
    )
    await activity_repo.insert(db, activity)
    response.headers["Location"] = f"/v1/trips/{trip_id}/activities/{activity.id}"
    return activity_response(activity, response)


@router.get(
    "/{activityId}",
    operation_id="get_activity",
    summary="Get an activity",
    response_model=Activity,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404)},
)
async def get_activity(
    trip_id: TripId, activity_id: ActivityId, response: Response, db: Db
) -> Activity:
    activity = await activity_repo.get(db, trip_id, activity_id)
    if activity is None:
        await load_trip(db, trip_id)
        raise activity_not_found(trip_id, activity_id)
    return activity_response(activity, response)


@router.patch(
    "/{activityId}",
    operation_id="update_activity",
    summary="Update an activity",
    description=(
        "Partial update: only the fields you send change. `schedule` and `location` are "
        "replaced as a whole. If the schedule changes and `status` is not sent, an `idea` that "
        "gets a date becomes `planned` and a `planned` activity that loses its date becomes "
        "`idea`."
    ),
    response_model=Activity,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def update_activity(
    trip_id: TripId,
    activity_id: ActivityId,
    body: UpdateActivityRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> Activity:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    sent = body.model_fields_set
    fields = body.model_dump(exclude_unset=True, exclude={"schedule", "traveler_ids"})
    status_expr = None
    if "schedule" in sent:
        schedule = resolve_schedule(body.schedule, trip, "body.schedule")
        fields["schedule"] = schedule.model_dump()
        if "status" not in sent:
            status_expr = _status_after_reschedule_expr(schedule.date)
    if "traveler_ids" in sent and body.traveler_ids is not None:
        fields["travelerIds"] = _check_travelers(body.traveler_ids, trip)
    activity = await activity_repo.update(
        db, trip_id, activity_id, fields, utc_now(), if_match=versions, status_expr=status_expr
    )
    if activity is None:
        raise await activity_write_failed(db, trip_id, activity_id, versions)
    return activity_response(activity, response)


def _status_after_reschedule_expr(new_date: str | None) -> dict[str, Any]:
    """The database-side version of ``status_after_reschedule``."""
    before, after = ("idea", "planned") if new_date is not None else ("planned", "idea")
    return {"$cond": [{"$eq": ["$status", before]}, after, "$status"]}


@router.post(
    "/{activityId}/move",
    operation_id="move_activity",
    summary="Move an activity to another day",
    description=(
        "Moves an activity to `date` (or unschedules it with `date: null`). Without `startAt`, "
        "each time of day is kept, in the trip's timezone, on the new day. With `startAt`, the "
        "new times are used and an omitted `endAt` keeps the duration. An `idea` moved onto a "
        "day becomes `planned`; a `planned` activity that is unscheduled becomes `idea`."
    ),
    response_model=Activity,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 409, 412, 422)},
)
async def move_activity(
    trip_id: TripId,
    activity_id: ActivityId,
    body: MoveActivityRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> Activity:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    # The new times depend on the current ones, so write only if the activity is unchanged
    # since it was read (compare-and-set on updatedAt), retrying a few times under contention.
    for _ in range(3):
        current = await activity_repo.get(db, trip_id, activity_id)
        if current is None:
            raise activity_not_found(trip_id, activity_id)
        if versions is not None and current.updated_at not in versions:
            raise stale(etag(current.updated_at), current)
        schedule = move_schedule(current.schedule, body, trip)
        fields = {
            "schedule": schedule.model_dump(),
            "status": status_after_reschedule(current.status, schedule.date),
        }
        activity = await activity_repo.update(
            db, trip_id, activity_id, fields, utc_now(), if_match=[current.updated_at]
        )
        if activity is not None:
            return activity_response(activity, response)
    raise concurrent_change(f"Activity {activity_id}")


@router.delete(
    "/{activityId}",
    operation_id="delete_activity",
    summary="Delete an activity",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 404, 412),
)
async def delete_activity(
    trip_id: TripId, activity_id: ActivityId, db: Db, if_match: IfMatch = None
) -> Response:
    versions = parse_if_match(if_match)
    if not await activity_repo.delete(db, trip_id, activity_id, if_match=versions):
        await load_trip(db, trip_id)
        raise await activity_write_failed(db, trip_id, activity_id, versions)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
