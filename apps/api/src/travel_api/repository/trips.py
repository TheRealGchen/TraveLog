from datetime import datetime
from typing import Any

from pymongo import ReturnDocument

from ..db import Database
from ..models import TRAVELER_PALETTE, Trip
from .documents import from_document, to_document, version_filter


def _trip(doc: dict[str, Any] | None) -> Trip | None:
    return None if doc is None else Trip.model_validate(from_document(doc))


async def insert(db: Database, trip: Trip) -> None:
    await db.trips.insert_one(to_document(trip))


async def get(db: Database, trip_id: str) -> Trip | None:
    return _trip(await db.trips.find_one({"_id": trip_id}))


async def list_all(db: Database) -> list[Trip]:
    return [Trip.model_validate(from_document(doc)) async for doc in db.trips.find({})]


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


async def add_traveler(
    db: Database,
    trip_id: str,
    traveler_id: str,
    name: str,
    color: str | None,
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> Trip | None:
    """Append a traveler. Without a color, picks the first palette color not yet in use."""
    if color is not None:
        color_expr: Any = {"$literal": color}
    else:
        palette = {"$literal": TRAVELER_PALETTE}
        unused = {
            "$filter": {
                "input": palette,
                "cond": {"$not": [{"$in": ["$$this", "$travelers.color"]}]},
            }
        }
        cycled = {
            "$arrayElemAt": [palette, {"$mod": [{"$size": "$travelers"}, len(TRAVELER_PALETTE)]}]
        }
        color_expr = {"$ifNull": [{"$arrayElemAt": [unused, 0]}, cycled]}
    traveler = {"id": {"$literal": traveler_id}, "name": {"$literal": name}, "color": color_expr}
    doc = await db.trips.find_one_and_update(
        {"_id": trip_id, **version_filter(if_match)},
        [
            {
                "$set": {
                    "travelers": {"$concatArrays": ["$travelers", [traveler]]},
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
    doc = await db.trips.find_one_and_update(
        {"_id": trip_id, "travelers.id": traveler_id, **version_filter(if_match)},
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
