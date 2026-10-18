from typing import Annotated

from pydantic import Field

from .common import ApiModel, HexColor, NotNull, patch_field

TRAVELER_PALETTE = [
    "#6366f1",
    "#ec4899",
    "#f59e0b",
    "#10b981",
    "#0ea5e9",
    "#8b5cf6",
    "#ef4444",
    "#14b8a6",
]
"""Colors assigned, in order, to travelers added without an explicit color."""


class Traveler(ApiModel):
    """A person on the trip. Travelers are stored inside their trip document."""

    id: str = Field(description="Traveler ID, prefixed with `trv_`.", examples=["trv_01J..."])
    name: str = Field(description="Display name of the traveler.", min_length=1, max_length=80)
    color: HexColor = Field(description="Avatar color as a `#rrggbb` hex string.")


class AddTravelerRequest(ApiModel):
    """Body for `add_traveler`."""

    name: str = Field(
        description="Display name of the traveler.", min_length=1, max_length=80, examples=["Sam"]
    )
    color: HexColor | None = Field(
        default=None,
        description=(
            "Avatar color as a `#rrggbb` hex string. Omit it to get the next unused color "
            "from a fixed palette."
        ),
    )


class UpdateTravelerRequest(ApiModel):
    """Body for `update_traveler`. Only the fields you send are changed."""

    name: Annotated[str | None, NotNull] = patch_field(
        "New display name. Cannot be null.", min_length=1, max_length=80
    )
    color: Annotated[HexColor | None, NotNull] = patch_field(
        "New avatar color as a `#rrggbb` hex string. Cannot be null."
    )
