from pydantic import Field

from .activity import Activity
from .common import ApiModel
from .trip import TripStatus


class ItineraryDay(ApiModel):
    """One calendar day of the trip."""

    date: str = Field(description="The day (YYYY-MM-DD) in the trip's timezone.")
    day_number: int = Field(description="1 for the trip's first day, 2 for the second, and so on.")
    activities: list[Activity] = Field(
        description="Activities on this day, by startAt; all-day activities (no startAt) last."
    )


class Itinerary(ApiModel):
    """Response of `get_itinerary`: the trip laid out day by day."""

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
    days: list[ItineraryDay] = Field(
        description="Every day from startDate to endDate, including days with no activities."
    )
    unscheduled: list[Activity] = Field(description="Activities with no date, oldest first.")
