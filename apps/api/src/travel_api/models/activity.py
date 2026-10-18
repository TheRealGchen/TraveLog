from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from .common import (
    ApiModel,
    DateStr,
    NotNull,
    UtcDatetime,
    format_utc,
    patch_field,
)

ActivityStatus = Literal["idea", "planned", "done"]


def _check_times(start_at: Any, end_at: Any) -> None:
    if end_at is not None and start_at is None:
        raise ValueError("endAt requires startAt; send startAt as well, or drop endAt")
    if start_at is not None and end_at is not None and end_at <= start_at:
        raise ValueError(
            f"endAt must be after startAt (got {format_utc(start_at)} and {format_utc(end_at)})"
        )


class ActivityTime(ApiModel):
    """When a timed activity happens (UTC). An activity without times has `time: null`."""

    start_at: UtcDatetime = Field(description="Start time (UTC). Falls on the activity's day.")
    end_at: UtcDatetime | None = Field(description="End time (UTC), or null if open-ended.")


class ActivityTimeInput(ApiModel):
    """Start and optional end of an activity.

    Send ISO 8601 timestamps with an offset or Z, e.g. `2027-04-03T10:00:00+09:00`. `startAt`
    must fall on the activity's day in the trip's timezone; `endAt` may be on a later day.
    """

    start_at: UtcDatetime = Field(
        description="Start time, ISO 8601 with an offset or Z, e.g. 2027-04-03T10:00:00+09:00."
    )
    end_at: UtcDatetime | None = Field(
        default=None, description="End time, ISO 8601 with an offset or Z. Must be after startAt."
    )

    @model_validator(mode="after")
    def _times_in_order(self) -> Self:
        _check_times(self.start_at, self.end_at)
        return self


class Location(ApiModel):
    """A place."""

    name: str = Field(
        description="Place name or address.", min_length=1, max_length=200, examples=["Toyosu"]
    )


class ActivityDocument(ApiModel):
    """An activity as stored inside its day document."""

    id: str = Field(description="Activity ID, prefixed with `act_`.")
    title: str = Field(description="What the activity is.")
    status: ActivityStatus = Field(description="`idea`, `planned`, or `done`.")
    time: ActivityTime | None = Field(description="Start and end time, or null if untimed.")
    location: Location | None = Field(description="Where it happens, or null.")
    notes: str | None = Field(description="Free-text notes, or null.")
    traveler_ids: list[str] = Field(description="IDs of the trip's travelers taking part.")
    created_at: UtcDatetime = Field(description="When the activity was created (UTC).")
    updated_at: UtcDatetime = Field(description="When the activity was last changed (UTC).")


class Activity(ApiModel):
    """An activity on one day of a trip."""

    id: str = Field(description="Activity ID, prefixed with `act_`.", examples=["act_01J..."])
    trip_id: str = Field(description="ID of the trip.")
    date: str = Field(description="The day (YYYY-MM-DD, trip timezone) this activity is on.")
    title: str = Field(description="What the activity is.", examples=["teamLab Planets"])
    status: ActivityStatus = Field(description="`idea` (maybe), `planned`, or `done`.")
    time: ActivityTime | None = Field(
        description="Start and end time (UTC), or null for an activity with no fixed time."
    )
    location: Location | None = Field(description="Where the activity happens, or null.")
    notes: str | None = Field(description="Free-text notes, or null.")
    traveler_ids: list[str] = Field(
        description="IDs of the trip's travelers taking part. Empty means not assigned."
    )
    created_at: UtcDatetime = Field(description="When the activity was created (UTC).")
    updated_at: UtcDatetime = Field(
        description="When the activity was last changed (UTC). Its ETag is derived from this."
    )


class ActivityList(ApiModel):
    """Response of `list_activities`."""

    activities: list[Activity] = Field(
        description="Matching activities by day, then start time (untimed ones last in a day)."
    )


class AddActivityRequest(ApiModel):
    """Body for `add_activity`. The day comes from the URL."""

    title: str = Field(
        description="What the activity is.",
        min_length=1,
        max_length=200,
        examples=["teamLab Planets"],
    )
    time: ActivityTimeInput | None = Field(
        default=None, description="Start and optional end. Omit for an activity with no time."
    )
    location: Location | None = Field(default=None, description="Where it happens.")
    notes: str | None = Field(default=None, description="Free-text notes.", max_length=5000)
    status: Annotated[ActivityStatus | None, NotNull] = patch_field(
        "`idea`, `planned`, or `done`. Defaults to `planned`."
    )
    traveler_ids: list[str] = Field(
        default_factory=list, description="IDs of travelers on this trip who take part."
    )


class UpdateActivityRequest(ApiModel):
    """Body for `update_activity`. Only the fields you send are changed; send null to clear
    `time`, `location`, or `notes`.

    `time` and `location` are replaced as a whole. To move the activity to another day, use
    `move_activity`.
    """

    title: Annotated[str | None, NotNull] = patch_field(
        "What the activity is. Cannot be null.", min_length=1, max_length=200
    )
    time: ActivityTimeInput | None = Field(
        default=None, description="Replaces the times; null makes the activity untimed."
    )
    location: Location | None = Field(
        default=None, description="Replaces the location; null clears it."
    )
    notes: str | None = Field(default=None, description="Notes; null clears them.", max_length=5000)
    status: Annotated[ActivityStatus | None, NotNull] = patch_field(
        "`idea`, `planned`, or `done`. Cannot be null."
    )
    traveler_ids: Annotated[list[str] | None, NotNull] = patch_field(
        "Replaces the list of travelers taking part. Cannot be null."
    )


class MoveActivityRequest(ApiModel):
    """Body for `move_activity`.

    - `date` alone keeps each time of day, in the trip's timezone, on the new day.
    - `date` with `startAt` (and optionally `endAt`) sets new times; an omitted `endAt` keeps
      the previous duration, and `endAt: null` clears it.
    """

    date: DateStr = Field(description="Target day (YYYY-MM-DD, trip timezone, within the trip).")
    start_at: UtcDatetime | None = Field(
        default=None, description="New start time on the target day, ISO 8601 with an offset or Z."
    )
    end_at: UtcDatetime | None = Field(
        default=None, description="New end time, ISO 8601 with an offset or Z. Requires startAt."
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_times(self.start_at, self.end_at)
        return self
