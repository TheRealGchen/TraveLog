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


class Schedule(ApiModel):
    """When an activity happens. All null means unscheduled."""

    date: str | None = Field(
        description=(
            "Calendar day (YYYY-MM-DD) in the trip's timezone, or null if unscheduled. "
            "Derived from startAt when startAt is set."
        )
    )
    start_at: UtcDatetime | None = Field(description="Start time (UTC), or null for all-day.")
    end_at: UtcDatetime | None = Field(description="End time (UTC), or null.")


class ScheduleInput(ApiModel):
    """When an activity happens. Omitted fields are null; all null means unscheduled.

    - Only `date`: an all-day activity on that day.
    - `startAt` (and optionally `endAt`): a timed activity; `date` is derived from `startAt` in
      the trip's timezone, so you can omit it. If you send it, it must agree.
    """

    date: DateStr | None = Field(
        default=None,
        description="Calendar day (YYYY-MM-DD) in the trip's timezone; must be within the trip.",
    )
    start_at: UtcDatetime | None = Field(
        default=None,
        description="Start time, ISO 8601 with an offset or Z, e.g. 2027-04-03T10:00:00+09:00.",
    )
    end_at: UtcDatetime | None = Field(
        default=None,
        description="End time, ISO 8601 with an offset or Z. Requires startAt and must be later.",
    )

    @model_validator(mode="after")
    def _times_in_order(self) -> Self:
        _check_times(self.start_at, self.end_at)
        return self


class Location(ApiModel):
    """Where an activity happens."""

    name: str = Field(
        description="Place name or address.", min_length=1, max_length=200, examples=["Toyosu"]
    )


class Activity(ApiModel):
    """An activity, stored as its own document in the `activities` collection."""

    id: str = Field(description="Activity ID, prefixed with `act_`.", examples=["act_01J..."])
    schema_version: int = Field(description="Version of the stored document shape.")
    trip_id: str = Field(description="ID of the trip this activity belongs to.")
    title: str = Field(description="What the activity is.", examples=["teamLab Planets"])
    status: ActivityStatus = Field(description="`idea`, `planned`, or `done`.")
    schedule: Schedule = Field(description="When the activity happens.")
    location: Location | None = Field(description="Where the activity happens, or null.")
    notes: str | None = Field(description="Free-text notes, or null.")
    traveler_ids: list[str] = Field(
        description="IDs of the trip's travelers taking part. Empty means not assigned."
    )
    created_at: UtcDatetime = Field(description="When the activity was created (UTC).")
    updated_at: UtcDatetime = Field(
        description="When the activity was last changed (UTC). The ETag is derived from this."
    )


class ActivityList(ApiModel):
    """Response of `list_activities`."""

    activities: list[Activity] = Field(
        description=(
            "Matching activities: scheduled ones by date then start time (all-day after timed "
            "ones on the same day), then unscheduled ones by creation time."
        )
    )


class AddActivityRequest(ApiModel):
    """Body for `add_activity`."""

    title: str = Field(
        description="What the activity is.",
        min_length=1,
        max_length=200,
        examples=["teamLab Planets"],
    )
    schedule: ScheduleInput | None = Field(
        default=None, description="When it happens. Omit or send null for an unscheduled idea."
    )
    location: Location | None = Field(default=None, description="Where it happens.")
    notes: str | None = Field(default=None, description="Free-text notes.", max_length=5000)
    status: ActivityStatus | None = Field(
        default=None,
        description="Defaults to `planned` if the activity has a date, otherwise `idea`.",
    )
    traveler_ids: list[str] = Field(
        default_factory=list, description="IDs of travelers on this trip who take part."
    )


class UpdateActivityRequest(ApiModel):
    """Body for `update_activity`. Only the fields you send are changed; send null to clear
    `location` or `notes`.

    `schedule` and `location` are replaced as a whole: send the complete object. Send
    `"schedule": null` to unschedule. To move an activity to another day while keeping its
    times of day, use `move_activity`.
    """

    title: Annotated[str | None, NotNull] = patch_field(
        "What the activity is. Cannot be null.", min_length=1, max_length=200
    )
    schedule: ScheduleInput | None = Field(
        default=None, description="Replaces the whole schedule; null unschedules the activity."
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

    - `date: null` unschedules the activity (and clears its times).
    - `date` alone keeps each time of day, in the trip's timezone, on the new day.
    - `date` with `startAt` (and optionally `endAt`) sets new times; an omitted `endAt` keeps the
      previous duration, and `endAt: null` clears it.
    """

    date: DateStr | None = Field(
        description="New day (YYYY-MM-DD, trip timezone, within the trip), or null to unschedule."
    )
    start_at: UtcDatetime | None = Field(
        default=None, description="New start time, ISO 8601 with an offset or Z."
    )
    end_at: UtcDatetime | None = Field(
        default=None, description="New end time, ISO 8601 with an offset or Z. Requires startAt."
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.date is None and (self.start_at is not None or self.end_at is not None):
            raise ValueError("startAt and endAt cannot be set when date is null (unscheduling)")
        _check_times(self.start_at, self.end_at)
        return self
