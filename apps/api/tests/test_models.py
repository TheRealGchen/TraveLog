from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from travel_api.models import (
    AddActivityRequest,
    CreateTripRequest,
    MoveActivityRequest,
    ScheduleInput,
    UpdateActivityRequest,
    UpdateTripRequest,
)


def messages(exc: ValidationError) -> str:
    return " | ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())


# Dates


def test_trip_dates_accept_calendar_dates() -> None:
    trip = CreateTripRequest.model_validate(
        {"name": "Japan", "startDate": "2027-04-02", "endDate": "2027-04-14"}
    )
    assert trip.start_date == "2027-04-02"
    assert trip.timezone == "UTC"


@pytest.mark.parametrize("bad", ["2027-4-2", "2027-04-02T00:00:00Z", "04/02/2027", "2027-02-30"])
def test_trip_dates_reject_non_dates(bad: str) -> None:
    with pytest.raises(ValidationError) as exc:
        CreateTripRequest.model_validate({"name": "x", "startDate": bad, "endDate": "2027-04-14"})
    assert "startDate" in messages(exc.value)


def test_end_date_before_start_date_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        CreateTripRequest.model_validate(
            {"name": "x", "startDate": "2027-04-14", "endDate": "2027-04-02"}
        )
    assert "endDate must be on or after startDate (got 2027-04-14 and 2027-04-02)" in messages(
        exc.value
    )


def test_single_day_trip_is_allowed() -> None:
    CreateTripRequest.model_validate(
        {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-02"}
    )


# UTC timestamps


def test_offset_timestamp_is_normalized_to_utc() -> None:
    s = ScheduleInput.model_validate({"startAt": "2027-04-03T10:00:00+09:00"})
    assert s.start_at == datetime(2027, 4, 3, 1, 0, tzinfo=UTC)
    assert s.start_at is not None and s.start_at.utcoffset() is not None
    assert s.model_dump(mode="json")["startAt"] == "2027-04-03T01:00:00.000Z"


def test_z_timestamp_is_accepted() -> None:
    s = ScheduleInput.model_validate({"startAt": "2027-04-03T01:00:00Z"})
    assert s.model_dump(mode="json")["startAt"] == "2027-04-03T01:00:00.000Z"


def test_timestamp_without_offset_is_rejected_with_explanation() -> None:
    with pytest.raises(ValidationError) as exc:
        ScheduleInput.model_validate({"startAt": "2027-04-03T10:00:00"})
    msg = messages(exc.value)
    assert "startAt" in msg
    assert "must include a UTC offset or 'Z'" in msg


def test_timestamps_are_truncated_to_milliseconds() -> None:
    s = ScheduleInput.model_validate({"startAt": "2027-04-03T01:00:00.123456Z"})
    assert s.start_at is not None and s.start_at.microsecond == 123000


def test_end_at_must_be_after_start_at() -> None:
    with pytest.raises(ValidationError) as exc:
        ScheduleInput.model_validate(
            {"startAt": "2027-04-03T02:00:00Z", "endAt": "2027-04-03T01:00:00Z"}
        )
    assert (
        "endAt must be after startAt (got 2027-04-03T02:00:00.000Z and 2027-04-03T01:00:00.000Z)"
        in messages(exc.value)
    )


def test_end_at_requires_start_at() -> None:
    with pytest.raises(ValidationError) as exc:
        ScheduleInput.model_validate({"date": "2027-04-03", "endAt": "2027-04-03T01:00:00Z"})
    assert "endAt requires startAt" in messages(exc.value)


def test_move_cannot_set_times_while_unscheduling() -> None:
    with pytest.raises(ValidationError):
        MoveActivityRequest.model_validate({"date": None, "startAt": "2027-04-03T01:00:00Z"})


def test_move_requires_date_key() -> None:
    with pytest.raises(ValidationError) as exc:
        MoveActivityRequest.model_validate({})
    assert "date" in messages(exc.value)


# Timezones


@pytest.mark.parametrize("tz", ["Asia/Tokyo", "America/New_York", "UTC", "Europe/Paris"])
def test_valid_timezones(tz: str) -> None:
    trip = CreateTripRequest.model_validate(
        {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-03", "timezone": tz}
    )
    assert trip.timezone == tz


@pytest.mark.parametrize("tz", ["Mars/Olympus", "+09:00", "JST9", "", "../etc/passwd"])
def test_invalid_timezones(tz: str) -> None:
    with pytest.raises(ValidationError) as exc:
        CreateTripRequest.model_validate(
            {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-03", "timezone": tz}
        )
    assert "timezone" in messages(exc.value)


# null versus omitted


def test_patch_omitted_fields_are_not_dumped() -> None:
    assert UpdateTripRequest.model_validate({}).model_dump(exclude_unset=True) == {}
    assert UpdateActivityRequest.model_validate({"title": "x"}).model_dump(exclude_unset=True) == {
        "title": "x"
    }


def test_patch_explicit_null_is_kept_for_nullable_fields() -> None:
    patch = UpdateActivityRequest.model_validate({"schedule": None, "notes": None})
    assert patch.model_dump(exclude_unset=True) == {"schedule": None, "notes": None}
    trip_patch = UpdateTripRequest.model_validate({"destination": None})
    assert trip_patch.model_dump(exclude_unset=True) == {"destination": None}


@pytest.mark.parametrize("field", ["title", "status", "travelerIds"])
def test_patch_null_is_rejected_for_required_fields(field: str) -> None:
    with pytest.raises(ValidationError) as exc:
        UpdateActivityRequest.model_validate({field: None})
    assert "cannot be null" in messages(exc.value)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        AddActivityRequest.model_validate({"title": "x", "tittle": "y"})
    assert "tittle" in messages(exc.value)
