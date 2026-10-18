from typing import Annotated

from pydantic import Field

from .common import ApiModel, Email, HexColor, NotNull, PassportNumber, patch_field

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
    email: Email | None = Field(description="Email address (lowercase), or null.")
    passport_number: PassportNumber | None = Field(
        description="Passport number (uppercase, no spaces or dashes), or null."
    )


class AddTravelerRequest(ApiModel):
    """Body for `add_traveler`, and one entry of `add_travelers`."""

    name: str = Field(
        description="Display name of the traveler.", min_length=1, max_length=80, examples=["Sam"]
    )
    email: Email | None = Field(
        default=None,
        description="Email address. Trimmed and lowercased; must be unique within the trip.",
    )
    passport_number: PassportNumber | None = Field(
        default=None,
        description=(
            "Passport number: 5-20 letters or digits; spaces and dashes are removed and letters "
            "uppercased. Must be unique within the trip."
        ),
    )
    color: HexColor | None = Field(
        default=None,
        description=(
            "Avatar color as a `#rrggbb` hex string. Omit it to get the next unused color "
            "from a fixed palette."
        ),
    )


class AddTravelersRequest(ApiModel):
    """Body for `add_travelers`: several travelers added at once, all or nothing."""

    travelers: list[AddTravelerRequest] = Field(
        description="Travelers to append, in order (1 to 50).", min_length=1, max_length=50
    )


class UpdateTravelerRequest(ApiModel):
    """Body for `update_traveler`. Only the fields you send are changed; send null to clear
    `email` or `passportNumber`."""

    name: Annotated[str | None, NotNull] = patch_field(
        "New display name. Cannot be null.", min_length=1, max_length=80
    )
    color: Annotated[HexColor | None, NotNull] = patch_field(
        "New avatar color as a `#rrggbb` hex string. Cannot be null."
    )
    email: Email | None = Field(
        default=None, description="New email address; null clears it. Unique within the trip."
    )
    passport_number: PassportNumber | None = Field(
        default=None, description="New passport number; null clears it. Unique within the trip."
    )
