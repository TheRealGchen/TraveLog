from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ..db import Database
from ..errors import ApiError, not_found
from ..ids import new_id
from ..models import (
    MAX_LINKS,
    AddLinkRequest,
    PinnedLink,
    Trip,
    TripResponse,
    UpdateLinkRequest,
    utc_now,
)
from ..previews import LinkPreview, PreviewFetcher
from ..repository import trips as trip_repo
from .deps import (
    ETAG_HEADER,
    IfMatch,
    TripId,
    get_db,
    load_trip,
    parse_if_match,
    problems,
    trip_response,
    trip_write_failed,
)

router = APIRouter(prefix="/trips/{tripId}/links", tags=["Links"])

Db = Annotated[Database, Depends(get_db)]
LinkId = Annotated[str, Path(alias="linkId", description="Link ID (`lnk_...`).")]


def _fetcher(request: Request) -> PreviewFetcher:
    return request.app.state.fetch_preview


Fetcher = Annotated[PreviewFetcher, Depends(_fetcher)]


def _preview_fields(preview: LinkPreview | None) -> dict[str, str | None]:
    return {
        "page_title": preview.title if preview else None,
        "image_url": preview.image_url if preview else None,
        "icon_url": preview.icon_url if preview else None,
    }


def _link_not_found(trip: Trip, link_id: str) -> ApiError:
    return not_found(
        f"Link {link_id} not found on trip {trip.id}. The trip's links are in get_trip."
    )


def _check_url_free(trip: Trip, url: str, path: str, except_id: str | None = None) -> None:
    for link in trip.links:
        if link.url == url and link.id != except_id:
            raise ApiError(
                422,
                f"{path}: {url} is already pinned to this trip as {link.id}",
                errors=[{"path": path, "message": f"already pinned as {link.id}"}],
            )


@router.post(
    "",
    operation_id="add_link",
    summary="Pin a link to a trip",
    description=(
        "Pins a web link (booking, guide, map, ...) to the trip. The API fetches the page once "
        "to get its title, preview image, and icon; if that fails the link is still pinned, "
        f"without a preview. A trip holds up to {MAX_LINKS} links and each URL once. Returns "
        "the updated trip; the new link is the last item of `links`."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=TripResponse,
    responses={201: {"headers": ETAG_HEADER}, **problems(401, 404, 409, 412, 422)},
)
async def add_link(
    trip_id: TripId,
    body: AddLinkRequest,
    response: Response,
    db: Db,
    fetch_preview: Fetcher,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    _check_url_free(trip, body.url, "body.url")
    if len(trip.links) >= MAX_LINKS:
        raise ApiError(409, f"Trip {trip_id} already has {MAX_LINKS} links; unpin one first.")
    now = utc_now()
    link = PinnedLink(
        id=new_id("lnk"),
        url=body.url,
        title=body.title,
        **_preview_fields(await fetch_preview(body.url)),
        created_at=now,
        updated_at=now,
    )
    updated = await trip_repo.add_link(db, trip_id, link, now, if_match=versions)
    if updated is None:
        latest = await load_trip(db, trip_id)
        _check_url_free(latest, body.url, "body.url")
        if len(latest.links) >= MAX_LINKS:
            raise ApiError(409, f"Trip {trip_id} already has {MAX_LINKS} links; unpin one first.")
        raise await trip_write_failed(db, trip_id, versions)
    return trip_response(updated, response)


@router.patch(
    "/{linkId}",
    operation_id="update_link",
    summary="Update a pinned link",
    description=(
        "Changes a link's title (null shows the page's own title again) or URL (the preview is "
        "fetched again). Returns the updated trip."
    ),
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412, 422)},
)
async def update_link(
    trip_id: TripId,
    link_id: LinkId,
    body: UpdateLinkRequest,
    response: Response,
    db: Db,
    fetch_preview: Fetcher,
    if_match: IfMatch = None,
) -> TripResponse:
    versions = parse_if_match(if_match)
    trip = await load_trip(db, trip_id)
    current = next((link for link in trip.links if link.id == link_id), None)
    if current is None:
        raise _link_not_found(trip, link_id)
    fields = body.model_dump(exclude_unset=True)
    if body.url is not None and body.url != current.url:
        _check_url_free(trip, body.url, "body.url", except_id=link_id)
        preview = _preview_fields(await fetch_preview(body.url))
        fields |= {
            "pageTitle": preview["page_title"],
            "imageUrl": preview["image_url"],
            "iconUrl": preview["icon_url"],
        }
    updated = await trip_repo.update_link(
        db, trip_id, link_id, fields, utc_now(), if_match=versions
    )
    if updated is None:
        latest = await load_trip(db, trip_id)
        if not any(link.id == link_id for link in latest.links):
            raise _link_not_found(latest, link_id)
        if body.url is not None:
            _check_url_free(latest, body.url, "body.url", except_id=link_id)
        raise await trip_write_failed(db, trip_id, versions)
    return trip_response(updated, response)


@router.delete(
    "/{linkId}",
    operation_id="remove_link",
    summary="Unpin a link",
    description="Removes a pinned link from the trip. Returns the updated trip.",
    response_model=TripResponse,
    responses={200: {"headers": ETAG_HEADER}, **problems(401, 404, 412)},
)
async def remove_link(
    trip_id: TripId, link_id: LinkId, response: Response, db: Db, if_match: IfMatch = None
) -> TripResponse:
    versions = parse_if_match(if_match)
    updated = await trip_repo.remove_link(db, trip_id, link_id, utc_now(), if_match=versions)
    if updated is None:
        latest = await load_trip(db, trip_id)
        if not any(link.id == link_id for link in latest.links):
            raise _link_not_found(latest, link_id)
        raise await trip_write_failed(db, trip_id, versions)
    return trip_response(updated, response)
