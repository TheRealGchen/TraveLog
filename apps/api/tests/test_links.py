import asyncio
from typing import Any

import httpx
import pytest

from .test_api import assert_problem

Json = dict[str, Any]


async def pin(client: httpx.AsyncClient, trip_id: str, **body: Any) -> httpx.Response:
    return await client.post(f"/v1/trips/{trip_id}/links", json=body)


async def test_new_trip_has_no_links(trip: Json) -> None:
    assert trip["links"] == []


async def test_pin_link_stores_preview(client: httpx.AsyncClient, trip: Json) -> None:
    r = await pin(client, trip["id"], url="  https://example.com/guide  ")
    assert r.status_code == 201, r.text
    assert r.headers["ETag"] and r.json()["updatedAt"] >= trip["updatedAt"]
    link = r.json()["links"][-1]
    assert link["id"].startswith("lnk_")
    assert link["url"] == "https://example.com/guide"
    assert link["title"] is None
    assert link["pageTitle"] == "Title of https://example.com/guide"
    assert link["imageUrl"] == "https://example.com/guide/og.png"
    assert link["iconUrl"] == "https://example.com/guide/favicon.ico"
    assert (await client.get(f"/v1/trips/{trip['id']}")).json()["links"] == [link]


async def test_pin_without_preview_still_pins(client: httpx.AsyncClient, trip: Json) -> None:
    r = await pin(client, trip["id"], url="https://example.com/nopreview", title="Hotel booking")
    link = r.json()["links"][-1]
    assert link["title"] == "Hotel booking"
    assert link["pageTitle"] is None and link["imageUrl"] is None and link["iconUrl"] is None


@pytest.mark.parametrize(
    "url", ["ftp://example.com/file", "example.com", "/relative/path", "javascript:alert(1)", ""]
)
async def test_invalid_urls_are_rejected(client: httpx.AsyncClient, trip: Json, url: str) -> None:
    assert_problem(await pin(client, trip["id"], url=url), 422, "body.url")


async def test_duplicate_url_is_rejected(client: httpx.AsyncClient, trip: Json) -> None:
    first = (await pin(client, trip["id"], url="https://example.com/a")).json()["links"][0]
    r = await pin(client, trip["id"], url="https://example.com/a")
    assert_problem(r, 422, "body.url", f"already pinned to this trip as {first['id']}")


async def test_concurrent_pins_of_the_same_url_land_once(
    client: httpx.AsyncClient, trip: Json
) -> None:
    results = await asyncio.gather(
        *(pin(client, trip["id"], url="https://example.com/same") for _ in range(5))
    )
    assert sorted(r.status_code for r in results).count(201) == 1
    assert len((await client.get(f"/v1/trips/{trip['id']}")).json()["links"]) == 1


async def test_update_link_title_and_url(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    link = (await pin(client, tid, url="https://example.com/a")).json()["links"][0]
    url = f"/v1/trips/{tid}/links/{link['id']}"

    r = await client.patch(url, json={"title": "Ryokan booking"})
    assert r.status_code == 200, r.text
    assert r.json()["links"][0]["title"] == "Ryokan booking"
    assert r.json()["links"][0]["pageTitle"] == link["pageTitle"]

    r = await client.patch(url, json={"title": None})
    assert r.json()["links"][0]["title"] is None

    r = await client.patch(url, json={"url": "https://example.com/b"})
    updated = r.json()["links"][0]
    assert updated["url"] == "https://example.com/b"
    assert updated["pageTitle"] == "Title of https://example.com/b"
    assert updated["imageUrl"] == "https://example.com/b/og.png"

    await pin(client, tid, url="https://example.com/c")
    assert_problem(
        await client.patch(url, json={"url": "https://example.com/c"}), 422, "already pinned"
    )
    assert_problem(await client.patch(url, json={"url": None}), 422, "cannot be null")


async def test_remove_link(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    r = await pin(client, tid, url="https://example.com/a")
    await pin(client, tid, url="https://example.com/b")
    first = r.json()["links"][0]
    r = await client.delete(f"/v1/trips/{tid}/links/{first['id']}")
    assert r.status_code == 200
    assert [link["url"] for link in r.json()["links"]] == ["https://example.com/b"]
    r = await client.delete(f"/v1/trips/{tid}/links/{first['id']}")
    assert_problem(r, 404, f"Link {first['id']} not found")
    assert_problem(await client.patch(f"/v1/trips/{tid}/links/lnk_nope", json={}), 404, "lnk_nope")
    assert_problem(await pin(client, "trip_nope", url="https://example.com"), 404, "trip_nope")


async def test_link_limit(client: httpx.AsyncClient, trip: Json, db: Any) -> None:
    from travel_api.models import utc_now

    now = utc_now()
    links = [
        {
            "id": f"lnk_{i}",
            "url": f"https://example.com/{i}",
            "title": None,
            "pageTitle": None,
            "imageUrl": None,
            "iconUrl": None,
            "createdAt": now,
            "updatedAt": now,
        }
        for i in range(50)
    ]
    await db.trips.update_one({"_id": trip["id"]}, {"$set": {"links": links}})
    assert_problem(await pin(client, trip["id"], url="https://example.com/x"), 409, "50 links")


async def test_if_match_on_links(client: httpx.AsyncClient, trip: Json) -> None:
    etag = (await client.get(f"/v1/trips/{trip['id']}")).headers["ETag"]
    await client.patch(f"/v1/trips/{trip['id']}", json={"name": "changed"})
    r = await client.post(
        f"/v1/trips/{trip['id']}/links",
        json={"url": "https://example.com"},
        headers={"If-Match": etag},
    )
    assert_problem(r, 412)


async def test_legacy_trip_without_links_reads_empty(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    await db.trips.update_one({"_id": trip["id"]}, {"$unset": {"links": ""}})
    assert (await client.get(f"/v1/trips/{trip['id']}")).json()["links"] == []
    r = await pin(client, trip["id"], url="https://example.com")
    assert r.status_code == 201 and len(r.json()["links"]) == 1
