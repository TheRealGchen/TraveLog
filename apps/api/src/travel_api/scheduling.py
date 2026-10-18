"""Date and time rules: trip countdowns, deriving activity days, and moving activities."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .errors import ApiError, invalid
from .models import (
    Activity,
    ActivityStatus,
    MoveActivityRequest,
    Schedule,
    ScheduleInput,
    Trip,
    TripStatus,
    format_utc,
    trip_status,
)


def today_in(timezone: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()


def countdown(trip: Trip, now: datetime | None = None) -> tuple[int, TripStatus]:
    """``(daysUntilStart, status)`` computed from today in the trip's timezone."""
    today = today_in(trip.timezone, now)
    days = (date.fromisoformat(trip.start_date) - today).days
    return days, trip_status(trip.start_date, trip.end_date, today.isoformat())


def local_date(instant: datetime, timezone: str) -> str:
    return instant.astimezone(ZoneInfo(timezone)).date().isoformat()


def trip_days(start_date: str, end_date: str) -> list[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _check_in_trip(day: str, trip: Trip, path: str, what: str) -> None:
    if not trip.start_date <= day <= trip.end_date:
        raise invalid(
            path,
            f"{what} {day} is outside the trip ({trip.start_date} to {trip.end_date}, "
            f"{trip.timezone}); pick a day in that range or unschedule the activity",
        )


def resolve_schedule(value: ScheduleInput | None, trip: Trip, path: str) -> Schedule:
    """Turn a requested schedule into the stored one, deriving ``date`` from ``startAt``."""
    if value is None or (value.date is None and value.start_at is None):
        return Schedule(date=None, start_at=None, end_at=None)
    day = value.date
    if value.start_at is not None:
        derived = local_date(value.start_at, trip.timezone)
        if day is not None and day != derived:
            raise invalid(
                f"{path}.date",
                f"date {day} does not match startAt {format_utc(value.start_at)}, which is on "
                f"{derived} in {trip.timezone}; omit date (it is derived from startAt) or make "
                f"them agree",
            )
        day = derived
        _check_in_trip(day, trip, f"{path}.startAt", "startAt falls on")
    else:
        assert day is not None
        _check_in_trip(day, trip, f"{path}.date", "date")
    return Schedule(date=day, start_at=value.start_at, end_at=value.end_at)


def _shift_to_day(instant: datetime, timezone: str, day_offset: int) -> datetime:
    """Move ``instant`` by whole calendar days, keeping its wall-clock time in ``timezone``."""
    tz = ZoneInfo(timezone)
    local = instant.astimezone(tz)
    moved = datetime.combine(local.date() + timedelta(days=day_offset), local.time(), tzinfo=tz)
    return moved.astimezone(UTC)


def move_schedule(current: Schedule, request: MoveActivityRequest, trip: Trip) -> Schedule:
    """Apply a ``move_activity`` request to an activity's current schedule."""
    sent = request.model_fields_set
    if request.date is None:
        return Schedule(date=None, start_at=None, end_at=None)

    if "start_at" in sent and request.start_at is not None:
        end_at = request.end_at
        if "end_at" not in sent and current.start_at and current.end_at:
            end_at = request.start_at + (current.end_at - current.start_at)
        target = ScheduleInput(date=request.date, start_at=request.start_at, end_at=end_at)
        return resolve_schedule(target, trip, "body")

    _check_in_trip(request.date, trip, "body.date", "date")
    if current.start_at is None:
        # All-day or unscheduled: only the day changes.
        return Schedule(date=request.date, start_at=None, end_at=None)
    # Keep each time of day on the new day, in the trip's timezone.
    from_day = date.fromisoformat(local_date(current.start_at, trip.timezone))
    offset = (date.fromisoformat(request.date) - from_day).days
    start_at = _shift_to_day(current.start_at, trip.timezone, offset)
    end_at = _shift_to_day(current.end_at, trip.timezone, offset) if current.end_at else None
    if "end_at" in sent:
        end_at = None
    return Schedule(date=local_date(start_at, trip.timezone), start_at=start_at, end_at=end_at)


def status_after_reschedule(status: ActivityStatus, new_date: str | None) -> ActivityStatus:
    """Scheduling an idea makes it planned; unscheduling a planned activity makes it an idea."""
    if new_date is not None and status == "idea":
        return "planned"
    if new_date is None and status == "planned":
        return "idea"
    return status


def default_status(schedule: Schedule) -> ActivityStatus:
    return "planned" if schedule.date is not None else "idea"


def activities_outside_range(
    activities: Iterable[Activity], start_date: str, end_date: str, timezone: str
) -> list[tuple[Activity, str]]:
    """Scheduled activities whose day (recomputed in ``timezone``) would fall outside the range."""
    outside = []
    for activity in activities:
        s = activity.schedule
        day = local_date(s.start_at, timezone) if s.start_at else s.date
        if day is not None and not start_date <= day <= end_date:
            outside.append((activity, day))
    return outside


def sort_key_in_day(activity: Activity) -> tuple[bool, datetime, datetime]:
    start = activity.schedule.start_at
    return (start is None, start or activity.created_at, activity.created_at)


def sort_key_flat(activity: Activity) -> tuple[bool, str, bool, datetime, datetime]:
    s = activity.schedule
    return (
        s.date is None,
        s.date or "",
        s.start_at is None,
        s.start_at or activity.created_at,
        activity.created_at,
    )


def conflict_with_activities(outside: list[tuple[Activity, str]], trip_range: str) -> ApiError:
    listed = ", ".join(f"{a.id} '{a.title}' ({day})" for a, day in outside[:10])
    more = f" and {len(outside) - 10} more" if len(outside) > 10 else ""
    return ApiError(
        409,
        f"This change would leave {len(outside)} scheduled activit"
        f"{'y' if len(outside) == 1 else 'ies'} outside the trip ({trip_range}): {listed}{more}. "
        "Move or unschedule them first (move_activity), then retry.",
        errors=[
            {"path": f"activities.{a.id}", "message": f"'{a.title}' is on {day}"}
            for a, day in outside
        ],
    )
