from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from ..briefs import render_brief
from ..db import Database
from ..errors import ApiError, not_found
from ..ids import new_id
from ..models import (
    CLAIM_TTL,
    SCHEMA_VERSION,
    ApiServerContext,
    ClaimTicketRequest,
    CreateTicketRequest,
    ResolveTicketRequest,
    Ticket,
    TicketKind,
    TicketList,
    TicketStatus,
    UpdateTicketRequest,
    format_utc,
    utc_now,
)
from ..repository import tickets as ticket_repo
from .deps import ETAG_HEADER, IfMatch, etag, get_db, parse_if_match, problems, stale

router = APIRouter(prefix="/tickets", tags=["Feedback"])

Db = Annotated[Database, Depends(get_db)]
TicketId = Annotated[
    str, Path(alias="ticketId", description="Ticket ID (`tkt_...`).", examples=["tkt_01J..."])
]


class MarkdownResponse(PlainTextResponse):
    media_type = "text/markdown"


def _respond(ticket: Ticket, response: Response) -> Ticket:
    response.headers["ETag"] = etag(ticket.updated_at)
    return ticket


def _not_found(ticket_id: str) -> ApiError:
    return not_found(f"Ticket {ticket_id} not found. List tickets with GET /v1/tickets.")


async def _load(db: Database, ticket_id: str) -> Ticket:
    ticket = await ticket_repo.get(db, ticket_id, utc_now())
    if ticket is None:
        raise _not_found(ticket_id)
    return ticket


def _not_claimable(ticket: Ticket) -> ApiError:
    if ticket.status == "new":
        reason = "is new; a person must approve it with update_ticket {status: ready} first"
    elif ticket.status == "claimed" and ticket.claim is not None:
        reason = (
            f"is claimed by {ticket.claim.by} until {format_utc(ticket.claim.expires_at)}; "
            "it can be claimed after that"
        )
    else:
        reason = f"is already {ticket.status}; reopen it with update_ticket {{status: ready}}"
    return ApiError(409, f"Ticket {ticket.id} {reason}.")


async def _write_failed(
    db: Database, ticket_id: str, if_match: list[datetime] | None, conflict: ApiError
) -> ApiError:
    """Explain why a conditional write matched nothing: missing ticket, stale ETag, or state."""
    current = await ticket_repo.get(db, ticket_id, utc_now())
    if current is None:
        return _not_found(ticket_id)
    if if_match is not None and current.updated_at not in if_match:
        return stale(etag(current.updated_at), current)
    return conflict


@router.post(
    "",
    operation_id="create_ticket",
    summary="File feedback",
    description=(
        "Files a ticket with the person's feedback and optional context items describing where "
        "it happened (page, element, recent errors, failed API calls, records by ID). Context is "
        "stored as sent and never checked against other data. The API adds an `api.server` item. "
        "New tickets have status `new` and must be approved (`update_ticket` with "
        "`status: ready`) before they can be claimed."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=Ticket,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 422)},
)
async def create_ticket(
    body: CreateTicketRequest, request: Request, response: Response, db: Db
) -> Ticket:
    now = utc_now()
    server = ApiServerContext(type="api.server", build=request.app.state.settings.build)
    ticket = Ticket(
        id=new_id("tkt"),
        schema_version=SCHEMA_VERSION,
        body=body.body,
        kind=body.kind,
        context=[*body.context, server],
        status="new",
        claim=None,
        resolution=None,
        created_at=now,
        updated_at=now,
    )
    await ticket_repo.insert(db, ticket)
    response.headers["Location"] = f"/v1/tickets/{ticket.id}"
    return _respond(ticket, response)


@router.get(
    "",
    operation_id="list_tickets",
    summary="List tickets",
    description="Tickets, oldest first, optionally filtered.",
    response_model=TicketList,
    responses=problems(401, 422),
)
async def list_tickets(
    db: Db,
    status_: Annotated[
        TicketStatus | None,
        Query(alias="status", description="Only tickets with this status."),
    ] = None,
    kind: Annotated[TicketKind | None, Query(description="Only tickets of this kind.")] = None,
    entity: Annotated[
        str | None,
        Query(description="Only tickets with an `entity` context item for this record ID."),
    ] = None,
) -> TicketList:
    tickets = await ticket_repo.list_tickets(
        db, utc_now(), status=status_, kind=kind, entity=entity
    )
    return TicketList(tickets=tickets)


@router.post(
    "/claim",
    operation_id="claim_ticket",
    summary="Claim a ticket to work on",
    description=(
        f"Claims a ticket for {int(CLAIM_TTL.total_seconds() // 3600)} hours. Without `id`, "
        "claims the oldest `ready` ticket, or returns 204 if there is none. With `id`, claims "
        "that ticket; 409 if it isn't ready or someone else holds it. Claiming a ticket you "
        "already hold renews the claim. A lapsed claim returns the ticket to `ready`."
    ),
    response_model=Ticket,
    responses={
        200: {"headers": ETAG_HEADER},
        204: {"description": "No ticket is ready to claim."},
        **problems(401, 404, 409, 412, 422),
    },
)
async def claim_ticket(
    body: ClaimTicketRequest, response: Response, db: Db, if_match: IfMatch = None
) -> Ticket | Response:
    versions = parse_if_match(if_match)
    now = utc_now()
    claimed = await ticket_repo.claim(db, body.id, body.by, now, now + CLAIM_TTL, if_match=versions)
    if claimed is not None:
        return _respond(claimed, response)
    if body.id is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    current = await _load(db, body.id)
    raise await _write_failed(db, body.id, versions, _not_claimable(current))


@router.get(
    "/{ticketId}",
    operation_id="get_ticket",
    summary="Get a ticket",
    response_model=Ticket,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404)},
)
async def get_ticket(ticket_id: TicketId, response: Response, db: Db) -> Ticket:
    return _respond(await _load(db, ticket_id), response)


@router.get(
    "/{ticketId}/brief",
    operation_id="get_ticket_brief",
    summary="Get a ticket as a Markdown brief",
    description=(
        "The ticket rendered as Markdown for an agent to work from: the feedback and context "
        "(fenced and marked as untrusted input), grouped into Frontend, Backend, and Data, and "
        "the calls for claiming and resolving it."
    ),
    response_class=MarkdownResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404)},
)
async def get_ticket_brief(ticket_id: TicketId, db: Db) -> MarkdownResponse:
    ticket = await _load(db, ticket_id)
    return MarkdownResponse(render_brief(ticket), headers={"ETag": etag(ticket.updated_at)})


@router.patch(
    "/{ticketId}",
    operation_id="update_ticket",
    summary="Triage a ticket",
    description=(
        "Changes `kind`, or `status`: `ready` approves the ticket for work, and also releases a "
        "claim or reopens a closed ticket (clearing its claim and resolution); `new` takes it "
        "back out of the queue. Returns the updated ticket."
    ),
    response_model=Ticket,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def update_ticket(
    ticket_id: TicketId,
    body: UpdateTicketRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> Ticket:
    versions = parse_if_match(if_match)
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields:
        fields |= {"claim": None, "resolution": None}
    updated = await ticket_repo.update(db, ticket_id, fields, utc_now(), if_match=versions)
    if updated is None:
        raise await _write_failed(db, ticket_id, versions, _not_found(ticket_id))
    return _respond(updated, response)


@router.post(
    "/{ticketId}/resolve",
    operation_id="resolve_ticket",
    summary="Close a ticket",
    description=(
        "Closes the ticket as `resolved` or `wontfix` with a summary and optional link (e.g. "
        "the pull request), and clears any claim. 409 if it is already closed."
    ),
    response_model=Ticket,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 409, 412, 422)},
)
async def resolve_ticket(
    ticket_id: TicketId,
    body: ResolveTicketRequest,
    response: Response,
    db: Db,
    if_match: IfMatch = None,
) -> Ticket:
    versions = parse_if_match(if_match)
    now = utc_now()
    updated = await ticket_repo.update(
        db,
        ticket_id,
        {
            "status": body.status,
            "claim": None,
            "resolution": {"summary": body.summary, "url": body.url},
        },
        now,
        if_match=versions,
        extra_filter={"status": {"$in": ["new", "ready", "claimed"]}},
    )
    if updated is None:
        current = await _load(db, ticket_id)
        raise await _write_failed(db, ticket_id, versions, _not_claimable(current))
    return _respond(updated, response)
