from datetime import datetime
from typing import Any

from pymongo import ASCENDING, ReturnDocument

from ..db import Database
from ..models import Ticket, TicketKind, TicketStatus
from .documents import from_document, to_document, version_filter


def _lapsed(now: datetime) -> dict[str, Any]:
    return {"status": "claimed", "claim.expiresAt": {"$lte": now}}


def _ticket(doc: dict[str, Any] | None, now: datetime) -> Ticket | None:
    if doc is None:
        return None
    data = from_document(doc)
    # A claim past its expiry is back in the queue; show it that way.
    claim = data.get("claim")
    if data["status"] == "claimed" and claim and claim["expiresAt"] <= now:
        data["status"], data["claim"] = "ready", None
    return Ticket.model_validate(data)


async def insert(db: Database, ticket: Ticket) -> None:
    await db.tickets.insert_one(to_document(ticket))


async def get(db: Database, ticket_id: str, now: datetime) -> Ticket | None:
    return _ticket(await db.tickets.find_one({"_id": ticket_id}), now)


async def list_tickets(
    db: Database,
    now: datetime,
    *,
    status: TicketStatus | None = None,
    kind: TicketKind | None = None,
    entity: str | None = None,
) -> list[Ticket]:
    query: dict[str, Any] = {}
    if status == "ready":
        query["$or"] = [{"status": "ready"}, _lapsed(now)]
    elif status == "claimed":
        query |= {"status": "claimed", "claim.expiresAt": {"$gt": now}}
    elif status is not None:
        query["status"] = status
    if kind is not None:
        query["kind"] = kind
    if entity is not None:
        query["context"] = {"$elemMatch": {"type": "entity", "id": entity}}
    cursor = db.tickets.find(query).sort([("createdAt", ASCENDING), ("_id", ASCENDING)])
    return [t async for doc in cursor if (t := _ticket(doc, now)) is not None]


async def update(
    db: Database,
    ticket_id: str,
    fields: dict[str, Any],
    now: datetime,
    *,
    if_match: list[datetime] | None = None,
    extra_filter: dict[str, Any] | None = None,
) -> Ticket | None:
    """``$set`` the given fields. Returns None if the ticket is missing or a condition failed."""
    doc = await db.tickets.find_one_and_update(
        {"_id": ticket_id, **version_filter(if_match), **(extra_filter or {})},
        {"$set": {**fields, "updatedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _ticket(doc, now)


async def claim(
    db: Database,
    ticket_id: str | None,
    by: str,
    now: datetime,
    expires_at: datetime,
    *,
    if_match: list[datetime] | None = None,
) -> Ticket | None:
    """Claim one ticket, or the oldest claimable one when ``ticket_id`` is None.

    A ticket is claimable if it is ready, its claim has lapsed, or ``by`` already holds it
    (which renews the claim). Returns None if nothing matched.
    """
    claimable: list[dict[str, Any]] = [{"status": "ready"}, _lapsed(now)]
    if ticket_id is not None:
        claimable.append({"status": "claimed", "claim.by": by})
    query: dict[str, Any] = {"$or": claimable, **version_filter(if_match)}
    if ticket_id is not None:
        query["_id"] = ticket_id
    doc = await db.tickets.find_one_and_update(
        query,
        {
            "$set": {
                "status": "claimed",
                "claim": {"by": by, "expiresAt": expires_at},
                "updatedAt": now,
            }
        },
        sort=[("createdAt", ASCENDING), ("_id", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )
    return _ticket(doc, now)
