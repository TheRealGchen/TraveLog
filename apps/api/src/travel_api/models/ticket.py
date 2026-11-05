"""Feedback tickets: what a person said, plus typed context from the web app and the API.

The ticket service never reads trips or other records. Context items are stored as sent (after
shape and size checks), so the web app and the API can each describe what only they know.
"""

from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .common import ApiModel, NotNull, UtcDatetime, patch_field
from .link import WebUrl

TicketKind = Literal["bug", "idea", "question", "other"]
TicketStatus = Literal["new", "ready", "claimed", "resolved", "wontfix"]
MAX_CONTEXT_ITEMS = 20
CLAIM_TTL = timedelta(hours=2)


def _text(max_length: int, min_length: int = 1) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


class WebPageContext(ApiModel):
    """The screen the person was on."""

    type: Literal["web.page"]
    route: Annotated[str, _text(300)] = Field(
        description="Route pattern with `[param]` placeholders.",
        examples=["/trips/[tripId]/days/[date]"],
    )
    path: Annotated[str, _text(2048)] = Field(
        description="The actual path, e.g. `/trips/trip_01J.../days/2027-04-03`."
    )
    viewport: str | None = Field(
        default=None,
        pattern=r"^\d{1,5}x\d{1,5}$",
        description="Viewport size as `WIDTHxHEIGHT` in CSS pixels.",
        examples=["390x844"],
    )
    theme: Literal["light", "dark"] | None = Field(default=None, description="Color theme in use.")
    build: Annotated[str, _text(64)] | None = Field(
        default=None, description="Version (git commit) of the web app build."
    )


class WebElementContext(ApiModel):
    """The part of the screen the person pointed at."""

    type: Literal["web.element"]
    component: Annotated[str, _text(100)] = Field(
        description="Component name, e.g. `ActivityCard`.", examples=["ActivityCard"]
    )
    label: Annotated[str, _text(200)] | None = Field(
        default=None, description="What it showed, e.g. the activity's title."
    )


class WebErrorContext(ApiModel):
    """An error the web app hit shortly before the ticket was filed."""

    type: Literal["web.error"]
    message: Annotated[str, _text(1000)] = Field(description="The error message.")
    stack: Annotated[str, _text(3000)] | None = Field(default=None, description="Stack trace.")


class ApiRequestContext(ApiModel):
    """An API call that failed shortly before the ticket was filed. Never includes bodies."""

    type: Literal["api.request"]
    operation_id: Annotated[str, _text(100)] = Field(
        description="The operation's `operationId`, e.g. `update_activity`."
    )
    status: int = Field(ge=100, le=599, description="HTTP status code of the response.")
    problem_type: Annotated[str, _text(200)] | None = Field(
        default=None, description="`type` of the problem+json response, if any."
    )
    error_paths: list[Annotated[str, _text(200)]] = Field(
        default_factory=list,
        max_length=20,
        description="`path` of each validation error, e.g. `body.time`.",
    )


class ApiServerContext(ApiModel):
    """Added by the API when the ticket is created; clients cannot send it."""

    type: Literal["api.server"]
    build: str | None = Field(description="Version (git commit) of the API, or null if unknown.")


class EntityContext(ApiModel):
    """A record the ticket is about, by ID. The ID prefix gives its type (`trip_`, `act_`, ...)."""

    type: Literal["entity"]
    id: str = Field(
        pattern=r"^[a-z]{2,10}_[0-9A-Za-z]{1,40}$",
        description="The record's ID. It is not checked; the record may since have been deleted.",
        examples=["act_01J..."],
    )
    etag: Annotated[str, _text(64)] | None = Field(
        default=None,
        description="The record's ETag when the person saw it, to tell whether it changed since.",
    )


ContextInput = Annotated[
    WebPageContext | WebElementContext | WebErrorContext | ApiRequestContext | EntityContext,
    Field(discriminator="type"),
]
"""A context item a client may send."""

ContextItem = Annotated[
    WebPageContext
    | WebElementContext
    | WebErrorContext
    | ApiRequestContext
    | ApiServerContext
    | EntityContext,
    Field(discriminator="type"),
]
"""A stored context item, including the ones the API adds."""


class Claim(ApiModel):
    """Who is working on a ticket, and until when."""

    by: str = Field(description="Who claimed it, e.g. an agent session name.")
    expires_at: UtcDatetime = Field(
        description="When the claim lapses (UTC). Claim again before then to keep it."
    )


class Resolution(ApiModel):
    """How a ticket was closed."""

    summary: str = Field(description="What was done, or why nothing will be.")
    url: str | None = Field(description="Link to the change (e.g. a pull request), or null.")


class Ticket(ApiModel):
    """A piece of feedback, with context, queued for a person or an agent to work on."""

    id: str = Field(description="Ticket ID, prefixed with `tkt_`.", examples=["tkt_01J..."])
    schema_version: int = Field(description="Version of the stored document shape.")
    body: str = Field(description="The feedback, as written.")
    kind: TicketKind = Field(description="`bug`, `idea`, `question`, or `other`.")
    context: list[ContextItem] = Field(description="What the web app and the API knew.")
    status: TicketStatus = Field(
        description=(
            "`new` (filed), `ready` (approved for work), `claimed` (being worked on), "
            "`resolved`, or `wontfix`."
        )
    )
    claim: Claim | None = Field(description="The current claim while `claimed`, else null.")
    resolution: Resolution | None = Field(
        description="How it was closed, once `resolved` or `wontfix`; else null."
    )
    created_at: UtcDatetime = Field(description="When the ticket was filed (UTC).")
    updated_at: UtcDatetime = Field(
        description="When the ticket last changed (UTC). The ETag is derived from this."
    )


class TicketList(ApiModel):
    """Tickets, oldest first."""

    tickets: list[Ticket]


class CreateTicketRequest(ApiModel):
    """Body for `create_ticket`. Only `body` is required."""

    body: Annotated[str, _text(10_000)] = Field(
        description="The feedback, in the person's own words.",
        examples=["Notes get cut off on mobile; I can only see two lines."],
    )
    kind: TicketKind = Field(default="other", description="Default `other`.")
    context: list[ContextInput] = Field(
        default_factory=list,
        max_length=MAX_CONTEXT_ITEMS,
        description=f"Up to {MAX_CONTEXT_ITEMS} context items.",
    )


class UpdateTicketRequest(ApiModel):
    """Body for `update_ticket`. Only the fields you send change."""

    status: Annotated[Literal["new", "ready"] | None, NotNull] = patch_field(
        "`ready` approves the ticket for work (also releases a claim or reopens a closed "
        "ticket); `new` takes it back out of the queue. Cannot be null."
    )
    kind: Annotated[TicketKind | None, NotNull] = patch_field("New kind. Cannot be null.")


class ClaimTicketRequest(ApiModel):
    """Body for `claim_ticket`."""

    by: Annotated[str, _text(100)] = Field(
        description="Who is claiming, e.g. an agent session name. Claiming again renews.",
        examples=["claude-session-7f3a"],
    )
    id: str | None = Field(
        default=None,
        description="A specific ticket to claim. Omit it to claim the oldest ready ticket.",
    )


class ResolveTicketRequest(ApiModel):
    """Body for `resolve_ticket`."""

    status: Literal["resolved", "wontfix"] = Field(description="How the ticket ends.")
    summary: Annotated[str, _text(2000)] = Field(
        description="What was done, or why nothing will be."
    )
    url: WebUrl | None = Field(default=None, description="Link to the change, e.g. a PR.")
