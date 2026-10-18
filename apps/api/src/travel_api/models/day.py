from pydantic import Field

from .activity import Activity, ActivityDocument, Location
from .common import ApiModel, UtcDatetime
from .trip import TripStatus


class DayDocument(ApiModel):
    """A day as stored in the `days` collection (one document per trip day)."""

    id: str = Field(description="Internal document ID: `<tripId>_<date>`.")
    schema_version: int = Field(description="Version of the stored document shape.")
    trip_id: str = Field(description="ID of the trip.")
    date: str = Field(description="The day (YYYY-MM-DD, trip timezone).")
    lodging: Location | None = Field(description="Where the travelers stay that night.")
    start_location: Location | None = Field(description="Where the day starts.")
    activities: list[ActivityDocument] = Field(description="The day's activities.")
    created_at: UtcDatetime = Field(description="When the day was created (UTC).")
    updated_at: UtcDatetime = Field(description="When the day or its activities last changed.")


class Day(ApiModel):
    """One calendar day of a trip, with where you sleep, where you start, and what you do."""

    trip_id: str = Field(description="ID of the trip.")
    date: str = Field(description="The day (YYYY-MM-DD) in the trip's timezone.")
    day_number: int = Field(description="1 for the trip's first day, 2 for the second, and so on.")
    lodging: Location | None = Field(
        description="Where the travelers stay that night, or null if not decided."
    )
    start_location: Location | None = Field(
        description="Where the day starts, or null (usually the previous night's lodging)."
    )
    activities: list[Activity] = Field(
        description="The day's activities, by start time; activities with no time come last."
    )
    created_at: UtcDatetime = Field(description="When the day was created (UTC).")
    updated_at: UtcDatetime = Field(
        description=(
            "When the day or any of its activities last changed (UTC). The day's ETag is "
            "derived from this."
        )
    )


class DayList(ApiModel):
    """Response of `list_days`: the whole trip, day by day."""

    trip_id: str = Field(description="Trip ID.")
    timezone: str = Field(
        description="IANA timezone of the trip. Times are UTC; convert with this for display."
    )
    start_date: str = Field(description="First day of the trip (YYYY-MM-DD).")
    end_date: str = Field(description="Last day of the trip (YYYY-MM-DD).")
    days_until_start: int = Field(
        description="Whole days from today (trip timezone) to startDate; negative once started."
    )
    status: TripStatus = Field(description="`upcoming`, `ongoing`, or `past`.")
    days: list[Day] = Field(description="Every day from startDate to endDate, in order.")


class UpdateDayRequest(ApiModel):
    """Body for `update_day`. Only the fields you send are changed; null clears a field."""

    lodging: Location | None = Field(
        default=None, description="Where the travelers stay that night; null clears it."
    )
    start_location: Location | None = Field(
        default=None, description="Where the day starts; null clears it."
    )
