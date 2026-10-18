from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import (
    ApiModel,
    DateStr,
    NotNull,
    TimezoneName,
    UtcDatetime,
    patch_field,
)
from .link import PinnedLink
from .traveler import Traveler

TripStatus = Literal["upcoming", "ongoing", "past"]
TripSort = Literal["startDate", "-startDate", "createdAt", "-createdAt", "name"]


def _check_range(start: str | None, end: str | None) -> None:
    if start is not None and end is not None and end < start:
        raise ValueError(f"endDate must be on or after startDate (got {start} and {end})")


class Trip(ApiModel):
    """A trip as stored in the `trips` collection. Its days live in the `days` collection."""

    id: str = Field(description="Trip ID, prefixed with `trip_`.", examples=["trip_01J..."])
    schema_version: int = Field(description="Version of the stored document shape.")
    owner_id: str | None = Field(description="Owner user ID. Always null until accounts exist.")
    name: str = Field(description="Trip name.", examples=["Japan 2027"])
    destination: str | None = Field(
        description="Free-text destination, or null.", examples=["Tokyo & Kyoto"]
    )
    timezone: TimezoneName = Field(
        description=(
            "IANA timezone of the trip. Trip dates and activity days are calendar dates in "
            "this timezone."
        )
    )
    start_date: DateStr = Field(description="First day of the trip (YYYY-MM-DD, trip timezone).")
    end_date: DateStr = Field(description="Last day of the trip (YYYY-MM-DD, trip timezone).")
    travelers: list[Traveler] = Field(description="People on the trip, in the order added.")
    links: list[PinnedLink] = Field(
        description="Web links pinned to the trip (bookings, guides, maps), in the order pinned."
    )
    created_at: UtcDatetime = Field(description="When the trip was created (UTC).")
    updated_at: UtcDatetime = Field(
        description="When the trip was last changed (UTC). The ETag is derived from this."
    )


class TripResponse(Trip):
    """A trip with values computed at request time."""

    days_until_start: int = Field(
        description=(
            "Whole days from today (in the trip's timezone) to startDate. 0 on the first day, "
            "negative once the trip has started."
        )
    )
    status: TripStatus = Field(
        description=(
            "`upcoming` before startDate, `ongoing` from startDate to endDate inclusive, "
            "`past` after endDate (all in the trip's timezone)."
        )
    )


class TripSummary(ApiModel):
    """The list view of a trip, with everything a trip card needs."""

    id: str = Field(description="Trip ID, prefixed with `trip_`.")
    name: str = Field(description="Trip name.")
    destination: str | None = Field(description="Free-text destination, or null.")
    timezone: str = Field(description="IANA timezone of the trip.")
    start_date: str = Field(description="First day of the trip (YYYY-MM-DD).")
    end_date: str = Field(description="Last day of the trip (YYYY-MM-DD).")
    travelers: list[Traveler] = Field(description="People on the trip, in the order added.")
    traveler_count: int = Field(description="Number of travelers on the trip.")
    days_until_start: int = Field(
        description="Whole days from today (trip timezone) to startDate; negative once started."
    )
    status: TripStatus = Field(description="`upcoming`, `ongoing`, or `past`.")
    created_at: UtcDatetime = Field(description="When the trip was created (UTC).")
    updated_at: UtcDatetime = Field(description="When the trip was last changed (UTC).")


class TripList(ApiModel):
    """Response of `list_trips`."""

    trips: list[TripSummary] = Field(description="Trips matching the query, in the chosen order.")


class CreateTripRequest(ApiModel):
    """Body for `create_trip`."""

    name: str = Field(
        description="Trip name.", min_length=1, max_length=120, examples=["Japan 2027"]
    )
    start_date: DateStr = Field(description="First day of the trip (YYYY-MM-DD).")
    end_date: DateStr = Field(
        description="Last day of the trip (YYYY-MM-DD), on or after startDate."
    )
    destination: str | None = Field(
        default=None, description="Free-text destination.", max_length=200
    )
    timezone: TimezoneName = Field(
        default="UTC", description="IANA timezone name of the destination. Defaults to `UTC`."
    )

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        _check_range(self.start_date, self.end_date)
        return self


class UpdateTripRequest(ApiModel):
    """Body for `update_trip`. Only the fields you send are changed; send null to clear
    `destination`.

    Changing `timezone` keeps every activity's UTC instants and recomputes the day of each timed
    activity. Changing the dates or timezone is rejected if a scheduled activity would fall
    outside the trip's dates.
    """

    name: Annotated[str | None, NotNull] = patch_field(
        "Trip name. Cannot be null.", min_length=1, max_length=120
    )
    destination: str | None = Field(
        default=None, description="Free-text destination; null clears it.", max_length=200
    )
    timezone: Annotated[TimezoneName | None, NotNull] = patch_field(
        "IANA timezone name. Cannot be null."
    )
    start_date: Annotated[DateStr | None, NotNull] = patch_field(
        "First day (YYYY-MM-DD). Cannot be null."
    )
    end_date: Annotated[DateStr | None, NotNull] = patch_field(
        "Last day (YYYY-MM-DD). Cannot be null."
    )

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        _check_range(self.start_date, self.end_date)
        return self


def trip_status(start_date: str, end_date: str, today: str) -> TripStatus:
    if today < start_date:
        return "upcoming"
    if today > end_date:
        return "past"
    return "ongoing"
