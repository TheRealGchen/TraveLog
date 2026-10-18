from typing import Any

from pydantic import Field

from .common import ApiModel


class ProblemError(ApiModel):
    """One validation failure."""

    path: str = Field(
        description="Where the problem is, e.g. `body.schedule.endAt` or `query.status`."
    )
    message: str = Field(description="What is wrong and how to fix it.")


class Problem(ApiModel):
    """An RFC 9457 problem details object (`application/problem+json`)."""

    type: str = Field(description="URI reference identifying the problem type.")
    title: str = Field(description="Short summary of the problem type.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(description="What went wrong in this request, specific enough to fix it.")
    errors: list[ProblemError] | None = Field(
        default=None, description="Individual validation failures, when there are any."
    )
    current: dict[str, Any] | None = Field(
        default=None,
        description="On 412 Precondition Failed: the current version of the resource.",
    )
