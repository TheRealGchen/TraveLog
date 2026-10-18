from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, BeforeValidator, Field

from .common import ApiModel, NotNull, UtcDatetime, patch_field

MAX_LINKS = 50


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _check_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(
            f"{value!r} is not a web link; send a full http(s) URL such as "
            "https://www.example.com/page"
        )
    return value


WebUrl = Annotated[
    str,
    BeforeValidator(_strip),
    Field(max_length=2048, examples=["https://www.japan-guide.com/e/e3011.html"]),
    AfterValidator(_check_url),
]
"""An absolute http(s) URL."""


class PinnedLink(ApiModel):
    """A web link pinned to a trip, with preview details fetched when it was pinned."""

    id: str = Field(description="Link ID, prefixed with `lnk_`.", examples=["lnk_01J..."])
    url: str = Field(description="The pinned http(s) URL.")
    title: str | None = Field(
        description=(
            "Title you set, or null. Display `title`, else `pageTitle`, else the URL's host."
        )
    )
    page_title: str | None = Field(
        description="The page's own title (`og:title` or `<title>`), fetched when pinned, or null."
    )
    image_url: str | None = Field(
        description="Preview image from the page (`og:image`), or null. Load it from the source."
    )
    icon_url: str | None = Field(description="The site's icon (favicon), or null.")
    created_at: UtcDatetime = Field(description="When the link was pinned (UTC).")
    updated_at: UtcDatetime = Field(description="When the link was last changed (UTC).")


class AddLinkRequest(ApiModel):
    """Body for `add_link`."""

    url: WebUrl = Field(description="Full http(s) URL to pin. Must not already be pinned.")
    title: str | None = Field(
        default=None,
        description="Your title for the link. Omit it to show the page's own title.",
        min_length=1,
        max_length=200,
    )


class UpdateLinkRequest(ApiModel):
    """Body for `update_link`. Only the fields you send change."""

    url: Annotated[WebUrl | None, NotNull] = patch_field(
        "New URL; the preview is fetched again. Cannot be null."
    )
    title: str | None = Field(
        default=None,
        description="New title; null clears it so the page's own title shows.",
        min_length=1,
        max_length=200,
    )
