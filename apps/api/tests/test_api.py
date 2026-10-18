import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

Json = dict[str, Any]


async def add_activity(client: httpx.AsyncClient, trip_id: str, date: str, **body: Any) -> Json:
    r = await client.post(f"/v1/trips/{trip_id}/days/{date}/activities", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def add_traveler(client: httpx.AsyncClient, trip_id: str, name: str) -> Json:
    r = await client.post(f"/v1/trips/{trip_id}/travelers", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["travelers"][-1]


def assert_problem(r: httpx.Response, status: int, *fragments: str) -> Json:
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == status and body["title"] and body["type"]
    for fragment in fragments:
        assert fragment in r.text, f"{fragment!r} not in {r.text}"
    return body


# Discovery and auth


async def test_openapi_and_llms_txt_are_public(client: httpx.AsyncClient) -> None:
    del client.headers["Authorization"]
    spec = (await client.get("/openapi.json")).json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert ops == {
        "list_trips",
        "create_trip",
        "get_trip",
        "update_trip",
        "delete_trip",
        "list_days",
        "get_day",
        "update_day",
        "add_traveler",
        "add_travelers",
        "update_traveler",
        "remove_traveler",
        "list_activities",
        "add_activity",
        "get_activity",
        "update_activity",
        "move_activity",
        "delete_activity",
    }
    r = await client.get("/llms.txt")
    assert r.status_code == 200 and "move_activity" in r.text


async def test_missing_and_wrong_token(client: httpx.AsyncClient) -> None:
    del client.headers["Authorization"]
    assert_problem(await client.get("/v1/trips"), 401, "Missing bearer token")
    r = await client.get("/v1/trips", headers={"Authorization": "Bearer nope"})
    assert_problem(r, 401, "Invalid bearer token")


# Trips


async def test_create_and_get_trip(client: httpx.AsyncClient, trip: Json) -> None:
    assert trip["id"].startswith("trip_")
    assert trip["timezone"] == "Asia/Tokyo"
    assert trip["travelers"] == [] and trip["ownerId"] is None and trip["schemaVersion"] == 1
    assert trip["createdAt"].endswith("Z")
    assert trip["status"] == "upcoming" and trip["daysUntilStart"] > 0
    r = await client.get(f"/v1/trips/{trip['id']}")
    assert r.status_code == 200
    assert r.headers["ETag"]
    assert r.json() == trip


async def test_create_trip_defaults_timezone_to_utc(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/trips", json={"name": "x", "startDate": "2027-01-01", "endDate": "2027-01-02"}
    )
    assert r.status_code == 201 and r.json()["timezone"] == "UTC"
    assert r.json()["destination"] is None


async def test_list_trips_status_and_sort(client: httpx.AsyncClient) -> None:
    for name, start, end in [
        ("Later", "2030-01-01", "2030-01-05"),
        ("Past", "2020-01-01", "2020-01-05"),
        ("Now", "2000-01-01", "2099-01-01"),
        ("Soon", "2029-01-01", "2029-01-05"),
    ]:
        await client.post("/v1/trips", json={"name": name, "startDate": start, "endDate": end})
    trips = (await client.get("/v1/trips")).json()["trips"]
    assert [t["name"] for t in trips] == ["Now", "Past", "Soon", "Later"]
    assert {t["name"]: t["status"] for t in trips} == {
        "Now": "ongoing",
        "Past": "past",
        "Soon": "upcoming",
        "Later": "upcoming",
    }
    assert trips[0]["travelerCount"] == 0
    upcoming = (await client.get("/v1/trips", params={"status": "upcoming"})).json()["trips"]
    assert [t["name"] for t in upcoming] == ["Soon", "Later"]
    by_name = (await client.get("/v1/trips", params={"sort": "name"})).json()["trips"]
    assert [t["name"] for t in by_name] == ["Later", "Now", "Past", "Soon"]
    r = await client.get("/v1/trips", params={"sort": "nope"})
    assert_problem(r, 422, "query.sort")


async def test_update_trip(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.patch(f"/v1/trips/{trip['id']}", json={"name": "Japan!", "destination": None})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Japan!" and body["destination"] is None
    assert body["startDate"] == trip["startDate"]
    assert body["updatedAt"] >= trip["updatedAt"]


async def test_update_trip_rejects_null_name_and_bad_range(
    client: httpx.AsyncClient, trip: Json
) -> None:
    r = await client.patch(f"/v1/trips/{trip['id']}", json={"name": None})
    assert_problem(r, 422, "body.name", "cannot be null")
    r = await client.patch(f"/v1/trips/{trip['id']}", json={"endDate": "2027-04-01"})
    assert_problem(r, 422, "endDate must be on or after startDate")


async def test_delete_trip_deletes_its_days(client: httpx.AsyncClient, trip: Json, db: Any) -> None:
    await add_activity(client, trip["id"], "2027-04-03", title="A")
    assert await db.days.count_documents({"tripId": trip["id"]}) == 13
    r = await client.delete(f"/v1/trips/{trip['id']}")
    assert r.status_code == 204
    assert await db.days.count_documents({"tripId": trip["id"]}) == 0
    assert_problem(await client.get(f"/v1/trips/{trip['id']}"), 404, trip["id"])


async def test_unknown_trip_is_404_naming_id(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/v1/trips/trip_nope"), 404, "Trip trip_nope not found")
    assert_problem(await client.delete("/v1/trips/trip_nope"), 404, "trip_nope")
    r = await client.post("/v1/trips/trip_nope/days/2027-04-03/activities", json={"title": "x"})
    assert_problem(r, 404, "trip_nope")
    assert_problem(await client.get("/v1/trips/trip_nope/days"), 404, "trip_nope")


# Validation failures


@pytest.mark.parametrize(
    ("body", "fragments"),
    [
        ({"name": "x", "startDate": "2027-13-01", "endDate": "2027-12-02"}, ["body.startDate"]),
        ({"name": "x", "startDate": "04/02/2027", "endDate": "2027-12-02"}, ["body.startDate"]),
        (
            {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-01"},
            ["endDate must be on or after startDate (got 2027-04-02 and 2027-04-01)"],
        ),
        (
            {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-03", "timezone": "Mars/X"},
            ["body.timezone", "not a known IANA timezone"],
        ),
        ({"startDate": "2027-04-02", "endDate": "2027-04-03"}, ["body.name", "is required"]),
        (
            {"name": "x", "startDate": "2027-04-02", "endDate": "2027-04-03", "nmae": "y"},
            ["body.nmae", "not a recognized field"],
        ),
    ],
)
async def test_create_trip_validation(
    client: httpx.AsyncClient, body: Json, fragments: list[str]
) -> None:
    problem = assert_problem(await client.post("/v1/trips", json=body), 422, *fragments)
    assert problem["errors"] and all({"path", "message"} <= e.keys() for e in problem["errors"])


async def test_invalid_json_body(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/trips", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert_problem(r, 422, "not valid JSON")


async def test_end_at_before_start_at(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/days/2027-04-03/activities",
        json={
            "title": "x",
            "time": {"startAt": "2027-04-03T02:00:00Z", "endAt": "2027-04-03T01:00:00Z"},
        },
    )
    assert_problem(
        r,
        422,
        "body.time",
        "endAt must be after startAt (got 2027-04-03T02:00:00.000Z and 2027-04-03T01:00:00.000Z)",
    )


async def test_timestamp_without_offset(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/days/2027-04-03/activities",
        json={"title": "x", "time": {"startAt": "2027-04-03T10:00:00"}},
    )
    assert_problem(r, 422, "body.time.startAt", "must include a UTC offset or 'Z'")


async def test_unknown_traveler_id(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/days/2027-04-03/activities",
        json={"title": "x", "travelerIds": ["trv_ghost"]},
    )
    assert_problem(r, 422, "body.travelerIds.0", "traveler trv_ghost is not on trip")


async def test_day_outside_trip_is_404(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(f"/v1/trips/{trip['id']}/days/2027-05-01/activities", json={"title": "x"})
    assert_problem(r, 404, "no day 2027-05-01", "2027-04-02 to 2027-04-14")
    assert_problem(await client.get(f"/v1/trips/{trip['id']}/days/2027-05-01"), 404)
    assert_problem(await client.get(f"/v1/trips/{trip['id']}/days/May-1"), 422, "path.date")


async def test_start_at_must_fall_on_the_day(client: httpx.AsyncClient, trip: Json) -> None:
    # 10:00 Tokyo on Apr 4 is not on Apr 3.
    r = await client.post(
        f"/v1/trips/{trip['id']}/days/2027-04-03/activities",
        json={"title": "x", "time": {"startAt": "2027-04-04T10:00:00+09:00"}},
    )
    assert_problem(r, 422, "body.time.startAt", "is on 2027-04-04 in Asia/Tokyo", "move_activity")


# Days


async def test_days_are_created_with_the_trip(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.get(f"/v1/trips/{trip['id']}/days")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "Asia/Tokyo" and body["daysUntilStart"] == trip["daysUntilStart"]
    assert [d["date"] for d in body["days"]][:3] == ["2027-04-02", "2027-04-03", "2027-04-04"]
    assert len(body["days"]) == 13
    assert body["days"][0] == {
        "tripId": trip["id"],
        "date": "2027-04-02",
        "dayNumber": 1,
        "lodging": None,
        "startLocation": None,
        "activities": [],
        "createdAt": trip["createdAt"],
        "updatedAt": trip["createdAt"],
    }


async def test_update_day_null_versus_omitted(client: httpx.AsyncClient, trip: Json) -> None:
    url = f"/v1/trips/{trip['id']}/days/2027-04-03"
    r = await client.patch(
        url, json={"lodging": {"name": "Hotel Gracery"}, "startLocation": {"name": "Narita"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["lodging"] == {"name": "Hotel Gracery"} and r.json()["dayNumber"] == 2
    assert r.headers["ETag"]
    r = await client.patch(url, json={"startLocation": None})
    assert r.json()["startLocation"] is None
    assert r.json()["lodging"] == {"name": "Hotel Gracery"}
    r = await client.get(url)
    assert r.json()["lodging"] == {"name": "Hotel Gracery"} and r.headers["ETag"]
    assert_problem(await client.patch(url, json={"lodging": "Hotel"}), 422, "body.lodging")


async def test_legacy_trip_without_day_documents_gets_days_on_read(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    await db.days.delete_many({"tripId": trip["id"]})
    r = await client.get(f"/v1/trips/{trip['id']}/days")
    assert len(r.json()["days"]) == 13
    assert await db.days.count_documents({"tripId": trip["id"]}) == 13
    await db.days.delete_many({"tripId": trip["id"]})
    r = await client.patch(
        f"/v1/trips/{trip['id']}/days/2027-04-05", json={"lodging": {"name": "Ryokan"}}
    )
    assert r.status_code == 200 and r.json()["lodging"] == {"name": "Ryokan"}


async def test_day_sorts_activities_by_time_untimed_last(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    await add_activity(client, tid, "2027-04-04", title="Wander")
    await add_activity(
        client, tid, "2027-04-04", title="Dinner", time={"startAt": "2027-04-04T19:00:00+09:00"}
    )
    # 23:30Z on Apr 3 is 08:30 on Apr 4 in Tokyo.
    await add_activity(
        client, tid, "2027-04-04", title="Breakfast", time={"startAt": "2027-04-03T23:30:00Z"}
    )
    day = (await client.get(f"/v1/trips/{tid}/days/2027-04-04")).json()
    assert [a["title"] for a in day["activities"]] == ["Breakfast", "Dinner", "Wander"]
    assert all(a["date"] == "2027-04-04" and a["tripId"] == tid for a in day["activities"])


# Activities


async def test_offset_timestamp_is_stored_as_utc_and_returned_with_z(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    act = await add_activity(
        client,
        trip["id"],
        "2027-04-03",
        title="teamLab Planets",
        time={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
        location={"name": "Toyosu"},
        notes="Book tickets ahead",
    )
    assert act["id"].startswith("act_") and act["date"] == "2027-04-03"
    assert act["time"] == {
        "startAt": "2027-04-03T01:00:00.000Z",
        "endAt": "2027-04-03T03:00:00.000Z",
    }
    assert act["status"] == "planned"
    doc = await db.days.find_one({"tripId": trip["id"], "date": "2027-04-03"})
    stored = doc["activities"][0]
    assert stored["time"]["startAt"] == datetime(2027, 4, 3, 1, 0, tzinfo=UTC)
    assert isinstance(stored["createdAt"], datetime)


async def test_activity_crud(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    act = await add_activity(client, tid, "2027-04-05", title="Ramen")
    assert act["time"] is None and act["status"] == "planned"
    url = f"/v1/trips/{tid}/activities/{act['id']}"

    r = await client.get(url)
    assert r.status_code == 200 and r.json() == act and r.headers["ETag"]

    r = await client.patch(url, json={"notes": "Ichiran", "location": {"name": "Shibuya"}})
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "Ichiran" and r.json()["location"] == {"name": "Shibuya"}
    assert r.json()["title"] == "Ramen" and r.json()["date"] == "2027-04-05"

    r = await client.patch(
        url, json={"notes": None, "time": {"startAt": "2027-04-05T12:00:00+09:00"}}
    )
    assert r.json()["notes"] is None and r.json()["location"] == {"name": "Shibuya"}
    assert r.json()["time"] == {"startAt": "2027-04-05T03:00:00.000Z", "endAt": None}

    r = await client.patch(url, json={"time": {"startAt": "2027-04-06T12:00:00+09:00"}})
    assert_problem(r, 422, "body.time.startAt", "move_activity")

    r = await client.patch(url, json={"time": None, "status": "done"})
    assert r.json()["time"] is None and r.json()["status"] == "done"

    r = await client.patch(url, json={"notes": "$where"})
    assert r.json()["notes"] == "$where"  # user text is never an expression

    assert_problem(await client.patch(url, json={"title": None}), 422, "cannot be null")

    assert (await client.delete(url)).status_code == 204
    assert_problem(await client.get(url), 404, act["id"])
    day = (await client.get(f"/v1/trips/{tid}/days/2027-04-05")).json()
    assert day["activities"] == []


async def test_activity_under_wrong_trip_is_404(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], "2027-04-03", title="x")
    other = (
        await client.post(
            "/v1/trips", json={"name": "Other", "startDate": "2027-04-01", "endDate": "2027-04-05"}
        )
    ).json()
    url = f"/v1/trips/{other['id']}/activities/{act['id']}"
    assert_problem(await client.get(url), 404, act["id"], other["id"])
    assert_problem(await client.patch(url, json={"title": "y"}), 404, act["id"])
    assert_problem(await client.post(f"{url}/move", json={"date": "2027-04-04"}), 404, act["id"])
    assert_problem(await client.delete(url), 404, act["id"])
    r = await client.get(f"/v1/trips/{trip['id']}/activities/{act['id']}")
    assert r.json()["title"] == "x"


async def test_list_activities_filters(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    sam = await add_traveler(client, tid, "Sam")
    await add_activity(
        client, tid, "2027-04-03", title="Late", time={"startAt": "2027-04-03T18:00:00+09:00"}
    )
    await add_activity(
        client,
        tid,
        "2027-04-03",
        title="Early",
        time={"startAt": "2027-04-03T08:00:00+09:00"},
        travelerIds=[sam["id"]],
    )
    await add_activity(client, tid, "2027-04-02", title="Day 1", status="done")
    await add_activity(client, tid, "2027-04-10", title="Maybe", status="idea")

    async def titles(**params: Any) -> list[str]:
        r = await client.get(f"/v1/trips/{tid}/activities", params=params)
        assert r.status_code == 200, r.text
        return [a["title"] for a in r.json()["activities"]]

    assert await titles() == ["Day 1", "Early", "Late", "Maybe"]
    assert await titles(date="2027-04-03") == ["Early", "Late"]
    assert await titles(travelerId=sam["id"]) == ["Early"]
    assert await titles(status="done") == ["Day 1"]
    assert await titles(status="idea") == ["Maybe"]
    r = await client.get(f"/v1/trips/{tid}/activities", params={"travelerId": "trv_ghost"})
    assert_problem(r, 404, "trv_ghost")


async def test_concurrent_add_activity_calls_all_land(
    client: httpx.AsyncClient, trip: Json
) -> None:
    url = f"/v1/trips/{trip['id']}/days/2027-04-03/activities"
    results = await asyncio.gather(*(client.post(url, json={"title": f"A{i}"}) for i in range(10)))
    assert all(r.status_code == 201 for r in results)
    day = (await client.get(f"/v1/trips/{trip['id']}/days/2027-04-03")).json()
    assert sorted(a["title"] for a in day["activities"]) == sorted(f"A{i}" for i in range(10))


async def test_concurrent_add_traveler_calls_all_land(
    client: httpx.AsyncClient, trip: Json
) -> None:
    results = await asyncio.gather(
        *(
            client.post(f"/v1/trips/{trip['id']}/travelers", json={"name": f"T{i}"})
            for i in range(6)
        )
    )
    assert all(r.status_code == 201 for r in results)
    travelers = (await client.get(f"/v1/trips/{trip['id']}")).json()["travelers"]
    assert sorted(t["name"] for t in travelers) == sorted(f"T{i}" for i in range(6))


# Moving


async def test_move_across_days_keeps_time_of_day(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    act = await add_activity(
        client,
        tid,
        "2027-04-03",
        title="x",
        time={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
    )
    r = await client.post(
        f"/v1/trips/{tid}/activities/{act['id']}/move", json={"date": "2027-04-10"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["date"] == "2027-04-10" and r.json()["id"] == act["id"]
    assert r.json()["time"] == {
        "startAt": "2027-04-10T01:00:00.000Z",
        "endAt": "2027-04-10T03:00:00.000Z",
    }
    assert r.headers["ETag"]
    source = (await client.get(f"/v1/trips/{tid}/days/2027-04-03")).json()
    target = (await client.get(f"/v1/trips/{tid}/days/2027-04-10")).json()
    assert source["activities"] == [] and [a["id"] for a in target["activities"]] == [act["id"]]


async def test_move_keeps_wall_clock_time_across_dst(client: httpx.AsyncClient) -> None:
    trip = (
        await client.post(
            "/v1/trips",
            json={
                "name": "NYC",
                "timezone": "America/New_York",
                "startDate": "2027-03-10",
                "endDate": "2027-03-20",
            },
        )
    ).json()
    act = await add_activity(
        client,
        trip["id"],
        "2027-03-12",
        title="Show",
        time={"startAt": "2027-03-12T19:00:00-05:00"},
    )
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities/{act['id']}/move", json={"date": "2027-03-15"}
    )
    # 19:00 local after the DST change is 23:00Z instead of 00:00Z.
    assert r.json()["time"]["startAt"] == "2027-03-15T23:00:00.000Z"


async def test_move_with_new_start_keeps_duration(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(
        client,
        trip["id"],
        "2027-04-03",
        title="x",
        time={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
    )
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}/move"
    r = await client.post(url, json={"date": "2027-04-05", "startAt": "2027-04-05T14:00:00+09:00"})
    assert r.json()["time"] == {
        "startAt": "2027-04-05T05:00:00.000Z",
        "endAt": "2027-04-05T07:00:00.000Z",
    }
    # Same day, new time.
    r = await client.post(url, json={"date": "2027-04-05", "startAt": "2027-04-05T09:00:00+09:00"})
    assert r.json()["time"]["startAt"] == "2027-04-05T00:00:00.000Z"
    day = (await client.get(f"/v1/trips/{trip['id']}/days/2027-04-05")).json()
    assert len(day["activities"]) == 1


async def test_move_validation(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], "2027-04-03", title="x")
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}/move"
    assert_problem(await client.post(url, json={"date": "2027-06-01"}), 422, "body.date", "outside")
    r = await client.post(url, json={"date": "2027-04-05", "startAt": "2027-04-06T10:00:00+09:00"})
    assert_problem(r, 422, "is on 2027-04-06")
    r = await client.post(url, json={"date": "2027-04-04"})
    assert r.json()["date"] == "2027-04-04" and r.json()["time"] is None


# Travelers


async def test_traveler_add_update_and_palette(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    r = await client.post(f"/v1/trips/{tid}/travelers", json={"name": "Sam"})
    assert r.status_code == 201
    sam = r.json()["travelers"][0]
    assert sam["id"].startswith("trv_") and sam["color"] == "#6366f1"
    r = await client.post(f"/v1/trips/{tid}/travelers", json={"name": "Ana", "color": "#000000"})
    r = await client.post(f"/v1/trips/{tid}/travelers", json={"name": "Lee"})
    assert [t["color"] for t in r.json()["travelers"]] == ["#6366f1", "#000000", "#ec4899"]
    assert r.json()["travelers"][-1]["name"] == "Lee"

    r = await client.patch(f"/v1/trips/{tid}/travelers/{sam['id']}", json={"name": "Samantha"})
    assert r.status_code == 200
    assert r.json()["travelers"][0] == {**sam, "name": "Samantha"}
    assert sam["email"] is None and sam["passportNumber"] is None
    r = await client.patch(f"/v1/trips/{tid}/travelers/trv_ghost", json={"name": "x"})
    assert_problem(r, 404, "Traveler trv_ghost not found on trip")
    r = await client.patch(f"/v1/trips/{tid}/travelers/{sam['id']}", json={"color": "red"})
    assert_problem(r, 422, "body.color")


async def test_traveler_email_and_passport_are_normalized(
    client: httpx.AsyncClient, trip: Json
) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/travelers",
        json={"name": "Sam", "email": " Sam@Example.COM ", "passportNumber": "x 1234-5678"},
    )
    assert r.status_code == 201, r.text
    sam = r.json()["travelers"][-1]
    assert sam["email"] == "sam@example.com" and sam["passportNumber"] == "X12345678"
    r = await client.post(f"/v1/trips/{trip['id']}/travelers", json={"name": "Kai"})
    assert r.json()["travelers"][-1]["email"] is None
    assert r.json()["travelers"][-1]["passportNumber"] is None


@pytest.mark.parametrize(
    ("body", "fragments"),
    [
        ({"name": "x", "email": "not-an-email"}, ["body.email", "not a valid email"]),
        ({"name": "x", "passportNumber": "12"}, ["body.passportNumber", "5-20 letters or digits"]),
        ({"name": "x", "passportNumber": "AB12#45"}, ["body.passportNumber"]),
    ],
)
async def test_invalid_email_or_passport(
    client: httpx.AsyncClient, trip: Json, body: Json, fragments: list[str]
) -> None:
    r = await client.post(f"/v1/trips/{trip['id']}/travelers", json=body)
    assert_problem(r, 422, *fragments)


async def test_bulk_add_appends_in_order_with_palette_colors(
    client: httpx.AsyncClient, trip: Json
) -> None:
    await add_traveler(client, trip["id"], "First")
    r = await client.post(
        f"/v1/trips/{trip['id']}/travelers/batch",
        json={
            "travelers": [
                {"name": "Sam Lee", "email": "sam@example.com", "passportNumber": "X12345678"},
                {"name": "Ana Ruiz", "email": "ana@example.com", "color": "#000000"},
                {"name": "Kai"},
            ]
        },
    )
    assert r.status_code == 201, r.text
    assert r.headers["ETag"]
    travelers = r.json()["travelers"]
    assert [t["name"] for t in travelers] == ["First", "Sam Lee", "Ana Ruiz", "Kai"]
    assert [t["color"] for t in travelers] == ["#6366f1", "#ec4899", "#000000", "#f59e0b"]
    assert len({t["id"] for t in travelers}) == 4
    assert travelers[1]["passportNumber"] == "X12345678"


async def test_bulk_add_is_all_or_nothing(client: httpx.AsyncClient, trip: Json) -> None:
    url = f"/v1/trips/{trip['id']}/travelers/batch"
    r = await client.post(
        url, json={"travelers": [{"name": "Ok"}, {"name": "Bad", "email": "nope"}, {"name": "Ok2"}]}
    )
    assert_problem(r, 422, "body.travelers.1.email")
    assert (await client.get(f"/v1/trips/{trip['id']}")).json()["travelers"] == []
    assert_problem(await client.post(url, json={"travelers": []}), 422, "body.travelers")
    too_many = {"travelers": [{"name": f"T{i}"} for i in range(51)]}
    assert_problem(await client.post(url, json=too_many), 422, "body.travelers")


async def test_duplicate_email_or_passport_is_rejected(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    await client.post(
        f"/v1/trips/{tid}/travelers",
        json={"name": "Sam", "email": "sam@example.com", "passportNumber": "X12345678"},
    )
    r = await client.post(
        f"/v1/trips/{tid}/travelers", json={"name": "Imposter", "email": "SAM@example.com"}
    )
    assert_problem(r, 422, "body.email", "already used by Sam")
    r = await client.post(
        f"/v1/trips/{tid}/travelers/batch",
        json={
            "travelers": [
                {"name": "A", "email": "a@example.com"},
                {"name": "B", "email": "a@example.com"},
                {"name": "C", "passportNumber": "x1234-5678"},
            ]
        },
    )
    problem = assert_problem(r, 422, "appears more than once", "already used by Sam")
    assert [e["path"] for e in problem["errors"]] == [
        "body.travelers.1.email",
        "body.travelers.2.passportNumber",
    ]
    assert len((await client.get(f"/v1/trips/{tid}")).json()["travelers"]) == 1


async def test_update_traveler_email_and_passport(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    r = await client.post(
        f"/v1/trips/{tid}/travelers/batch",
        json={"travelers": [{"name": "Sam", "email": "sam@example.com"}, {"name": "Ana"}]},
    )
    sam, ana = r.json()["travelers"]
    url = f"/v1/trips/{tid}/travelers/{ana['id']}"
    r = await client.patch(url, json={"email": "ana@example.com", "passportNumber": "p9876543"})
    assert r.status_code == 200, r.text
    assert r.json()["travelers"][1] == {
        **ana,
        "email": "ana@example.com",
        "passportNumber": "P9876543",
    }
    r = await client.patch(url, json={"passportNumber": None})
    assert r.json()["travelers"][1]["passportNumber"] is None
    assert r.json()["travelers"][1]["email"] == "ana@example.com"
    assert_problem(await client.patch(url, json={"email": "sam@example.com"}), 422, "Sam")
    # Re-saving your own email is fine.
    r = await client.patch(
        f"/v1/trips/{tid}/travelers/{sam['id']}", json={"email": "sam@example.com"}
    )
    assert r.status_code == 200
    assert_problem(await client.patch(url, json={"name": None}), 422, "cannot be null")


async def test_legacy_travelers_without_email_or_passport_read_as_null(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    await db.trips.update_one(
        {"_id": trip["id"]},
        {"$set": {"travelers": [{"id": "trv_OLD", "name": "Old", "color": "#6366f1"}]}},
    )
    t = (await client.get(f"/v1/trips/{trip['id']}")).json()["travelers"][0]
    assert t == {
        "id": "trv_OLD",
        "name": "Old",
        "color": "#6366f1",
        "email": None,
        "passportNumber": None,
    }
    listed = (await client.get("/v1/trips")).json()["trips"][0]["travelers"][0]
    assert listed["email"] is None


async def test_concurrent_bulk_adds_all_land(client: httpx.AsyncClient, trip: Json) -> None:
    url = f"/v1/trips/{trip['id']}/travelers/batch"
    results = await asyncio.gather(
        *(
            client.post(url, json={"travelers": [{"name": f"G{g}-{i}"} for i in range(3)]})
            for g in range(4)
        )
    )
    assert all(r.status_code == 201 for r in results)
    travelers = (await client.get(f"/v1/trips/{trip['id']}")).json()["travelers"]
    assert len(travelers) == 12


async def test_removing_traveler_cleans_up_activities(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    sam = await add_traveler(client, tid, "Sam")
    ana = await add_traveler(client, tid, "Ana")
    a1 = await add_activity(
        client, tid, "2027-04-03", title="x", travelerIds=[sam["id"], ana["id"]]
    )
    a2 = await add_activity(client, tid, "2027-04-03", title="y", travelerIds=[sam["id"]])
    a3 = await add_activity(client, tid, "2027-04-08", title="z", travelerIds=[sam["id"]])
    r = await client.delete(f"/v1/trips/{tid}/travelers/{sam['id']}")
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["travelers"]] == [ana["id"]]
    for act, expected in [(a1, [ana["id"]]), (a2, []), (a3, [])]:
        got = (await client.get(f"/v1/trips/{tid}/activities/{act['id']}")).json()
        assert got["travelerIds"] == expected
    assert_problem(await client.delete(f"/v1/trips/{tid}/travelers/{sam['id']}"), 404, sam["id"])


# ETag and If-Match


async def test_if_match_mismatch_returns_412_with_current(
    client: httpx.AsyncClient, trip: Json
) -> None:
    url = f"/v1/trips/{trip['id']}"
    etag = (await client.get(url)).headers["ETag"]
    r = await client.patch(url, json={"name": "A"}, headers={"If-Match": etag})
    assert r.status_code == 200
    new_etag = r.headers["ETag"]
    assert new_etag != etag

    r = await client.patch(url, json={"name": "B"}, headers={"If-Match": etag})
    problem = assert_problem(r, 412, "current ETag")
    assert problem["current"]["name"] == "A"
    assert r.headers["ETag"] == new_etag
    assert (await client.get(url)).json()["name"] == "A"


async def test_if_match_on_activity_and_day(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], "2027-04-03", title="x")
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}"
    etag = (await client.get(url)).headers["ETag"]
    assert (
        await client.patch(url, json={"title": "y"}, headers={"If-Match": etag})
    ).status_code == 200
    r = await client.patch(url, json={"title": "z"}, headers={"If-Match": etag})
    assert assert_problem(r, 412)["current"]["title"] == "y"
    r = await client.post(f"{url}/move", json={"date": "2027-04-04"}, headers={"If-Match": etag})
    assert_problem(r, 412)
    assert_problem(await client.delete(url, headers={"If-Match": etag}), 412)

    day_url = f"/v1/trips/{trip['id']}/days/2027-04-03"
    day_etag = (await client.get(day_url)).headers["ETag"]
    await client.patch(url, json={"notes": "bumps the day"})
    r = await client.patch(day_url, json={"lodging": {"name": "x"}}, headers={"If-Match": day_etag})
    assert_problem(r, 412)
    assert (await client.delete(url, headers={"If-Match": "*"})).status_code == 204


# Trip range and timezone changes


async def test_extending_and_shrinking_trip_adds_and_removes_empty_days(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    r = await client.patch(
        f"/v1/trips/{tid}", json={"startDate": "2027-03-31", "endDate": "2027-04-05"}
    )
    assert r.status_code == 200, r.text
    dates = [d["date"] for d in (await client.get(f"/v1/trips/{tid}/days")).json()["days"]]
    assert dates == [
        "2027-03-31",
        "2027-04-01",
        "2027-04-02",
        "2027-04-03",
        "2027-04-04",
        "2027-04-05",
    ]


async def test_shrinking_trip_with_plans_on_removed_days_is_rejected(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    act = await add_activity(client, tid, "2027-04-12", title="Kyoto")
    await client.patch(f"/v1/trips/{tid}/days/2027-04-13", json={"lodging": {"name": "Inn"}})
    r = await client.patch(f"/v1/trips/{tid}", json={"endDate": "2027-04-10"})
    assert_problem(r, 409, "2027-04-12 (1 activity)", "2027-04-13 (0 activities, lodging)")
    assert (await client.get(f"/v1/trips/{tid}")).json()["endDate"] == "2027-04-14"
    await client.post(f"/v1/trips/{tid}/activities/{act['id']}/move", json={"date": "2027-04-10"})
    await client.patch(f"/v1/trips/{tid}/days/2027-04-13", json={"lodging": None})
    r = await client.patch(f"/v1/trips/{tid}", json={"endDate": "2027-04-10"})
    assert r.status_code == 200
    assert len((await client.get(f"/v1/trips/{tid}/days")).json()["days"]) == 9


async def test_timezone_change_that_moves_an_activity_day_is_rejected(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    # 01:00 Apr 4 in Tokyo is 16:00Z Apr 3, so in UTC it would start on Apr 3.
    act = await add_activity(
        client, tid, "2027-04-04", title="Early", time={"startAt": "2027-04-04T01:00:00+09:00"}
    )
    await add_activity(
        client, tid, "2027-04-04", title="Noon", time={"startAt": "2027-04-04T12:00:00+09:00"}
    )
    r = await client.patch(f"/v1/trips/{tid}", json={"timezone": "UTC"})
    assert_problem(r, 409, act["id"], "would be on 2027-04-03")
    # Seoul is also +09:00, so nothing changes day.
    r = await client.patch(f"/v1/trips/{tid}", json={"timezone": "Asia/Seoul"})
    assert r.status_code == 200
    got = (await client.get(f"/v1/trips/{tid}/activities/{act['id']}")).json()
    assert got["time"]["startAt"] == "2027-04-03T16:00:00.000Z" and got["date"] == "2027-04-04"
