from datetime import datetime
from typing import Any

from pymongo import ReturnDocument

from ..db import Database
from ..models import Activity
from .documents import from_document, to_document, version_filter


def _activity(doc: dict[str, Any] | None) -> Activity | None:
    return None if doc is None else Activity.model_validate(from_document(doc))


async def insert(db: Database, activity: Activity) -> None:
    await db.activities.insert_one(to_document(activity))


async def get(db: Database, trip_id: str, activity_id: str) -> Activity | None:
    return _activity(await db.activities.find_one({"_id": activity_id, "tripId": trip_id}))


async def find(db: Database, trip_id: str, query: dict[str, Any] | None = None) -> list[Activity]:
    cursor = db.activities.find({"tripId": trip_id, **(query or {})})
    return [Activity.model_validate(from_document(doc)) async for doc in cursor]


async def update(
    db: Database,
    trip_id: str,
    activity_id: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
    status_expr: Any = None,
) -> Activity | None:
    """Set fields in one pipeline update. ``status_expr`` may compute status from the stored one.

    Values are wrapped in ``$literal`` so user text starting with ``$`` is never an expression.
    """
    stage: dict[str, Any] = {k: {"$literal": v} for k, v in fields.items()}
    if status_expr is not None:
        stage["status"] = status_expr
    stage["updatedAt"] = {"$literal": now}
    doc = await db.activities.find_one_and_update(
        {"_id": activity_id, "tripId": trip_id, **version_filter(if_match)},
        [{"$set": stage}],
        return_document=ReturnDocument.AFTER,
    )
    return _activity(doc)


async def delete(
    db: Database, trip_id: str, activity_id: str, *, if_match: list[datetime] | None = None
) -> bool:
    result = await db.activities.delete_one(
        {"_id": activity_id, "tripId": trip_id, **version_filter(if_match)}
    )
    return result.deleted_count == 1


async def delete_for_trip(db: Database, trip_id: str) -> None:
    await db.activities.delete_many({"tripId": trip_id})


async def pull_traveler(db: Database, trip_id: str, traveler_id: str, now: datetime) -> None:
    await db.activities.update_many(
        {"tripId": trip_id, "travelerIds": traveler_id},
        {"$pull": {"travelerIds": traveler_id}, "$set": {"updatedAt": now}},
    )


async def recompute_dates(db: Database, trip_id: str, timezone: str, now: datetime) -> None:
    """Re-derive ``schedule.date`` of every timed activity in ``timezone``; instants are kept."""
    await db.activities.update_many(
        {"tripId": trip_id, "schedule.startAt": {"$ne": None}},
        [
            {
                "$set": {
                    "schedule.date": {
                        "$dateToString": {
                            "date": "$schedule.startAt",
                            "format": "%Y-%m-%d",
                            "timezone": timezone,
                        }
                    },
                    "updatedAt": {"$literal": now},
                }
            }
        ],
    )
