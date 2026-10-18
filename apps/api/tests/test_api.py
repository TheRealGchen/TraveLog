import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

Json = dict[str, Any]


async def add_activity(client: httpx.AsyncClient, trip_id: str, **body: Any) -> Json:
    r = await client.post(f"/v1/trips/{trip_id}/activities", json=body)
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
        "get_itinerary",
        "add_traveler",
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


async def test_delete_trip_deletes_its_activities(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    await add_activity(client, trip["id"], title="A")
    await add_activity(client, trip["id"], title="B", schedule={"date": "2027-04-03"})
    assert await db.activities.count_documents({"tripId": trip["id"]}) == 2
    r = await client.delete(f"/v1/trips/{trip['id']}")
    assert r.status_code == 204
    assert await db.activities.count_documents({"tripId": trip["id"]}) == 0
    assert_problem(await client.get(f"/v1/trips/{trip['id']}"), 404, trip["id"])


async def test_unknown_trip_is_404_naming_id(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/v1/trips/trip_nope"), 404, "Trip trip_nope not found")
    assert_problem(await client.delete("/v1/trips/trip_nope"), 404, "trip_nope")
    r = await client.post("/v1/trips/trip_nope/activities", json={"title": "x"})
    assert_problem(r, 404, "trip_nope")


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
        f"/v1/trips/{trip['id']}/activities",
        json={
            "title": "x",
            "schedule": {"startAt": "2027-04-03T02:00:00Z", "endAt": "2027-04-03T01:00:00Z"},
        },
    )
    assert_problem(
        r,
        422,
        "body.schedule",
        "endAt must be after startAt (got 2027-04-03T02:00:00.000Z and 2027-04-03T01:00:00.000Z)",
    )


async def test_timestamp_without_offset(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities",
        json={"title": "x", "schedule": {"startAt": "2027-04-03T10:00:00"}},
    )
    assert_problem(r, 422, "body.schedule.startAt", "must include a UTC offset or 'Z'")


async def test_unknown_traveler_id(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities", json={"title": "x", "travelerIds": ["trv_ghost"]}
    )
    assert_problem(r, 422, "body.travelerIds.0", "traveler trv_ghost is not on trip")


async def test_activity_date_outside_trip(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities",
        json={"title": "x", "schedule": {"date": "2027-05-01"}},
    )
    assert_problem(r, 422, "body.schedule.date", "outside the trip (2027-04-02 to 2027-04-14")


async def test_date_must_agree_with_start_at(client: httpx.AsyncClient, trip: Json) -> None:
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities",
        json={
            "title": "x",
            "schedule": {"date": "2027-04-04", "startAt": "2027-04-03T10:00:00+09:00"},
        },
    )
    assert_problem(r, 422, "body.schedule.date", "does not match startAt")


# Activities


async def test_offset_timestamp_is_stored_as_utc_and_returned_with_z(
    client: httpx.AsyncClient, trip: Json, db: Any
) -> None:
    act = await add_activity(
        client,
        trip["id"],
        title="teamLab Planets",
        schedule={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
        location={"name": "Toyosu"},
        notes="Book tickets ahead",
    )
    assert act["id"].startswith("act_")
    assert act["schedule"] == {
        "date": "2027-04-03",
        "startAt": "2027-04-03T01:00:00.000Z",
        "endAt": "2027-04-03T03:00:00.000Z",
    }
    assert act["status"] == "planned"
    doc = await db.activities.find_one({"_id": act["id"]})
    assert doc["schedule"]["startAt"] == datetime(2027, 4, 3, 1, 0, tzinfo=UTC)
    assert doc["schedule"]["startAt"].utcoffset().total_seconds() == 0
    assert isinstance(doc["createdAt"], datetime)


async def test_activity_crud(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    act = await add_activity(client, tid, title="Ramen")
    assert act["status"] == "idea" and act["schedule"]["date"] is None
    url = f"/v1/trips/{tid}/activities/{act['id']}"

    r = await client.get(url)
    assert r.status_code == 200 and r.json() == act and r.headers["ETag"]

    r = await client.patch(url, json={"notes": "Ichiran", "location": {"name": "Shibuya"}})
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "Ichiran" and r.json()["location"] == {"name": "Shibuya"}
    assert r.json()["title"] == "Ramen"

    r = await client.patch(url, json={"notes": None})
    assert r.json()["notes"] is None and r.json()["location"] == {"name": "Shibuya"}

    r = await client.patch(url, json={"schedule": {"date": "2027-04-05"}})
    assert r.json()["schedule"]["date"] == "2027-04-05"
    assert r.json()["status"] == "planned"  # an idea that gets a day becomes planned

    r = await client.patch(url, json={"schedule": None})
    assert r.json()["schedule"] == {"date": None, "startAt": None, "endAt": None}
    assert r.json()["status"] == "idea"

    r = await client.patch(url, json={"status": "done", "schedule": {"date": "2027-04-06"}})
    assert r.json()["status"] == "done"

    r = await client.patch(url, json={"notes": "$where"})
    assert r.json()["notes"] == "$where"  # user text is never an expression

    assert (await client.delete(url)).status_code == 204
    assert_problem(await client.get(url), 404, act["id"])


async def test_activity_under_wrong_trip_is_404(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], title="x")
    other = (
        await client.post(
            "/v1/trips", json={"name": "Other", "startDate": "2027-01-01", "endDate": "2027-01-02"}
        )
    ).json()
    url = f"/v1/trips/{other['id']}/activities/{act['id']}"
    assert_problem(await client.get(url), 404, act["id"], other["id"])
    assert_problem(await client.patch(url, json={"title": "y"}), 404, act["id"])
    assert_problem(await client.post(f"{url}/move", json={"date": None}), 404, act["id"])
    assert_problem(await client.delete(url), 404, act["id"])
    # And it is untouched under its own trip.
    r = await client.get(f"/v1/trips/{trip['id']}/activities/{act['id']}")
    assert r.json()["title"] == "x"


async def test_list_activities_filters(client: httpx.AsyncClient, trip: Json) -> None:
    tid = trip["id"]
    sam = await add_traveler(client, tid, "Sam")
    await add_activity(client, tid, title="Idea")
    await add_activity(client, tid, title="Late", schedule={"startAt": "2027-04-03T18:00:00+09:00"})
    await add_activity(
        client,
        tid,
        title="Early",
        schedule={"startAt": "2027-04-03T08:00:00+09:00"},
        travelerIds=[sam["id"]],
    )
    await add_activity(client, tid, title="Day 1", schedule={"date": "2027-04-02"}, status="done")

    async def titles(**params: Any) -> list[str]:
        r = await client.get(f"/v1/trips/{tid}/activities", params=params)
        assert r.status_code == 200, r.text
        return [a["title"] for a in r.json()["activities"]]

    assert await titles() == ["Day 1", "Early", "Late", "Idea"]
    assert await titles(date="2027-04-03") == ["Early", "Late"]
    assert await titles(unscheduled="true") == ["Idea"]
    assert await titles(unscheduled="false") == ["Day 1", "Early", "Late"]
    assert await titles(travelerId=sam["id"]) == ["Early"]
    assert await titles(status="done") == ["Day 1"]
    r = await client.get(f"/v1/trips/{tid}/activities", params={"travelerId": "trv_ghost"})
    assert_problem(r, 404, "trv_ghost")


async def test_concurrent_add_activity_calls_all_land(
    client: httpx.AsyncClient, trip: Json
) -> None:
    results = await asyncio.gather(
        *(
            client.post(f"/v1/trips/{trip['id']}/activities", json={"title": f"A{i}"})
            for i in range(10)
        )
    )
    assert all(r.status_code == 201 for r in results)
    listed = (await client.get(f"/v1/trips/{trip['id']}/activities")).json()["activities"]
    assert sorted(a["title"] for a in listed) == sorted(f"A{i}" for i in range(10))


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


async def test_move_keeps_time_of_day_in_trip_timezone(
    client: httpx.AsyncClient, trip: Json
) -> None:
    act = await add_activity(
        client,
        trip["id"],
        title="x",
        schedule={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
    )
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}/move"
    r = await client.post(url, json={"date": "2027-04-10"})
    assert r.status_code == 200, r.text
    assert r.json()["schedule"] == {
        "date": "2027-04-10",
        "startAt": "2027-04-10T01:00:00.000Z",
        "endAt": "2027-04-10T03:00:00.000Z",
    }
    assert r.headers["ETag"]


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
        client, trip["id"], title="Show", schedule={"startAt": "2027-03-12T19:00:00-05:00"}
    )
    r = await client.post(
        f"/v1/trips/{trip['id']}/activities/{act['id']}/move", json={"date": "2027-03-15"}
    )
    # 19:00 local after the DST change is 23:00Z instead of 00:00Z.
    assert r.json()["schedule"]["startAt"] == "2027-03-15T23:00:00.000Z"


async def test_move_with_new_start_keeps_duration(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(
        client,
        trip["id"],
        title="x",
        schedule={"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"},
    )
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}/move"
    r = await client.post(url, json={"date": "2027-04-05", "startAt": "2027-04-05T14:00:00+09:00"})
    assert r.json()["schedule"] == {
        "date": "2027-04-05",
        "startAt": "2027-04-05T05:00:00.000Z",
        "endAt": "2027-04-05T07:00:00.000Z",
    }


async def test_move_unschedule_and_reschedule(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], title="x", schedule={"date": "2027-04-03"})
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}/move"
    r = await client.post(url, json={"date": None})
    assert r.json()["schedule"]["date"] is None and r.json()["status"] == "idea"
    r = await client.post(url, json={"date": "2027-04-04"})
    assert r.json()["schedule"] == {"date": "2027-04-04", "startAt": None, "endAt": None}
    assert r.json()["status"] == "planned"
    r = await client.post(url, json={"date": "2027-06-01"})
    assert_problem(r, 422, "body.date", "outside the trip")


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
    r = await client.patch(f"/v1/trips/{tid}/travelers/trv_ghost", json={"name": "x"})
    assert_problem(r, 404, "Traveler trv_ghost not found on trip")
    r = await client.patch(f"/v1/trips/{tid}/travelers/{sam['id']}", json={"color": "red"})
    assert_problem(r, 422, "body.color")


async def test_removing_traveler_cleans_up_activities(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    sam = await add_traveler(client, tid, "Sam")
    ana = await add_traveler(client, tid, "Ana")
    act = await add_activity(client, tid, title="x", travelerIds=[sam["id"], ana["id"]])
    r = await client.delete(f"/v1/trips/{tid}/travelers/{sam['id']}")
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["travelers"]] == [ana["id"]]
    act = (await client.get(f"/v1/trips/{tid}/activities/{act['id']}")).json()
    assert act["travelerIds"] == [ana["id"]]
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


async def test_if_match_on_activity(client: httpx.AsyncClient, trip: Json) -> None:
    act = await add_activity(client, trip["id"], title="x")
    url = f"/v1/trips/{trip['id']}/activities/{act['id']}"
    etag = (await client.get(url)).headers["ETag"]
    assert (
        await client.patch(url, json={"title": "y"}, headers={"If-Match": etag})
    ).status_code == 200
    r = await client.patch(url, json={"title": "z"}, headers={"If-Match": etag})
    assert_problem(r, 412)
    r = await client.post(f"{url}/move", json={"date": None}, headers={"If-Match": etag})
    assert_problem(r, 412)
    assert_problem(await client.delete(url, headers={"If-Match": etag}), 412)
    assert (await client.delete(url, headers={"If-Match": "*"})).status_code == 204


# Itinerary


async def test_itinerary_includes_empty_days_groups_by_timezone_and_sorts(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    # 23:30Z on Apr 3 is 08:30 on Apr 4 in Tokyo.
    await add_activity(client, tid, title="Breakfast", schedule={"startAt": "2027-04-03T23:30:00Z"})
    await add_activity(client, tid, title="All day", schedule={"date": "2027-04-04"})
    await add_activity(
        client, tid, title="Dinner", schedule={"startAt": "2027-04-04T19:00:00+09:00"}
    )
    await add_activity(
        client, tid, title="Lunch", schedule={"startAt": "2027-04-04T12:00:00+09:00"}
    )
    await add_activity(client, tid, title="Someday")

    r = await client.get(f"/v1/trips/{tid}/itinerary")
    assert r.status_code == 200, r.text
    it = r.json()
    assert it["timezone"] == "Asia/Tokyo" and it["daysUntilStart"] == trip["daysUntilStart"]
    assert len(it["days"]) == 13
    assert it["days"][0] == {"date": "2027-04-02", "dayNumber": 1, "activities": []}
    day3 = it["days"][2]
    assert day3["date"] == "2027-04-04" and day3["dayNumber"] == 3
    assert [a["title"] for a in day3["activities"]] == ["Breakfast", "Lunch", "Dinner", "All day"]
    assert it["days"][1]["activities"] == []
    assert [a["title"] for a in it["unscheduled"]] == ["Someday"]


async def test_timezone_change_recomputes_dates_and_keeps_instants(
    client: httpx.AsyncClient, trip: Json
) -> None:
    tid = trip["id"]
    # 01:00 Apr 4 in Tokyo == 16:00Z Apr 3.
    act = await add_activity(
        client, tid, title="x", schedule={"startAt": "2027-04-04T01:00:00+09:00"}
    )
    assert act["schedule"]["date"] == "2027-04-04"
    r = await client.patch(f"/v1/trips/{tid}", json={"timezone": "UTC"})
    assert r.status_code == 200, r.text
    moved = (await client.get(f"/v1/trips/{tid}/activities/{act['id']}")).json()
    assert moved["schedule"] == {
        "date": "2027-04-03",
        "startAt": "2027-04-03T16:00:00.000Z",
        "endAt": None,
    }


async def test_shrinking_trip_with_activities_outside_is_rejected(
    client: httpx.AsyncClient, trip: Json
) -> None:
    act = await add_activity(client, trip["id"], title="Kyoto", schedule={"date": "2027-04-12"})
    r = await client.patch(f"/v1/trips/{trip['id']}", json={"endDate": "2027-04-10"})
    assert_problem(r, 409, act["id"], "Move or unschedule them first")
    r = await client.patch(f"/v1/trips/{trip['id']}", json={"endDate": "2027-04-12"})
    assert r.status_code == 200
