from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from ..db import Database
from ..errors import ApiError
from ..ids import new_id
from ..models import (
    SCHEMA_VERSION,
    CreateTripRequest,
    Trip,
    TripList,
    TripResponse,
    TripSort,
    TripStatus,
    TripSummary,
    UpdateTripRequest,
    utc_now,
)
from ..repository import days as day_repo
from ..repository import trips as trip_repo
from ..scheduling import (
    countdown,
    day_has_content,
    days_conflict,
    timezone_conflict,
    timezone_conflicts,
    trip_days,
)
from .deps import (
    ETAG_HEADER,
    IfMatch,
    TripId,
    get_db,
    load_days,
    load_trip,
    parse_if_match,
    problems,
    trip_not_found,
    trip_response,
    trip_write_failed,
)

router = APIRouter(prefix="/trips", tags=["Trips"])

Db = Annotated[Database, Depends(get_db)]


@router.get(
    "",
    operation_id="list_trips",
    summary="List trips",
    description="Summary view of every trip, with countdown, status, and travelers for each.",
    response_model=TripList,
    responses=problems(401, 422),
)
async def list_trips(
    db: Db,
    status_: Annotated[
        TripStatus | None,
        Query(alias="status", description="Only trips with this status (trip timezone)."),
    ] = None,
    sort: Annotated[
        TripSort,
        Query(
            description=(
                "Order: `startDate` (soonest first, default), `-startDate`, `createdAt`, "
                "`-createdAt` (newest first), or `name`."
            )
        ),
    ] = "startDate",
) -> TripList:
    summaries = []
    for trip in await trip_repo.list_all(db):
        days, trip_status = countdown(trip)
        if status_ is not None and trip_status != status_:
            continue
        summaries.append(
            TripSummary(
                id=trip.id,
                name=trip.name,
                destination=trip.destination,
                timezone=trip.timezone,
                start_date=trip.start_date,
                end_date=trip.end_date,
                travelers=trip.travelers,
                traveler_count=len(trip.travelers),
                days_until_start=days,
                status=trip_status,
                created_at=trip.created_at,
                updated_at=trip.updated_at,
            )
        )
    field = sort.removeprefix("-")
    key = {
        "startDate": lambda t: (t.start_date, t.created_at),
        "createdAt": lambda t: (t.created_at,),
        "name": lambda t: (t.name.casefold(), t.created_at),
    }[field]
    summaries.sort(key=key, reverse=sort.startswith("-"))
    return TripList(trips=summaries)


@router.post(
    "",
    operation_id="create_trip",
    summary="Create a trip",
    description=(
        "Creates a trip with no travelers and one empty day per date. Returns the new trip and "
        "its ETag."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=TripResponse,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 422)},
)
async def create_trip(body: CreateTripRequest, response: Response, db: Db) -> TripResponse:
    now = utc_now()
    trip = Trip(
        schema_version=SCHEMA_VERSION,
        id=new_id("trip"),
        owner_id=None,
        name=body.name,
        destination=body.destination,
        timezone=body.timezone,
        start_date=body.start_date,
        end_date=body.end_date,
        travelers=[],
        created_at=now,
        updated_at=now,
    )
    await trip_repo.insert(db, trip)
    await day_repo.insert_missing(db, trip.id, trip_days(trip.start_date, trip.end_date), now)
    response.headers["Location"] = f"/v1/trips/{trip.id}"
    return trip_response(trip, response)


@router.get(
    "/{tripId}",
    operation_id="get_trip",
    summary="Get a trip",
    description=(
        "The trip with its travelers and countdown. Its days (lodging, start location, "
        "activities) are fetched with `list_days`."
    ),
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404)},
)
async def get_trip(trip_id: TripId, response: Response, db: Db) -> TripResponse:
    return trip_response(await load_trip(db, trip_id), response)


@router.patch(
    "/{tripId}",
    operation_id="update_trip",
    summary="Update a trip",
    description=(
        "Partial update: only the fields you send change. New dates add empty days and remove "
        "days that fall outside the range; removing a day that still has plans is rejected "
        "with 409. Changing `timezone` keeps activity times as instants (UTC); it is rejected "
        "with 409 if a timed activity would then start on a different day."
    ),
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 409, 412, 422)},
)
async def update_trip(
    trip_id: TripId,
    body: UpdateTripRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    fields = body.model_dump(exclude_unset=True)
    extra_filter = {}
    if {"startDate", "endDate", "timezone"} & fields.keys():
        current = await load_trip(db, trip_id)
        start = fields.get("startDate", current.start_date)
        end = fields.get("endDate", current.end_date)
        timezone = fields.get("timezone", current.timezone)
        if end < start:
            raise ApiError(
                422,
                f"endDate must be on or after startDate (would be {start} to {end})",
                errors=[
                    {
                        "path": "body.startDate" if "startDate" in fields else "body.endDate",
                        "message": f"endDate must be on or after startDate (got {start} and {end})",
                    }
                ],
            )
        dropped = [
            d for d in await day_repo.find_outside(db, trip_id, start, end) if day_has_content(d)
        ]
        if dropped:
            raise days_conflict(dropped, start, end)
        if timezone != current.timezone:
            conflicts = timezone_conflicts(await load_days(db, current), timezone)
            if conflicts:
                raise timezone_conflict(conflicts, timezone)
        # Guard the range check against a concurrent change to the other end of the range.
        if "startDate" not in fields:
            extra_filter["startDate"] = current.start_date
        if "endDate" not in fields:
            extra_filter["endDate"] = current.end_date
    now = utc_now()
    trip = await trip_repo.update(
        db, trip_id, fields, now, if_match=versions, extra_filter=extra_filter
    )
    if trip is None:
        raise await trip_write_failed(db, trip_id, versions)
    if {"startDate", "endDate"} & fields.keys():
        await day_repo.delete_empty_outside(db, trip_id, trip.start_date, trip.end_date)
        await day_repo.insert_missing(db, trip_id, trip_days(trip.start_date, trip.end_date), now)
    return trip_response(trip, response)


@router.delete(
    "/{tripId}",
    operation_id="delete_trip",
    summary="Delete a trip",
    description="Deletes the trip with its travelers, days, and activities. Returns 204.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 404),
)
async def delete_trip(trip_id: TripId, db: Db) -> Response:
    if not await trip_repo.delete(db, trip_id):
        raise trip_not_found(trip_id)
    await day_repo.delete_for_trip(db, trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
