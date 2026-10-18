from datetime import datetime
from typing import Any

from pymongo import ReturnDocument

from ..db import Database
from ..models import TRAVELER_PALETTE, Trip
from .documents import from_document, to_document, version_filter


def _trip(doc: dict[str, Any] | None) -> Trip | None:
    if doc is None:
        return None
    data = from_document(doc)
    for traveler in data.get("travelers", []):
        # Travelers stored before email and passport existed read as null (migrate on read).
        traveler.setdefault("email", None)
        traveler.setdefault("passportNumber", None)
    return Trip.model_validate(data)


async def insert(db: Database, trip: Trip) -> None:
    await db.trips.insert_one(to_document(trip))


async def get(db: Database, trip_id: str) -> Trip | None:
    return _trip(await db.trips.find_one({"_id": trip_id}))


async def list_all(db: Database) -> list[Trip]:
    return [trip async for doc in db.trips.find({}) if (trip := _trip(doc)) is not None]


async def update(
    db: Database,
    trip_id: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
    extra_filter: dict[str, Any] | None = None,
) -> Trip | None:
    """``$set`` the given fields. Returns None if the trip is missing or a condition failed."""
    doc = await db.trips.find_one_and_update(
        {"_id": trip_id, **version_filter(if_match), **(extra_filter or {})},
        {"$set": {**fields, "updatedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _trip(doc)


async def delete(db: Database, trip_id: str) -> bool:
    result = await db.trips.delete_one({"_id": trip_id})
    return result.deleted_count == 1


def _no_duplicates(emails: list[str], passports: list[str], *, except_id: str | None = None):
    """Filter clauses that match only if no (other) traveler already uses these values."""
    clauses: list[dict[str, Any]] = []
    for field, values in (("email", emails), ("passportNumber", passports)):
        if not values:
            continue
        match: dict[str, Any] = {field: {"$in": values}}
        if except_id is not None:
            match["id"] = {"$ne": except_id}
        clauses.append({"travelers": {"$not": {"$elemMatch": match}}})
    return {"$and": clauses} if clauses else {}


async def add_travelers(
    db: Database,
    trip_id: str,
    travelers: list[dict[str, Any]],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> Trip | None:
    """Append travelers in one atomic update.

    Each traveler without a color gets the first palette color not used by the trip or by an
    earlier traveler in the batch (cycling once all are used). The write applies only if no
    existing traveler shares an email or passport number with the new ones; otherwise None.
    """
    palette = {"$literal": TRAVELER_PALETTE}
    unused = {
        "$filter": {
            "input": palette,
            "as": "c",
            "cond": {"$not": [{"$in": ["$$c", "$$value.color"]}]},
        }
    }
    cycled = {"$arrayElemAt": [palette, {"$mod": [{"$size": "$$value"}, len(TRAVELER_PALETTE)]}]}
    next_color = {"$ifNull": [{"$arrayElemAt": [unused, 0]}, cycled]}
    new = [{k: {"$literal": v} for k, v in t.items()} for t in travelers]
    emails = [t["email"] for t in travelers if t.get("email")]
    passports = [t["passportNumber"] for t in travelers if t.get("passportNumber")]
    doc = await db.trips.find_one_and_update(
        {"_id": trip_id, **version_filter(if_match), **_no_duplicates(emails, passports)},
        [
            {
                "$set": {
                    "travelers": {
                        "$reduce": {
                            "input": new,
                            "initialValue": "$travelers",
                            "in": {
                                "$concatArrays": [
                                    "$$value",
                                    [
                                        {
                                            "$mergeObjects": [
                                                "$$this",
                                                {
                                                    "color": {
                                                        "$ifNull": ["$$this.color", next_color]
                                                    }
                                                },
                                            ]
                                        }
                                    ],
                                ]
                            },
                        }
                    },
                    "updatedAt": {"$literal": now},
                }
            }
        ],
        return_document=ReturnDocument.AFTER,
    )
    return _trip(doc)


async def update_traveler(
    db: Database,
    trip_id: str,
    traveler_id: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> Trip | None:
    emails = [fields["email"]] if fields.get("email") else []
    passports = [fields["passportNumber"]] if fields.get("passportNumber") else []
    doc = await db.trips.find_one_and_update(
        {
            "_id": trip_id,
            "travelers.id": traveler_id,
            **version_filter(if_match),
            **_no_duplicates(emails, passports, except_id=traveler_id),
        },
        {"$set": {**{f"travelers.$[t].{k}": v for k, v in fields.items()}, "updatedAt": now}},
        array_filters=[{"t.id": traveler_id}],
        return_document=ReturnDocument.AFTER,
    )
    return _trip(doc)


async def remove_traveler(
    db: Database,
    trip_id: str,
    traveler_id: str,
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> Trip | None:
    doc = await db.trips.find_one_and_update(
        {"_id": trip_id, "travelers.id": traveler_id, **version_filter(if_match)},
        {"$pull": {"travelers": {"id": traveler_id}}, "$set": {"updatedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _trip(doc)
