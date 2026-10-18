"""Date and time rules: trip countdowns, trip days, activity times, and moving activities."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .errors import ApiError, invalid
from .models import (
    ActivityDocument,
    ActivityTime,
    ActivityTimeInput,
    DayDocument,
    MoveActivityRequest,
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


def day_number(trip: Trip, day: str) -> int:
    return (date.fromisoformat(day) - date.fromisoformat(trip.start_date)).days + 1


def in_trip(trip: Trip, day: str) -> bool:
    return trip.start_date <= day <= trip.end_date


def check_day_in_trip(trip: Trip, day: str, path: str) -> None:
    if not in_trip(trip, day):
        raise invalid(
            path,
            f"{day} is outside the trip ({trip.start_date} to {trip.end_date}); pick a day in "
            "that range",
        )


def resolve_time(
    value: ActivityTimeInput | None, day: str, trip: Trip, path: str
) -> ActivityTime | None:
    """Validate requested times for an activity on ``day``: startAt must fall on that day."""
    if value is None:
        return None
    on = local_date(value.start_at, trip.timezone)
    if on != day:
        raise invalid(
            f"{path}.startAt",
            f"startAt {format_utc(value.start_at)} is on {on} in {trip.timezone}, but this "
            f"activity is on {day}. Pick a time on {day}, or use move_activity to change its day",
        )
    return ActivityTime(start_at=value.start_at, end_at=value.end_at)


def _shift_to_day(instant: datetime, timezone: str, day_offset: int) -> datetime:
    """Move ``instant`` by whole calendar days, keeping its wall-clock time in ``timezone``."""
    tz = ZoneInfo(timezone)
    local = instant.astimezone(tz)
    moved = datetime.combine(local.date() + timedelta(days=day_offset), local.time(), tzinfo=tz)
    return moved.astimezone(UTC)


def move_time(
    current: ActivityTime | None, from_day: str, request: MoveActivityRequest, trip: Trip
) -> ActivityTime | None:
    """The activity's times after a ``move_activity`` request to ``request.date``."""
    sent = request.model_fields_set
    if request.start_at is not None:
        end_at = request.end_at
        if "end_at" not in sent and current is not None and current.end_at is not None:
            end_at = request.start_at + (current.end_at - current.start_at)
        target = ActivityTimeInput(start_at=request.start_at, end_at=end_at)
        return resolve_time(target, request.date, trip, "body")
    if current is None:
        return None
    # Keep each time of day on the new day, in the trip's timezone.
    offset = (date.fromisoformat(request.date) - date.fromisoformat(from_day)).days
    start_at = _shift_to_day(current.start_at, trip.timezone, offset)
    end_at = _shift_to_day(current.end_at, trip.timezone, offset) if current.end_at else None
    if "end_at" in sent:
        end_at = None
    return ActivityTime(start_at=start_at, end_at=end_at)


def sort_key_in_day(activity: ActivityDocument) -> tuple[bool, datetime, datetime]:
    start = activity.time.start_at if activity.time else None
    return (start is None, start or activity.created_at, activity.created_at)


def day_has_content(day: DayDocument) -> bool:
    return bool(day.lodging or day.start_location or day.activities)


def days_conflict(days: list[DayDocument], start: str, end: str) -> ApiError:
    """409 for days that would fall outside a new trip range but still hold plans."""
    listed = ", ".join(
        f"{d.date} ({len(d.activities)} activit{'y' if len(d.activities) == 1 else 'ies'}"
        f"{', lodging' if d.lodging else ''}{', start location' if d.start_location else ''})"
        for d in days[:10]
    )
    more = f" and {len(days) - 10} more" if len(days) > 10 else ""
    return ApiError(
        409,
        f"The new dates ({start} to {end}) would drop {len(days)} day"
        f"{' that still has' if len(days) == 1 else 's that still have'} plans: {listed}{more}. "
        "Move their activities (move_activity) and clear lodging and start location "
        "(update_day) first.",
        errors=[{"path": f"days.{d.date}", "message": "has plans"} for d in days],
    )


def timezone_conflicts(days: Iterable[DayDocument], timezone: str) -> list[tuple[str, str, str]]:
    """Timed activities whose start would land on another day in ``timezone``."""
    conflicts = []
    for day in days:
        for activity in day.activities:
            if activity.time is not None:
                on = local_date(activity.time.start_at, timezone)
                if on != day.date:
                    conflicts.append((activity.id, activity.title, on))
    return conflicts


def timezone_conflict(conflicts: list[tuple[str, str, str]], timezone: str) -> ApiError:
    listed = ", ".join(f"{aid} '{title}' (would be on {on})" for aid, title, on in conflicts[:10])
    return ApiError(
        409,
        f"In {timezone}, {len(conflicts)} timed activit"
        f"{'y' if len(conflicts) == 1 else 'ies'} would start on a different day: {listed}. "
        "Times are kept as instants (UTC). Move those activities (move_activity) or change "
        "their times first.",
        errors=[
            {"path": f"activities.{aid}", "message": f"'{title}' would start on {on}"}
            for aid, title, on in conflicts
        ],
    )
