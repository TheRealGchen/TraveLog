from typing import Any

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

Database = AsyncDatabase[dict[str, Any]]


def connect(uri: str) -> AsyncMongoClient[dict[str, Any]]:
    # tz_aware=True makes PyMongo return datetimes as UTC-aware values.
    return AsyncMongoClient(uri, tz_aware=True)


async def create_indexes(db: Database) -> None:
    await db.trips.create_index([("ownerId", ASCENDING), ("startDate", ASCENDING)])
    await db.days.create_index([("tripId", ASCENDING), ("date", ASCENDING)])
    await db.days.create_index([("activities.id", ASCENDING)])
