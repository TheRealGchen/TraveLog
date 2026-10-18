from collections.abc import AsyncGenerator, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from testcontainers.community.mongodb import MongoDbContainer

from travel_api.config import Settings
from travel_api.main import create_app

TOKEN = "test-token"


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer("mongo:8") as mongo:
        yield mongo.get_connection_url()


@pytest.fixture
async def app(mongo_uri: str) -> AsyncGenerator[FastAPI]:
    db_name = f"test_{uuid4().hex}"
    app = create_app(Settings(mongodb_uri=mongo_uri, api_token=TOKEN, mongodb_db=db_name))
    async with app.router.lifespan_context(app):
        yield app
        await app.state.db.client.drop_database(db_name)


@pytest.fixture
def db(app: FastAPI) -> Any:
    return app.state.db


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as c:
        yield c


@pytest.fixture
async def trip(client: httpx.AsyncClient) -> dict[str, Any]:
    """A Tokyo trip, 2027-04-02 to 2027-04-14."""
    r = await client.post(
        "/v1/trips",
        json={
            "name": "Japan 2027",
            "destination": "Tokyo & Kyoto",
            "timezone": "Asia/Tokyo",
            "startDate": "2027-04-02",
            "endDate": "2027-04-14",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
