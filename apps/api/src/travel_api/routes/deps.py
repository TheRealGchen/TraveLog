"""Dependencies and helpers shared by the route modules."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Header, Path, Request, Response

from ..db import Database
from ..errors import ApiError, not_found
from ..models import (
    Activity,
    ActivityDocument,
    Day,
    DayDocument,
    Problem,
    Trip,
    TripResponse,
    utc_now,
)
from ..repository import days as day_repo
from ..repository import trips as trip_repo
from ..scheduling import countdown, day_number, in_trip, sort_key_in_day, trip_days


def get_db(request: Request) -> Database:
    return request.app.state.db


TripId = Annotated[
    str, Path(alias="tripId", description="Trip ID (`trip_...`).", examples=["trip_01J..."])
]
TravelerId = Annotated[str, Path(alias="travelerId", description="Traveler ID (`trv_...`).")]
ActivityId = Annotated[str, Path(alias="activityId", description="Activity ID (`act_...`).")]
DayDate = Annotated[
    str,
    Path(
        alias="date",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="The day (YYYY-MM-DD, trip timezone); must be within the trip.",
        examples=["2027-04-03"],
    ),
]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description=(
            "Optional. The ETag from a previous response; the change is applied only if the "
            "resource has not changed since. On mismatch the API returns 412 with the current "
            "version."
        ),
    ),
]


def etag(updated_at: datetime) -> str:
    return f'"{int(updated_at.timestamp() * 1000)}"'


def parse_if_match(value: str | None) -> list[datetime] | None:
    """Turn an If-Match header into the ``updatedAt`` values it allows (None = no condition)."""
    if value is None or value.strip() == "*":
        return None
    allowed = []
    for tag in value.split(","):
        tag = tag.strip().removeprefix("W/").strip('"')
        if tag.isdigit():
            allowed.append(datetime.fromtimestamp(int(tag) / 1000, UTC))
    if not allowed:
        raise ApiError(
            412,
            f"If-Match {value!r} is not an ETag issued by this API. Send the exact ETag "
            "header value from a previous response, or omit If-Match.",
        )
    return allowed


def trip_response(trip: Trip, response: Response | None = None) -> TripResponse:
    days, status = countdown(trip)
    if response is not None:
        response.headers["ETag"] = etag(trip.updated_at)
    return TripResponse(**trip.model_dump(by_alias=False), days_until_start=days, status=status)


def to_activity(trip_id: str, date: str, activity: ActivityDocument) -> Activity:
    return Activity.model_validate({**activity.model_dump(), "tripId": trip_id, "date": date})


def activity_response(activity: Activity, response: Response) -> Activity:
    response.headers["ETag"] = etag(activity.updated_at)
    return activity


def day_response(trip: Trip, day: DayDocument, response: Response | None = None) -> Day:
    if response is not None:
        response.headers["ETag"] = etag(day.updated_at)
    return Day(
        trip_id=trip.id,
        date=day.date,
        day_number=day_number(trip, day.date),
        lodging=day.lodging,
        start_location=day.start_location,
        activities=[
            to_activity(trip.id, day.date, a) for a in sorted(day.activities, key=sort_key_in_day)
        ],
        created_at=day.created_at,
        updated_at=day.updated_at,
    )


def day_not_found(trip: Trip, date: str) -> ApiError:
    return not_found(
        f"Trip {trip.id} has no day {date}; it runs from {trip.start_date} to {trip.end_date}."
    )


async def load_day(db: Database, trip: Trip, date: str) -> DayDocument:
    """The stored day, creating it if the trip predates day documents."""
    if not in_trip(trip, date):
        raise day_not_found(trip, date)
    day = await day_repo.get(db, trip.id, date)
    if day is None:
        await day_repo.insert_missing(db, trip.id, [date], utc_now())
        day = await day_repo.get(db, trip.id, date)
    assert day is not None
    return day


async def load_days(db: Database, trip: Trip) -> list[DayDocument]:
    """Every day of the trip in order, creating any that are missing (lazy migration)."""
    stored = {d.date: d for d in await day_repo.list_for_trip(db, trip.id)}
    expected = trip_days(trip.start_date, trip.end_date)
    missing = [d for d in expected if d not in stored]
    if missing:
        await day_repo.insert_missing(db, trip.id, missing, utc_now())
        stored = {d.date: d for d in await day_repo.list_for_trip(db, trip.id)}
    return [stored[d] for d in expected if d in stored]


def trip_not_found(trip_id: str) -> ApiError:
    return not_found(f"Trip {trip_id} not found. List trips with GET /v1/trips.")


async def load_trip(db: Database, trip_id: str) -> Trip:
    trip = await trip_repo.get(db, trip_id)
    if trip is None:
        raise trip_not_found(trip_id)
    return trip


def traveler_not_found(trip: Trip, traveler_id: str) -> ApiError:
    known = ", ".join(t.id for t in trip.travelers) or "none"
    return not_found(
        f"Traveler {traveler_id} not found on trip {trip.id} (travelers on this trip: {known})."
    )


def activity_not_found(trip_id: str, activity_id: str) -> ApiError:
    return not_found(
        f"Activity {activity_id} not found on trip {trip_id}. "
        f"List activities with GET /v1/trips/{trip_id}/activities."
    )


async def trip_write_failed(
    db: Database, trip_id: str, if_match: list[datetime] | None
) -> ApiError:
    """Explain why a conditional trip write matched nothing: missing trip or stale ETag."""
    current = await trip_repo.get(db, trip_id)
    if current is None:
        return trip_not_found(trip_id)
    if if_match is not None and current.updated_at not in if_match:
        return stale(etag(current.updated_at), trip_response(current))
    return concurrent_change(f"Trip {trip_id}")


def check_travelers(ids: list[str], trip: Trip) -> list[str]:
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


def concurrent_change(what: str) -> ApiError:
    return ApiError(409, f"{what} changed while this request was being applied. Retry it.")


def stale(current_etag: str, current: Any) -> ApiError:
    return ApiError(
        412,
        f"The resource changed since your If-Match ETag; the current ETag is {current_etag}. "
        "Re-read it (it is included as `current`), reapply your change, and retry.",
        current=current,
        headers={"ETag": current_etag},
    )


def problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for problem+json error responses."""
    descriptions = {
        401: "Missing or invalid bearer token.",
        404: "A trip, traveler, or activity ID in the path does not exist.",
        409: "The change conflicts with other data (the detail says what to fix).",
        412: "If-Match did not match the current ETag; `current` holds the current version.",
        422: "The request is invalid; `errors` lists each problem with its path.",
    }
    return {code: {"model": Problem, "description": descriptions[code]} for code in codes}


ETAG_HEADER = {
    "ETag": {
        "description": "Version of the returned resource; send it back as If-Match.",
        "schema": {"type": "string"},
    }
}
