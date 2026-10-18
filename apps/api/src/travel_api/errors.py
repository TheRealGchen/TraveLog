"""RFC 9457 problem+json errors and the exception handlers that produce them."""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"

_TITLES = {
    400: "Bad request",
    401: "Unauthorized",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    412: "Precondition failed",
    422: "Validation failed",
    500: "Internal server error",
}
_TYPES = {
    400: "/problems/bad-request",
    401: "/problems/unauthorized",
    404: "/problems/not-found",
    405: "/problems/method-not-allowed",
    409: "/problems/conflict",
    412: "/problems/precondition-failed",
    422: "/problems/validation-error",
    500: "/problems/internal-error",
}


class ApiError(Exception):
    """Raise to return a problem+json response."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        errors: list[dict[str, str]] | None = None,
        current: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.errors = errors
        self.current = current
        self.headers = headers


def not_found(detail: str) -> ApiError:
    return ApiError(404, detail)


def invalid(path: str, message: str) -> ApiError:
    """A single validation failure at ``path`` (for example ``body.schedule.date``)."""
    return ApiError(422, f"{path}: {message}", errors=[{"path": path, "message": message}])


def problem_response(
    status: int,
    detail: str,
    *,
    errors: list[dict[str, str]] | None = None,
    current: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": _TYPES.get(status, "about:blank"),
        "title": _TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
    }
    if errors:
        body["errors"] = errors
    if current is not None:
        body["current"] = jsonable_encoder(current)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _path(loc: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in loc)


def _message(error: dict[str, Any]) -> str:
    kind = error.get("type")
    if kind == "missing":
        return "is required"
    if kind == "extra_forbidden":
        return "is not a recognized field (check the spelling; field names are camelCase)"
    if kind == "json_invalid":
        reason = (error.get("ctx") or {}).get("error", "")
        return f"request body is not valid JSON ({reason})".replace(" ()", "")
    message = str(error.get("msg", "is invalid"))
    return message.removeprefix("Value error, ")


def validation_problem(exc: RequestValidationError) -> JSONResponse:
    errors = [{"path": _path(e["loc"]), "message": _message(e)} for e in exc.errors()]
    summary = "; ".join(f"{e['path']}: {e['message']}" for e in errors[:5])
    if len(errors) > 5:
        summary += f"; and {len(errors) - 5} more"
    count = f"{len(errors)} validation error{'s' if len(errors) != 1 else ''}"
    return problem_response(422, f"{count}: {summary}", errors=errors)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem_response(
            exc.status, exc.detail, errors=exc.errors, current=exc.current, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return validation_problem(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if exc.status_code == 404 and detail == "Not Found":
            detail = f"No route matches {request.method} {request.url.path}. See /openapi.json."
        if exc.status_code == 405:
            detail = f"{request.method} is not allowed on {request.url.path}. See /openapi.json."
        return problem_response(exc.status_code, detail, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return problem_response(500, f"Unexpected server error ({type(exc).__name__}).")
