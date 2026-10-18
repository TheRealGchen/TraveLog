"""Shared field types and the base model configuration.

JSON uses camelCase; Python uses snake_case. Every timestamp is normalized to UTC on the way
in and serialized with a trailing ``Z`` on the way out.
"""

from datetime import UTC, date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
)
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = 1


class ApiModel(BaseModel):
    """Base for every request, response, and document model."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        field_title_generator=lambda name, _: name.replace("_", " ").capitalize(),
    )


def _parse_utc(value: Any) -> Any:
    """Parse ISO 8601 strings, rejecting any timestamp that has no offset."""
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(
                f"must be an ISO 8601 timestamp with an offset or 'Z', "
                f"for example 2027-04-03T10:00:00+09:00 (got {value!r})"
            ) from None
        value = parsed
    if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(
            f"must include a UTC offset or 'Z', for example 2027-04-03T10:00:00+09:00 "
            f"(got {value.isoformat()!r}, which has no offset)"
        )
    return value


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("must include a UTC offset or 'Z'")
    utc = value.astimezone(UTC)
    # MongoDB stores milliseconds, so truncate here to keep stored and returned values equal.
    return utc.replace(microsecond=utc.microsecond // 1000 * 1000)


def format_utc(value: datetime) -> str:
    """Serialize a datetime as UTC ISO 8601 with milliseconds and a trailing Z."""
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime,
    BeforeValidator(_parse_utc),
    AfterValidator(_to_utc),
    PlainSerializer(format_utc, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]
"""A timezone-aware timestamp, stored and returned in UTC."""


def _check_calendar_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{value!r} is not a real calendar date (expected YYYY-MM-DD)") from None
    return value


DateStr = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2027-04-03"]),
    AfterValidator(_check_calendar_date),
]
"""A calendar date (YYYY-MM-DD) with no time and no timezone."""


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError, ValueError:
        raise ValueError(
            f"{value!r} is not a known IANA timezone name (examples: 'Asia/Tokyo', "
            f"'Europe/Paris', 'America/New_York', 'UTC')"
        ) from None
    return value


TimezoneName = Annotated[str, Field(examples=["Asia/Tokyo"]), AfterValidator(_check_timezone)]
"""An IANA timezone name such as ``Asia/Tokyo``."""

HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$", examples=["#6366f1"])]


def utc_now() -> datetime:
    """The current time in UTC, truncated to milliseconds (MongoDB's precision)."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _reject_null(value: Any) -> Any:
    if value is None:
        raise ValueError("cannot be null; omit the field to leave it unchanged")
    return value


def _drop_null_from_schema(schema: dict[str, Any]) -> None:
    schema.pop("default", None)
    any_of = schema.pop("anyOf", None)
    if any_of is None:
        return
    rest = [s for s in any_of if s.get("type") != "null"]
    if len(rest) == 1:
        schema.update(rest[0])
    else:
        schema["anyOf"] = rest


NotNull = AfterValidator(_reject_null)
"""Marks an optional PATCH field that may be omitted but not sent as null."""


def patch_field(description: str, **kwargs: Any) -> Any:
    """A PATCH field that may be omitted but must not be null (use with ``NotNull``)."""
    return Field(
        default=None, description=description, json_schema_extra=_drop_null_from_schema, **kwargs
    )
