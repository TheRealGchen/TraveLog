"""The `days` collection: one document per trip day, holding that day's activities."""

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError

from ..db import Database
from ..models import SCHEMA_VERSION, ActivityDocument, DayDocument
from .documents import from_document, to_document, version_filter


def day_id(trip_id: str, date: str) -> str:
    return f"{trip_id}_{date}"


def _day(doc: dict[str, Any] | None) -> DayDocument | None:
    return None if doc is None else DayDocument.model_validate(from_document(doc))


async def insert_missing(db: Database, trip_id: str, dates: list[str], now: datetime) -> None:
    """Create empty day documents for ``dates``; days that already exist are left alone."""
    if not dates:
        return
    docs = [
        to_document(
            DayDocument(
                id=day_id(trip_id, d),
                schema_version=SCHEMA_VERSION,
                trip_id=trip_id,
                date=d,
                lodging=None,
                start_location=None,
                activities=[],
                created_at=now,
                updated_at=now,
            )
        )
        for d in dates
    ]
    try:
        await db.days.insert_many(docs, ordered=False)
    except BulkWriteError as exc:
        # Duplicate keys mean a concurrent request created the same day: that's fine.
        if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
            raise


async def get(db: Database, trip_id: str, date: str) -> DayDocument | None:
    return _day(await db.days.find_one({"_id": day_id(trip_id, date)}))


async def list_for_trip(db: Database, trip_id: str) -> list[DayDocument]:
    cursor = db.days.find({"tripId": trip_id}).sort("date", 1)
    return [DayDocument.model_validate(from_document(doc)) async for doc in cursor]


async def update(
    db: Database,
    trip_id: str,
    date: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> DayDocument | None:
    doc = await db.days.find_one_and_update(
        {"_id": day_id(trip_id, date), **version_filter(if_match)},
        {"$set": {**fields, "updatedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _day(doc)


async def push_activity(
    db: Database, trip_id: str, date: str, activity: ActivityDocument, now: datetime
) -> DayDocument | None:
    """Append an activity to a day (no-op if an activity with that ID is already there)."""
    doc = await db.days.find_one_and_update(
        {"_id": day_id(trip_id, date), "activities.id": {"$ne": activity.id}},
        {"$push": {"activities": activity.model_dump()}, "$set": {"updatedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _day(doc)


async def find_activity(
    db: Database, trip_id: str, activity_id: str
) -> tuple[DayDocument, ActivityDocument] | None:
    day = _day(await db.days.find_one({"tripId": trip_id, "activities.id": activity_id}))
    if day is None:
        return None
    activity = next(a for a in day.activities if a.id == activity_id)
    return day, activity


def _activity_version(activity_id: str, if_match: list[datetime] | None) -> dict[str, Any]:
    if if_match is None:
        return {"activities.id": activity_id}
    return {"activities": {"$elemMatch": {"id": activity_id, "updatedAt": {"$in": if_match}}}}


async def update_activity(
    db: Database,
    trip_id: str,
    activity_id: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    date: str | None = None,
    if_match: list[datetime] | None = None,
) -> DayDocument | None:
    """``$set`` fields of one embedded activity (located with an array filter).

    With ``date``, the write applies only if the activity is still on that day.
    """
    sets = {f"activities.$[a].{k}": v for k, v in fields.items()}
    query: dict[str, Any] = {"tripId": trip_id, **_activity_version(activity_id, if_match)}
    if date is not None:
        query["_id"] = day_id(trip_id, date)
    doc = await db.days.find_one_and_update(
        query,
        {"$set": {**sets, "activities.$[a].updatedAt": now, "updatedAt": now}},
        array_filters=[{"a.id": activity_id}],
        return_document=ReturnDocument.AFTER,
    )
    return _day(doc)


async def pull_activity(
    db: Database,
    trip_id: str,
    activity_id: str,
    now: datetime,
    *,
    date: str | None = None,
    if_match: list[datetime] | None = None,
) -> bool:
    query: dict[str, Any] = {"tripId": trip_id, **_activity_version(activity_id, if_match)}
    if date is not None:
        query["_id"] = day_id(trip_id, date)
    result = await db.days.update_one(
        query,
        {"$pull": {"activities": {"id": activity_id}}, "$set": {"updatedAt": now}},
    )
    return result.modified_count == 1


async def delete_for_trip(db: Database, trip_id: str) -> None:
    await db.days.delete_many({"tripId": trip_id})


def _outside(start: str, end: str) -> dict[str, Any]:
    return {"$or": [{"date": {"$lt": start}}, {"date": {"$gt": end}}]}


async def find_outside(db: Database, trip_id: str, start: str, end: str) -> list[DayDocument]:
    cursor = db.days.find({"tripId": trip_id, **_outside(start, end)}).sort("date", 1)
    return [DayDocument.model_validate(from_document(doc)) async for doc in cursor]


async def delete_empty_outside(db: Database, trip_id: str, start: str, end: str) -> None:
    await db.days.delete_many(
        {
            "tripId": trip_id,
            **_outside(start, end),
            "lodging": None,
            "startLocation": None,
            "activities": {"$size": 0},
        }
    )


async def pull_traveler(db: Database, trip_id: str, traveler_id: str, now: datetime) -> None:
    await db.days.update_many(
        {"tripId": trip_id, "activities.travelerIds": traveler_id},
        {
            "$pull": {"activities.$[a].travelerIds": traveler_id},
            "$set": {"activities.$[a].updatedAt": now, "updatedAt": now},
        },
        array_filters=[{"a.travelerIds": traveler_id}],
    )
