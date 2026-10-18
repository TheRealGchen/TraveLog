from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..db import Database
from ..errors import ApiError
from ..ids import new_id
from ..models import (
    AddTravelerRequest,
    AddTravelersRequest,
    Trip,
    TripResponse,
    UpdateTravelerRequest,
    utc_now,
)
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


Row = tuple[str, str | None, str | None]
"""(path prefix, email, passport number) of one traveler in a request."""


def _duplicate_errors(rows: list[Row], trip: Trip, except_id: str | None = None) -> list[dict]:
    """Emails and passport numbers that clash with the trip's travelers or with each other."""
    errors = []
    for field, label, index in (("email", "email", 1), ("passportNumber", "passport number", 2)):
        attr = "email" if field == "email" else "passport_number"
        taken = {getattr(t, attr): t for t in trip.travelers if t.id != except_id}
        seen: dict[str, str] = {}
        for row in rows:
            value, path = row[index], f"{row[0]}.{field}"
            if not value:
                continue
            if (owner := taken.get(value)) is not None:
                message = (
                    f"{label} {value} is already used by {owner.name} ({owner.id}) on this trip"
                )
                errors.append({"path": path, "message": message})
            elif value in seen:
                message = (
                    f"{label} {value} appears more than once in this request (also {seen[value]})"
                )
                errors.append({"path": path, "message": message})
            seen.setdefault(value, path)
    return errors


def _check_duplicates(rows: list[Row], trip: Trip, except_id: str | None = None) -> None:
    errors = _duplicate_errors(rows, trip, except_id)
    if errors:
        detail = "; ".join(f"{e['path']}: {e['message']}" for e in errors)
        raise ApiError(422, detail, errors=errors)


async def _add(
    db: Database, trip_id: str, items: list[AddTravelerRequest], prefixes: list[str], if_match
) -> Trip:
    """Validate and append travelers in one atomic write (all or nothing)."""
    rows = [(p, t.email, t.passport_number) for p, t in zip(prefixes, items, strict=True)]
    _check_duplicates(rows, await load_trip(db, trip_id))
    docs = [
        {
            "id": new_id("trv"),
            "name": t.name,
            "color": t.color,
            "email": t.email,
            "passportNumber": t.passport_number,
        }
        for t in items
    ]
    trip = await trip_repo.add_travelers(db, trip_id, docs, utc_now(), if_match=if_match)
    if trip is None:
        # Someone else may have added a clashing traveler since the check above.
        _check_duplicates(rows, await load_trip(db, trip_id))
        raise await trip_write_failed(db, trip_id, if_match)
    return trip


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
        "Appends a traveler. Only `name` is required. Without `color`, the next unused palette "
        "color is assigned. Email and passport number must be unique within the trip. Returns "
        "the updated trip; the new traveler is the last item of `travelers`."
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
    trip = await _add(db, trip_id, [body], ["body"], parse_if_match(if_match))
    return trip_response(trip, response)


@router.post(
    "/batch",
    operation_id="add_travelers",
    summary="Add several travelers at once",
    description=(
        "Appends 1 to 50 travelers in order, all or nothing: if any entry is invalid, nothing "
        "is added and each problem is reported with its path (e.g. `body.travelers.1.email`). "
        "Travelers without `color` get successive unused palette colors. Returns the updated "
        "trip; the new travelers are the last items of `travelers`."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=TripResponse,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def add_travelers(
    trip_id: TripId,
    body: AddTravelersRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> TripResponse:
    prefixes = [f"body.travelers.{i}" for i in range(len(body.travelers))]
    trip = await _add(db, trip_id, body.travelers, prefixes, parse_if_match(if_match))
    return trip_response(trip, response)


@router.patch(
    "/{travelerId}",
    operation_id="update_traveler",
    summary="Update a traveler",
    description=(
        "Changes a traveler's name, color, email, or passport number; null clears email or "
        "passport number. Returns the updated trip."
    ),
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
    rows = [("body", fields.get("email"), fields.get("passportNumber"))]
    current = await load_trip(db, trip_id)
    if not any(t.id == traveler_id for t in current.travelers):
        raise traveler_not_found(current, traveler_id)
    _check_duplicates(rows, current, except_id=traveler_id)
    trip = await trip_repo.update_traveler(
        db, trip_id, traveler_id, fields, utc_now(), if_match=versions
    )
    if trip is None:
        _check_duplicates(rows, await load_trip(db, trip_id), except_id=traveler_id)
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
