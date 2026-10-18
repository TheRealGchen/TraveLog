from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from ..db import Database
from ..errors import ApiError
from ..models import (
    Activity,
    ActivityList,
    ActivityStatus,
    MoveActivityRequest,
    Trip,
    UpdateActivityRequest,
    utc_now,
)
from ..repository import days as day_repo
from ..scheduling import check_day_in_trip, move_time, resolve_time, sort_key_in_day
from .deps import (
    ETAG_HEADER,
    ActivityId,
    IfMatch,
    TripId,
    activity_not_found,
    activity_response,
    check_travelers,
    concurrent_change,
    etag,
    get_db,
    load_day,
    load_days,
    load_trip,
    parse_if_match,
    problems,
    stale,
    to_activity,
    traveler_not_found,
)

router = APIRouter(prefix="/trips/{tripId}/activities", tags=["Activities"])

Db = Annotated[Database, Depends(get_db)]


async def _write_failed(
    db: Database, trip: Trip, activity_id: str, if_match: list[datetime] | None
) -> ApiError:
    """Explain why a conditional activity write matched nothing."""
    found = await day_repo.find_activity(db, trip.id, activity_id)
    if found is None:
        return activity_not_found(trip.id, activity_id)
    day, current = found
    if if_match is not None and current.updated_at not in if_match:
        return stale(etag(current.updated_at), to_activity(trip.id, day.date, current))
    return concurrent_change(f"Activity {activity_id}")


@router.get(
    "",
    operation_id="list_activities",
    summary="List a trip's activities",
    description=(
        "Activities across all days of the trip, optionally filtered, ordered by day and then "
        "start time. To see a day with its lodging, use `get_day` or `list_days`."
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
    traveler_id: Annotated[
        str | None, Query(alias="travelerId", description="Only activities with this traveler.")
    ] = None,
    status_: Annotated[
        ActivityStatus | None,
        Query(alias="status", description="Only activities with this status."),
    ] = None,
) -> ActivityList:
    trip = await load_trip(db, trip_id)
    if traveler_id is not None and not any(t.id == traveler_id for t in trip.travelers):
        raise traveler_not_found(trip, traveler_id)
    activities = []
    for day in await load_days(db, trip):
        if date is not None and day.date != date:
            continue
        for a in sorted(day.activities, key=sort_key_in_day):
            if status_ is not None and a.status != status_:
                continue
            if traveler_id is not None and traveler_id not in a.traveler_ids:
                continue
            activities.append(to_activity(trip_id, day.date, a))
    return ActivityList(activities=activities)


@router.get(
    "/{activityId}",
    operation_id="get_activity",
    summary="Get an activity",
    description="One activity, including the `date` of the day it is on. Returns an ETag.",
    response_model=Activity,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404)},
)
async def get_activity(
    trip_id: TripId, activity_id: ActivityId, response: Response, db: Db
) -> Activity:
    found = await day_repo.find_activity(db, trip_id, activity_id)
    if found is None:
        await load_trip(db, trip_id)
        raise activity_not_found(trip_id, activity_id)
    day, activity = found
    return activity_response(to_activity(trip_id, day.date, activity), response)


@router.patch(
    "/{activityId}",
    operation_id="update_activity",
    summary="Update an activity",
    description=(
        "Partial update: only the fields you send change. `time` and `location` are replaced "
        "as a whole; null clears them. A new `time.startAt` must fall on the activity's day; "
        "use `move_activity` to change the day."
    ),
    response_model=Activity,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 409, 412, 422)},
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
    found = await day_repo.find_activity(db, trip_id, activity_id)
    if found is None:
        raise activity_not_found(trip_id, activity_id)
    day, _ = found
    sent = body.model_fields_set
    fields = body.model_dump(exclude_unset=True, exclude={"time", "traveler_ids"})
    if "time" in sent:
        time = resolve_time(body.time, day.date, trip, "body.time")
        fields["time"] = time.model_dump() if time else None
    if "traveler_ids" in sent and body.traveler_ids is not None:
        fields["travelerIds"] = check_travelers(body.traveler_ids, trip)
    # Pinned to the day the times were validated against, in case of a concurrent move.
    updated = await day_repo.update_activity(
        db, trip_id, activity_id, fields, utc_now(), date=day.date, if_match=versions
    )
    if updated is None:
        raise await _write_failed(db, trip, activity_id, versions)
    activity = next(a for a in updated.activities if a.id == activity_id)
    return activity_response(to_activity(trip_id, updated.date, activity), response)


@router.post(
    "/{activityId}/move",
    operation_id="move_activity",
    summary="Move an activity to another day",
    description=(
        "Moves an activity to `date`. Without `startAt`, each time of day is kept, in the "
        "trip's timezone, on the new day. With `startAt` (on the new day), the new times are "
        "used and an omitted `endAt` keeps the duration."
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
    check_day_in_trip(trip, body.date, "body.date")
    await load_day(db, trip, body.date)
    # The new times depend on the current ones, so every write below is conditional on the
    # activity being unchanged since it was read; on contention, re-read and retry.
    for _ in range(3):
        found = await day_repo.find_activity(db, trip_id, activity_id)
        if found is None:
            raise activity_not_found(trip_id, activity_id)
        day, current = found
        if versions is not None and current.updated_at not in versions:
            raise stale(etag(current.updated_at), to_activity(trip_id, day.date, current))
        time = move_time(current.time, day.date, body, trip)
        now = utc_now()
        if body.date == day.date:
            updated = await day_repo.update_activity(
                db,
                trip_id,
                activity_id,
                {"time": time.model_dump() if time else None},
                now,
                date=day.date,
                if_match=[current.updated_at],
            )
            if updated is not None:
                moved = next(a for a in updated.activities if a.id == activity_id)
                return activity_response(to_activity(trip_id, body.date, moved), response)
            continue
        # Across days: add to the target first, then remove from the source. A failure in
        # between leaves a duplicate rather than losing the activity.
        moved = current.model_copy(update={"time": time, "updated_at": now})
        if await day_repo.push_activity(db, trip_id, body.date, moved, now) is None:
            raise concurrent_change(f"Activity {activity_id}")
        removed = await day_repo.pull_activity(
            db, trip_id, activity_id, now, date=day.date, if_match=[current.updated_at]
        )
        if removed:
            return activity_response(to_activity(trip_id, body.date, moved), response)
        # The source changed meanwhile: undo the copy and retry with fresh data.
        await day_repo.pull_activity(db, trip_id, activity_id, now, date=body.date)
    raise concurrent_change(f"Activity {activity_id}")


@router.delete(
    "/{activityId}",
    operation_id="delete_activity",
    summary="Delete an activity",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 404, 409, 412),
)
async def delete_activity(
    trip_id: TripId, activity_id: ActivityId, db: Db, if_match: IfMatch = None
) -> Response:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    if not await day_repo.pull_activity(db, trip_id, activity_id, utc_now(), if_match=versions):
        raise await _write_failed(db, trip, activity_id, versions)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
