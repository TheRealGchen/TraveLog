# Travel Planner: Implementation Plan for an Agent

An API-first travel planning app. Every action available in the UI must also be available through the public API, so AI tools have full parity with the frontend. An MCP server is planned as a later phase.

## 0. How to use this document

You are an implementation agent. Work through the phases in order. Finish each phase's acceptance checks before starting the next. Do not add features, libraries or abstractions that are not listed here. If something is ambiguous, pick the simplest option, note the assumption in `DECISIONS.md`, and continue.

## 1. Non-negotiable principles

1. **API-first.** The frontend never imports `mongodb` and never touches the database. Every read and write is an HTTP call to the API.
2. **No UI-only endpoints.** If a screen needs data in a particular shape, add a public endpoint for it.
3. **Business logic lives in the API.** Validation, defaults, sorting, grouping and status rules are server-side.
4. **One source of truth for shapes.** Pydantic models in `apps/api` define the database document and the API requests and responses. FastAPI turns them into the OpenAPI spec, which is the public contract. The TypeScript client is generated from that spec, never written by hand.
5. **One auth path.** Bearer token for the UI and for agents alike. No internal-only auth.
6. **Every mutation returns the updated resource** so callers can confirm the result without a second request.
7. **Errors are actionable.** A caller should be able to fix its request from the error message alone.

## 2. Stack

| Layer | Choice |
| --- | --- |
| Backend language | Python 3.15+, managed with `uv` |
| Frontend language | TypeScript (frontend only) |
| Repo | Simple monorepo: `apps/api` is a `uv` project; `apps/web` and `packages/client` use pnpm; a root `Makefile` holds the common commands (`dev`, `test`, `gen-client`) |
| Frontend | Next.js (App Router, used as a pure client; no Server Actions, no route handlers that touch data), Tailwind, shadcn/ui, react-day-picker, date-fns, TanStack Query, Framer Motion (optional) |
| API client | `openapi-typescript` + `openapi-fetch`, generated from the API's OpenAPI spec |
| Backend | FastAPI with Pydantic v2, served by uvicorn |
| Database | MongoDB (Atlas free tier) via PyMongo's async API (`AsyncMongoClient`, `tz_aware=True`), with separate `trips` and `activities` collections (one document per trip, one per activity) |
| AI access | `/openapi.json` and `/llms.txt` (an MCP server is planned as a later phase) |
| Testing | `pytest` + `pytest-asyncio` + `httpx` against a throwaway MongoDB (Docker via `testcontainers`); Playwright for one end-to-end smoke test |
| Python tooling | `ruff` (lint and format), `t``y` (types) |
| IDs | Prefixed ULIDs (`python-ulid`): `trip_`, `trv_`, `act_` |

## 3. Repository layout

```
travel-planner/
  apps/
    api/              FastAPI + Pydantic + PyMongo (uv project)
      src/travel_api/
        main.py       app factory, lifespan, routers
        config.py     settings from environment
        auth.py       bearer-token dependency
        errors.py     problem+json exception handlers
        db.py         Mongo client and indexes
        models/       Pydantic models (Trip, Traveler, Activity, requests, responses)
        repository/   all Mongo access: trips.py, activities.py (atomic operators only)
        routes/       trips.py, travelers.py, activities.py
      scripts/        export_openapi.py
      tests/
    web/              Next.js, depends only on the generated client
  packages/
    client/           Generated TypeScript client (openapi-typescript output)
  openapi.json        Committed export of the API spec (the contract)
  Makefile
  DECISIONS.md
  README.md
```

Enforce the boundary with a lint rule: in `apps/web`, an ESLint `no-restricted-imports` rule bans `mongodb`. Only `apps/api` may import a database driver.

## 4. Data model

Two MongoDB collections: `trips` and `activities`. A trip document holds the trip and its travelers. Each activity is its own document that points to its trip with `tripId`, so activities can grow (more fields, bookings, costs) without enlarging or contending on the trip document.

```json
{
  "_id": "trip_01J...",
  "schemaVersion": 1,
  "ownerId": null,
  "name": "Japan 2027",
  "destination": "Tokyo & Kyoto",
  "timezone": "Asia/Tokyo",
  "startDate": "2027-04-02",
  "endDate": "2027-04-14",
  "travelers": [
    { "id": "trv_01J...", "name": "Sam", "color": "#6366f1" }
  ],
  "createdAt": "2026-10-17T12:00:00.000Z",
  "updatedAt": "2026-10-17T12:00:00.000Z"
}
```

An activity, in the `activities` collection (the times below are 10:00 to 12:00 in Tokyo, stored as UTC):

```json
{
  "_id": "act_01J...",
  "schemaVersion": 1,
  "tripId": "trip_01J...",
  "title": "teamLab Planets",
  "status": "planned",
  "schedule": {
    "date": "2027-04-03",
    "startAt": "2027-04-03T01:00:00.000Z",
    "endAt": "2027-04-03T03:00:00.000Z"
  },
  "location": { "name": "Toyosu" },
  "notes": "Book tickets ahead",
  "travelerIds": ["trv_01J..."],
  "createdAt": "2026-10-17T12:00:00.000Z",
  "updatedAt": "2026-10-17T12:00:00.000Z"
}
```

Rules:

- **Timestamps are UTC.** Every timestamp is stored in UTC as a real MongoDB `Date`. The API accepts ISO 8601 timestamps with an explicit offset or `Z` (for example `2027-04-03T10:00:00+09:00`), converts them to UTC, and always returns UTC with a trailing `Z`. Conversion to local time happens at display time, using the trip's `timezone`.
- **`timezone`** is a required IANA name on every trip (for example `Asia/Tokyo`), validated on write and defaulting to `UTC`. Changing it never moves an activity's UTC instants; the API recomputes each timed activity's `schedule.date` in the same request.
- **Trip dates** (`startDate`, `endDate`) are calendar dates (`YYYY-MM-DD`) in the trip's timezone, not timestamps.
- Each activity is its own document in `activities` with a `tripId`. Activity routes stay nested under the trip, and every activity query filters on `{ _id, tripId }`, so an activity ID under the wrong trip returns 404. Deleting a trip deletes its activities.
- Related activity fields are grouped in nested objects (`schedule`, `location`), so new fields (address, coordinates, booking details, cost) can be added inside them without changing the top-level shape.
- `schedule.date` is the activity's calendar day in the trip's timezone and is nullable. `null` means unscheduled (an idea with no day yet). When `startAt` is set, the API derives `date` from it, so the two can never disagree. A date with no times is an all-day activity.
- `schedule.startAt` and `schedule.endAt` are nullable UTC timestamps. `endAt` requires `startAt` and must be later than it.
- `status` is one of `idea`, `planned`, `done`.
- `travelerIds` must reference travelers on the same trip. Removing a traveler removes their ID from every activity of that trip (one `updateMany` with `$pull`).
- `endDate` must be on or after `startDate`. Scheduled activity dates should fall within the trip range (reject with a clear error, or allow with a `warnings` entry; pick one, document it in `DECISIONS.md`).
- `createdAt` and `updatedAt` are stored as `Date` (UTC) and serialized as ISO 8601 strings with `Z`.
- `schemaVersion` is on every document, trips and activities. Migrate lazily in the API read path (upgrade old documents in code when read) rather than with bulk migrations.
- **Days until trip** is never stored. Compute it from `startDate` in the trip's timezone.

Indexes: on `trips`, `{ ownerId: 1, startDate: 1 }`; on `activities`, `{ tripId: 1, "schedule.startAt": 1 }` and `{ tripId: 1, "schedule.date": 1 }`.

## 5. API surface

Base path `/v1`. Every route sets a verb-style `operation_id` (it appears as `operationId` in the OpenAPI spec), a summary, and a `Field(description=...)` on every Pydantic field. Agents read these.

### Trips

| operationId | Method and path | Notes |
| --- | --- | --- |
| `list_trips` | `GET /trips` | Summary view. Includes `daysUntilStart`, `status` (`upcoming`, `ongoing`, `past`), traveler count. Query: `status`, `sort`. |
| `create_trip` | `POST /trips` | Required: name, startDate, endDate. Optional: destination, timezone (IANA name, default `UTC`). |
| `get_trip` | `GET /trips/{tripId}` | The trip document, including travelers (activities are fetched separately), plus computed `daysUntilStart`. Returns `ETag`. |
| `update_trip` | `PATCH /trips/{tripId}` | Partial update. Supports `If-Match`. Changing `timezone` recomputes `schedule.date` on timed activities. |
| `delete_trip` | `DELETE /trips/{tripId}` | Also deletes the trip's activities. |
| `get_itinerary` | `GET /trips/{tripId}/itinerary` | One entry per day in the trip range (including empty days), grouped by date in the trip's timezone, each with its activities sorted by `schedule.startAt` (nulls last). Plus the trip's `timezone`, an `unscheduled` list, and `daysUntilStart`. Times are UTC. |

### Travelers

| operationId | Method and path |
| --- | --- |
| `add_traveler` | `POST /trips/{tripId}/travelers` |
| `update_traveler` | `PATCH /trips/{tripId}/travelers/{travelerId}` |
| `remove_traveler` | `DELETE /trips/{tripId}/travelers/{travelerId}` |

If `color` is omitted on add, assign the next color from a fixed palette.

### Activities

| operationId | Method and path | Notes |
| --- | --- | --- |
| `list_activities` | `GET /trips/{tripId}/activities` | Query filters: `date` (a day in the trip's timezone), `unscheduled=true`, `travelerId`, `status`. |
| `add_activity` | `POST /trips/{tripId}/activities` | Required: title. Optional: `schedule` (`date`, `startAt`, `endAt`), `location`, `notes`, `status`, `travelerIds`. Timestamps are ISO 8601 with an offset or `Z`. |
| `get_activity` | `GET /trips/{tripId}/activities/{activityId}` | Returns `ETag`. |
| `update_activity` | `PATCH /trips/{tripId}/activities/{activityId}` | Partial update. Supports `If-Match`. |
| `move_activity` | `POST /trips/{tripId}/activities/{activityId}/move` | Body: `date` (nullable), optional `startAt` and `endAt`. If the times are omitted while `date` changes, the API keeps each time of day (in the trip's timezone) and moves it to the new day. Convenience for drag and drop and for agents. |
| `delete_activity` | `DELETE /trips/{tripId}/activities/{activityId}` |  |

### Cross-cutting behavior

- **Atomic updates only.** Use single-document atomic operators (`$set`, `$push`, `$pull`, with `arrayFilters` for travelers on the trip). Never read a document, edit it in Python, and write it back.
- **Optimistic concurrency.** Every trip and activity response includes an `ETag` derived from that document's `updatedAt`. Mutations accept `If-Match`; on mismatch return `412` with the current version. `If-Match` is optional, so simple callers still work.
- **Time in, time out.** Request timestamps must be ISO 8601 with an offset or `Z`; a timestamp without an offset is rejected with a message saying so. Responses are always UTC.
- **Auth.** `Authorization: Bearer <token>`. For now, compare against `API_TOKEN` from the environment. Keep the check in one middleware so per-user tokens can replace it later.
- **Errors** use RFC 9457 `application/problem+json`: `type`, `title`, `status`, `detail`, and an `errors` array with `path` and `message` for validation failures. Messages must be specific, e.g. `endAt must be after startAt (got 2027-04-03T02:00:00Z and 2027-04-03T01:00:00Z)`.
- **IDs and 404s.** Unknown trip, traveler, or activity IDs return `404` with a message naming which ID was not found.
- **Public discovery.** Serve `GET /openapi.json` and `GET /llms.txt` (a plain-language description of the API, the data model, and common workflows) without authentication.
- **CORS** allows the web app's origin.

## 6. Frontend spec

Visual direction: clean, light, generous whitespace, rounded cards (`rounded-2xl`), soft shadows, one accent color, large clear typography. Cards are easy to click: the whole card is the target, with a subtle lift on hover and a visible focus ring. Fully responsive, and good on mobile.

**Trips dashboard (`/`)**

- Grid of trip cards. Each shows name, destination, date range, a countdown badge (`12 days to go`, `Today!`, `In progress`, or `Completed`), and overlapping traveler avatars (initials on the traveler's color).
- A "New trip" card opens a dialog with name, destination, timezone (a searchable IANA timezone select, defaulting to the browser's), and a date range picker (react-day-picker in range mode inside a popover).

**Trip page (`/trips/[tripId]`)**

- Header: name, destination, date range (editable via the same range picker), a large countdown, and a traveler row with an "Add traveler" button (name input, color auto-assigned).
- Tabs: **Itinerary** and **Things to do**.
- **Itinerary tab:** one section per day from `get_itinerary`, with a day header (`Day 3, Thu Apr 4`), activity cards sorted by start time showing the time range, title, location, and traveler avatars. Empty days show a friendly "Nothing planned" row with an "Add" action. An **Unscheduled** section lists activities with no date.
- **Things to do tab:** a flat list of all activities with filters (status, traveler). Each row shows title, date, and time range.
- **Activity dialog** (opened by clicking any activity card): title, date (calendar picker limited to the trip range, clearable), start time and end time, location, notes, status, and traveler multi-select. Saves with `update_activity`; has a delete action with confirmation.
- Drag and drop (dnd-kit) from Unscheduled onto a day, or between days, calls `move_activity`. Add this in the last phase; the dialog is the primary way to change the date.

**Data fetching**

- All calls go through the generated `openapi-fetch` client. Wrap them in TanStack Query hooks.
- Refetch on window focus, and poll the open trip every 10 seconds so edits made by AI agents appear in the UI.
- Use optimistic updates for moves and status changes, rolling back on error and showing a toast with the API's `detail` message.
- Dates in the UI: use `date-fns` with plain `YYYY-MM-DD` strings; never construct `Date` objects from them in the local timezone without care (parse as local calendar dates).
- Times in the UI: the API returns UTC. Convert to the trip's `timezone` for display, and convert the user's chosen local time back to UTC before sending, using `@date-fns/tz` (`TZDate`). Show the timezone name in the trip header and in the activity dialog. Never use the browser's timezone for trip times.

## 7. Implementation phases

### Phase 1: Foundations

1. Create the repo layout from section 3. Set up `apps/api` as a `uv` project (Python 3.12; FastAPI, pydantic, pymongo, python-ulid, uvicorn, pytest, pytest-asyncio, httpx, ruff) and `apps/web` with pnpm. Add the lint rule, the `Makefile`, and a README stub.
2. In `apps/api/src/travel_api/models`, write the Pydantic v2 models for `Trip`, `Traveler`, `Activity` (with nested `Schedule` and `Location` models), and every request and response body (create, patch, move, itinerary). Set `extra="forbid"` so typos are rejected, and add a `Field(description=...)` to every field.
3. Model trip `startDate` and `endDate` as `YYYY-MM-DD` strings with pattern validation. Model every timestamp (`schedule.startAt`, `schedule.endAt`, `createdAt`, `updatedAt`) as a timezone-aware `datetime`: normalize every incoming value to UTC and reject values with no offset. Validate `timezone` as an IANA name with `zoneinfo`. Add validators for `endDate >= startDate` and `endAt > startAt`.
4. Make PATCH models all-optional and apply them with `model_dump(exclude_unset=True)`, so an explicit `null` (for example, un-scheduling an activity) is different from an omitted field.
5. Create `DECISIONS.md` and `.env.example` (`MONGODB_URI`, `API_TOKEN`, `API_URL`, `WEB_ORIGIN`).

**Acceptance:** `uv run ruff check` and `uv run pytest` pass; model tests cover the date, UTC-timestamp, timezone, and `null`-versus-omitted rules.

### Phase 2: API

1. FastAPI app with a lifespan that opens one `AsyncMongoClient` (with `tz_aware=True`, so datetimes come back as UTC-aware values) and creates indexes, a bearer-token dependency, exception handlers that return problem+json (including turning FastAPI's validation errors into the `errors` array), and CORS.
2. The `trips` and `activities` repositories in `repository/`. All writes use single-document atomic operators (`$set`, `$push`, `$pull`), never read-modify-write. Deleting a trip deletes its activities; removing a traveler `$pull`s their ID from the trip's activities.
3. Implement all trip, traveler, and activity routes from section 5, including `get_itinerary`, `move_activity`, ETag and `If-Match`.
4. Serve `/openapi.json` (FastAPI's built-in) and `/llms.txt`. Add `scripts/export_openapi.py` that writes the spec to the root `openapi.json`, and make `make test` fail if the committed file is out of date.
5. Tests with `pytest` and `httpx.AsyncClient` (ASGI transport) against a throwaway MongoDB: each route's happy path; validation failures (bad date, `endAt` before `startAt`, a timestamp with no offset, an invalid timezone, an unknown traveler ID); a `+09:00` timestamp is stored as UTC and returned with `Z`; an activity under the wrong trip returns 404; deleting a trip deletes its activities; removing a traveler cleans up activities; concurrent `add_activity` calls both land; `If-Match` mismatch returns 412; itinerary includes empty days, groups by the trip's timezone, and sorts by time.

**Acceptance:** all tests pass; every operation in section 5 is present in `/openapi.json` with the correct `operationId`; the whole flow (create trip, add travelers, add and move activities, read itinerary) works using only `curl`.

### Phase 3: Generated client and frontend shell

1. In `packages/client`, add a script that runs `openapi-typescript` against the root `openapi.json` and exports a configured `openapi-fetch` client. `make gen-client` runs it, and CI fails if regenerating changes the committed output.
2. Next.js app with Tailwind and shadcn/ui; TanStack Query provider; token read from an env var.
3. Build the trips dashboard with trip cards and the new-trip dialog with the date range picker.

**Acceptance:** creating a trip in the UI and then fetching it with `curl` returns the same data; no `mongodb` import exists in `apps/web`.

### Phase 4: Trip page

1. Add a small `lib/time.ts` helper that converts UTC timestamps to the trip's `timezone` for display and converts local picks back to UTC for requests, with unit tests that run in a timezone different from the machine's.
2. Header with countdown and traveler row (add and remove travelers).
3. Itinerary tab driven by `get_itinerary`, including the Unscheduled section.
4. Activity dialog for create, edit, and delete. Things to do tab with filters.
5. Polling, focus refetch, optimistic updates, and error toasts.

**Acceptance:** every UI action maps to exactly one documented API operation; editing a trip with `curl` while the page is open shows the change within about 10 seconds.

### Phase 5: Polish

1. Drag and drop with dnd-kit calling `move_activity`.
2. Framer Motion card hover and expand animations; loading skeletons; empty states.
3. Playwright smoke test: create a trip, add a traveler and an activity, verify the countdown and the itinerary.
4. README with setup, environment variables, and a worked example for both `curl` and MCP.

**Acceptance:** the Playwright test passes; a new developer can run everything from the README.

## 8. Definition of done

- Everything in the UI can be done through the public API, and there is a test or a checklist in the README mapping each UI action to its `operationId`.
- `/openapi.json` is complete, accurate, and well described.
- No database code exists outside `apps/api`.
- Times and dates behave correctly for a trip in a timezone different from the machine running the app.

## 9. Explicitly out of scope for now

The MCP server (its own later phase), user accounts and login, per-user permissions, sharing links, maps and geocoding, file uploads, real-time WebSockets or SSE (polling is enough), budgets and expenses, and notifications.

Design choices to keep in mind so these stay easy later: nullable `ownerId`, the single auth middleware, and the optional `userId` on travelers when accounts arrive. A `GET /trips/{tripId}/events` SSE endpoint is the natural next step for live updates.
