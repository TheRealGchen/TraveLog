from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..db import Database
from ..ids import new_id
from ..models import AddTravelerRequest, TripResponse, UpdateTravelerRequest, utc_now
from ..repository import days as day_repo
from ..repository import trips as trip_repo
from .deps import (
    ETAG_HEADER,
    IfMatch,
    TravelerId,
    TripId,
    get_db,
    load_trip,
    parse_if_match,
    problems,
    traveler_not_found,
    trip_response,
    trip_write_failed,
)

router = APIRouter(prefix="/trips/{tripId}/travelers", tags=["Travelers"])

Db = Annotated[Database, Depends(get_db)]


async def _traveler_write_failed(db: Database, trip_id: str, traveler_id: str, versions):
    trip = await load_trip(db, trip_id)
    if not any(t.id == traveler_id for t in trip.travelers):
        return traveler_not_found(trip, traveler_id)
    return await trip_write_failed(db, trip_id, versions)


@router.post(
    "",
    operation_id="add_traveler",
    summary="Add a traveler to a trip",
    description=(
        "Appends a traveler. Without `color`, the next unused palette color is assigned. "
        "Returns the updated trip; the new traveler is the last item of `travelers`."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=TripResponse,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def add_traveler(
    trip_id: TripId,
    body: AddTravelerRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    trip = await trip_repo.add_traveler(
        db, trip_id, new_id("trv"), body.name, body.color, utc_now(), if_match=versions
    )
    if trip is None:
        raise await trip_write_failed(db, trip_id, versions)
    return trip_response(trip, response)


@router.patch(
    "/{travelerId}",
    operation_id="update_traveler",
    summary="Update a traveler",
    description="Changes a traveler's name or color. Returns the updated trip.",
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def update_traveler(
    trip_id: TripId,
    traveler_id: TravelerId,
    body: UpdateTravelerRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    fields = body.model_dump(exclude_unset=True)
    trip = await trip_repo.update_traveler(
        db, trip_id, traveler_id, fields, utc_now(), if_match=versions
    )
    if trip is None:
        raise await _traveler_write_failed(db, trip_id, traveler_id, versions)
    return trip_response(trip, response)


@router.delete(
    "/{travelerId}",
    operation_id="remove_traveler",
    summary="Remove a traveler",
    description=(
        "Removes the traveler from the trip and from every activity of the trip. "
        "Returns the updated trip."
    ),
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412)},
)
async def remove_traveler(
    trip_id: TripId,
    traveler_id: TravelerId,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    now = utc_now()
    trip = await trip_repo.remove_traveler(db, trip_id, traveler_id, now, if_match=versions)
    if trip is None:
        raise await _traveler_write_failed(db, trip_id, traveler_id, versions)
    await day_repo.pull_traveler(db, trip_id, traveler_id, now)
    return trip_response(trip, response)
