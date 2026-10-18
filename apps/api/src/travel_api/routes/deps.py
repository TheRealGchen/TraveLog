"""Dependencies and helpers shared by the route modules."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Header, Path, Request, Response

from ..db import Database
from ..errors import ApiError, not_found
from ..models import Activity, Problem, Trip, TripResponse
from ..repository import activities as activity_repo
from ..repository import trips as trip_repo
from ..scheduling import countdown


def get_db(request: Request) -> Database:
    return request.app.state.db


TripId = Annotated[
    str, Path(alias="tripId", description="Trip ID (`trip_...`).", examples=["trip_01J..."])
]
TravelerId = Annotated[str, Path(alias="travelerId", description="Traveler ID (`trv_...`).")]
ActivityId = Annotated[str, Path(alias="activityId", description="Activity ID (`act_...`).")]
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


def activity_response(activity: Activity, response: Response) -> Activity:
    response.headers["ETag"] = etag(activity.updated_at)
    return activity


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


async def activity_write_failed(
    db: Database, trip_id: str, activity_id: str, if_match: list[datetime] | None
) -> ApiError:
    current = await activity_repo.get(db, trip_id, activity_id)
    if current is None:
        return activity_not_found(trip_id, activity_id)
    if if_match is not None and current.updated_at not in if_match:
        return stale(etag(current.updated_at), current)
    return concurrent_change(f"Activity {activity_id}")


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
