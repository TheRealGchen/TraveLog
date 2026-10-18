from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..db import Database
from ..ids import new_id
from ..models import (
    Activity,
    ActivityDocument,
    AddActivityRequest,
    Day,
    DayList,
    UpdateDayRequest,
    utc_now,
)
from ..repository import days as day_repo
from ..scheduling import countdown, resolve_time
from .deps import (
    ETAG_HEADER,
    DayDate,
    IfMatch,
    TripId,
    activity_response,
    check_travelers,
    concurrent_change,
    day_response,
    etag,
    get_db,
    load_day,
    load_days,
    load_trip,
    parse_if_match,
    problems,
    stale,
    to_activity,
)

router = APIRouter(prefix="/trips/{tripId}/days", tags=["Days"])

Db = Annotated[Database, Depends(get_db)]


@router.get(
    "",
    operation_id="list_days",
    summary="List the trip's days",
    description=(
        "Every day from startDate to endDate, in order, each with its lodging, start location, "
        "and activities (sorted by start time; untimed activities last). Days are in the "
        "trip's timezone; times are UTC."
    ),
    response_model=DayList,
    responses=problems(401, 404),
)
async def list_days(trip_id: TripId, db: Db) -> DayList:
    trip = await load_trip(db, trip_id)
    days = await load_days(db, trip)
    days_until, trip_status = countdown(trip)
    return DayList(
        trip_id=trip.id,
        timezone=trip.timezone,
        start_date=trip.start_date,
        end_date=trip.end_date,
        days_until_start=days_until,
        status=trip_status,
        days=[day_response(trip, d) for d in days],
    )


@router.get(
    "/{date}",
    operation_id="get_day",
    summary="Get one day",
    description="The day with its lodging, start location, and activities. Returns an ETag.",
    response_model=Day,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 422)},
)
async def get_day(trip_id: TripId, date: DayDate, response: Response, db: Db) -> Day:
    trip = await load_trip(db, trip_id)
    return day_response(trip, await load_day(db, trip, date), response)


@router.patch(
    "/{date}",
    operation_id="update_day",
    summary="Update a day",
    description=(
        "Sets where the travelers stay that night (`lodging`) and where the day starts "
        "(`startLocation`). Only the fields you send change; null clears one. Returns the day."
    ),
    response_model=Day,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def update_day(
    trip_id: TripId,
    date: DayDate,
    body: UpdateDayRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> Day:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    await load_day(db, trip, date)
    day = await day_repo.update(
        db, trip_id, date, body.model_dump(exclude_unset=True), utc_now(), if_match=versions
    )
    if day is None:
        latest = await load_day(db, trip, date)
        if versions is not None and latest.updated_at not in versions:
            raise stale(etag(latest.updated_at), day_response(trip, latest))
        raise concurrent_change(f"Day {date}")
    return day_response(trip, day, response)


@router.post(
    "/{date}/activities",
    operation_id="add_activity",
    summary="Add an activity to a day",
    description=(
        "Creates an activity on this day. With `time`, `startAt` must fall on this day in the "
        "trip's timezone. Returns the new activity (201) and its ETag."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=Activity,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 404, 422)},
)
async def add_activity(
    trip_id: TripId, date: DayDate, body: AddActivityRequest, response: Response, db: Db
) -> Activity:
    trip = await load_trip(db, trip_id)
    await load_day(db, trip, date)
    now = utc_now()
    activity = ActivityDocument(
        id=new_id("act"),
        title=body.title,
        status=body.status or "planned",
        time=resolve_time(body.time, date, trip, "body.time"),
        location=body.location,
        notes=body.notes,
        traveler_ids=check_travelers(body.traveler_ids, trip),
        created_at=now,
        updated_at=now,
    )
    if await day_repo.push_activity(db, trip_id, date, activity, now) is None:
        raise concurrent_change(f"Day {date}")
    response.headers["Location"] = f"/v1/trips/{trip_id}/activities/{activity.id}"
    return activity_response(to_activity(trip_id, date, activity), response)
