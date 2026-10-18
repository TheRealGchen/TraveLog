"""The single bearer-token check used by every /v1 route (the web app and agents alike)."""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError

_bearer = HTTPBearer(
    auto_error=False,
    description="Send `Authorization: Bearer <API_TOKEN>` on every /v1 request.",
)


async def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    challenge = {"WWW-Authenticate": "Bearer"}
    if credentials is None:
        raise ApiError(
            401,
            "Missing bearer token. Send the header 'Authorization: Bearer <API_TOKEN>'.",
            headers=challenge,
        )
    expected: str = request.app.state.settings.api_token
    if not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise ApiError(401, "Invalid bearer token.", headers=challenge)
