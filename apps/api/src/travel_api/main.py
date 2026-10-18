from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .auth import require_token
from .config import Settings
from .db import connect, create_indexes
from .errors import PROBLEM_JSON, install_error_handlers
from .routes import activities, travelers, trips

DESCRIPTION = """\
API-first travel planner. Everything the web app does goes through this API, so AI agents
have the same capabilities as the UI.

- Authenticate every `/v1` request with `Authorization: Bearer <API_TOKEN>`.
- Timestamps are ISO 8601. Send them with an offset or `Z`; responses are always UTC (`Z`).
- Dates (`YYYY-MM-DD`) are calendar days in the trip's IANA `timezone`.
- Errors are `application/problem+json` with a specific `detail` and, for validation
  failures, an `errors` array of `{path, message}`.
- Trips and activities return an `ETag`; send it as `If-Match` on a change to avoid
  overwriting someone else's edit (412 on mismatch).

A plain-language guide with workflows is at `/llms.txt`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        client = connect(settings.mongodb_uri)
        app.state.db = client[settings.mongodb_db]
        await create_indexes(app.state.db)
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(
        title="Travel Planner API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        separate_input_output_schemas=False,
    )
    app.state.settings = settings
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
        expose_headers=["ETag", "Location"],
    )

    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
    v1.include_router(trips.router)
    v1.include_router(travelers.router)
    v1.include_router(activities.router)
    app.include_router(v1)

    llms_txt = files("travel_api").joinpath("llms.txt").read_text(encoding="utf-8")

    @app.get("/llms.txt", include_in_schema=False)
    async def get_llms_txt() -> PlainTextResponse:
        return PlainTextResponse(llms_txt)

    _customize_openapi(app)
    return app


def _customize_openapi(app: FastAPI) -> None:
    """Document error responses as problem+json and drop FastAPI's unused default 422 schemas."""
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = default_openapi()
        for path in schema["paths"].values():
            for operation in path.values():
                for code, response in operation.get("responses", {}).items():
                    if int(code) < 400:
                        continue
                    content = response.setdefault("content", {})
                    content.pop("application/json", None)
                    content[PROBLEM_JSON] = {"schema": {"$ref": "#/components/schemas/Problem"}}
                    if code == "422":
                        response["description"] = (
                            "The request is invalid; `errors` lists each problem with its path."
                        )
        components = schema.get("components", {}).get("schemas", {})
        for name in ("HTTPValidationError", "ValidationError"):
            components.pop(name, None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # ty: ignore[invalid-assignment]
