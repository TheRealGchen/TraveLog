# Travel Planner

An API-first travel planner. The web app is a pure client of a public HTTP API, so anything you
can do in the UI, an AI agent can do through the same API with the same token.

A trip is a collection of days. Each day records where you're staying that night, an optional
place where the day starts, and that day's activities.

```
apps/api         FastAPI + Pydantic + PyMongo (uv project). The only code that touches MongoDB.
apps/web         Next.js (App Router, client only), Tailwind, shadcn/ui, TanStack Query
packages/client  TypeScript client generated from openapi.json (openapi-typescript + openapi-fetch)
openapi.json     The committed API contract, exported from the Pydantic models
```

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 24+, pnpm 10, Docker (for tests and a
local MongoDB), and [just](https://github.com/casey/just) (a command runner; run `just` to
list the recipes).

```bash
cp .env.example .env
```

```bash
just install
```

```bash
just mongo
```

```bash
just dev
```

Then open http://localhost:3001. The API is at http://localhost:8000; its spec is at
http://localhost:8000/openapi.json, interactive docs at http://localhost:8000/docs, and an
agent-oriented guide at http://localhost:8000/llms.txt.

To use MongoDB Atlas instead of `just mongo`, set `MONGODB_URI` to your Atlas connection string.

### Environment variables

All of them live in one `.env` at the repo root (see `.env.example`). The justfile loads and
exports it, and the web app's `next.config.ts` reads it.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `MONGODB_URI` | API | MongoDB connection string (Atlas or `mongodb://localhost:27017`). Required. |
| `MONGODB_DB` | API | Database name. Default `travel_planner`. |
| `API_TOKEN` | API, web | The bearer token every caller must send. Required. |
| `API_URL` | web | Where the browser reaches the API. Default `http://localhost:8000`. |
| `LINK_PREVIEWS` | API | Fetch a title, image, and icon when a link is pinned. Default `true`. |
| `WEB_ORIGIN` | API | Origin(s) allowed by CORS, comma-separated. Default `http://localhost:3001`. |

## Commands

| Command | What it does |
| --- | --- |
| `just dev` | API (with reload) and web app together |
| `just test` | Lint, type-check, contract drift checks, API tests, web unit tests |
| `just e2e` | Playwright smoke test (starts its own API and a production web build) |
| `just openapi` | Re-export `openapi.json` from the API |
| `just gen-client` | Regenerate `packages/client/src/schema.ts` from `openapi.json` |

When you change an API model or route, run `just openapi gen-client` and commit both files.
`just test` (and CI) fails if either is stale.

API tests run against a throwaway MongoDB container (testcontainers), so Docker must be running.

## Using the API with curl

Every `/v1` request needs `Authorization: Bearer $API_TOKEN`. Timestamps go in with an offset
(`+09:00` or `Z`) and always come back in UTC; dates are calendar days in the trip's timezone.

```bash
export API=http://localhost:8000/v1 TOKEN=change-me
```

Each step below uses IDs from earlier responses; export them as `TRIP`, `TRAVELER`, and
`ACTIVITY` as you go.

Create a trip in Tokyo:

```bash
curl -s -X POST $API/trips -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name": "Japan 2027", "destination": "Tokyo & Kyoto", "timezone": "Asia/Tokyo", "startDate": "2027-04-02", "endDate": "2027-04-14"}'
```

Add a traveler. Only `name` is required; the response is the trip, with the new traveler last
in `travelers`:

```bash
curl -s -X POST $API/trips/$TRIP/travelers -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name": "Sam Lee", "email": "sam@example.com", "passportNumber": "X12345678"}'
```

Or add several at once. It's all or nothing: if any row is invalid, nothing is added and each
error names its row (for example `body.travelers.1.email`):

```bash
curl -s -X POST $API/trips/$TRIP/travelers/batch -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"travelers": [{"name": "Ana Ruiz", "email": "ana@example.com"}, {"name": "Kai"}]}'
```

Pin a link to the trip. The API fetches the page's title, preview image, and icon:

```bash
curl -s -X POST $API/trips/$TRIP/links -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"url": "https://www.japan-guide.com/e/e3011.html"}'
```

Set where you're staying on April 3 and where the day starts:

```bash
curl -s -X PATCH $API/trips/$TRIP/days/2027-04-03 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"lodging": {"name": "Hotel Gracery Shinjuku"}, "startLocation": {"name": "Narita Airport"}}'
```

Add an activity to that day from 10:00 to 12:00 Tokyo time (stored as 01:00Z to 03:00Z):

```bash
curl -s -X POST $API/trips/$TRIP/days/2027-04-03/activities -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"title": "teamLab Planets", "time": {"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"}, "location": {"name": "Toyosu"}, "travelerIds": ["'$TRAVELER'"]}'
```

Move it to April 5, keeping 10:00 to 12:00 local time:

```bash
curl -s -X POST $API/trips/$TRIP/activities/$ACTIVITY/move -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"date": "2027-04-05"}'
```

Read the whole trip day by day (every day with its lodging, start location, and activities):

```bash
curl -s $API/trips/$TRIP/days -H "Authorization: Bearer $TOKEN"
```

Errors are `application/problem+json` and say how to fix the request, for example a timestamp
without an offset:

```json
{
  "type": "/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "detail": "1 validation error: body.time.startAt: must include a UTC offset or 'Z', for example 2027-04-03T10:00:00+09:00 (got '2027-04-03T10:00:00', which has no offset)",
  "errors": [{ "path": "body.time.startAt", "message": "must include a UTC offset or 'Z', ..." }]
}
```

To avoid overwriting someone else's change, send the `ETag` from a previous response as
`If-Match`; a stale ETag returns 412 with the current version.

## Using the API from AI agents (MCP)

The MCP server is a later phase and doesn't exist yet. Until then, agents use the HTTP API
directly:

1. Read `GET /llms.txt` for the data model, time rules, and common workflows.
2. Load `GET /openapi.json` as the tool schema. Every operation has a verb-style `operationId`
   (`create_trip`, `add_activity`, `move_activity`, ...), a summary, and a description on every
   field.
3. Call the API with `Authorization: Bearer <API_TOKEN>`.

For example, "Move teamLab to Saturday and add Ana" is `list_activities` (find the ID),
`move_activity` with `{"date": "2027-04-03"}`, then `update_activity` with the new
`travelerIds`. Each call returns the updated resource, so no extra reads are needed. When the
MCP server lands, it will expose these same operations as tools.

## UI action to API operation

Every UI action is exactly one documented API operation; the web app has no other data path
(ESLint bans importing `mongodb` in `apps/web`).

| UI action | operationId |
| --- | --- |
| Open the trips dashboard | `list_trips` |
| New trip dialog, Create | `create_trip` |
| Open a trip page (header, travelers) | `get_trip` |
| Edit trip dialog, Save; header date range picker | `update_trip` |
| Edit trip dialog, Delete trip | `delete_trip` |
| Days tab (the grid of day cards) | `list_days` |
| Open a day card (day page) | `get_day` |
| Day page, "Staying tonight" / "Starting from" | `update_day` |
| "Pin link" (chips below the travelers row) | `add_link` |
| Link chip pencil, Save (title, URL) | `update_link` |
| Link chip pencil, Unpin | `remove_link` |
| Add traveler | `add_traveler` |
| Add traveler, "Add multiple…" (paste box) | `add_travelers` |
| Traveler chip, Save (name, email, passport number, color) | `update_traveler` |
| Traveler chip, Remove | `remove_traveler` |
| Things to do tab and its status and traveler filters | `list_activities` |
| Day page, "Add an activity…" | `add_activity` |
| Activity editor, Save; status picker on a card | `update_activity` |
| Activity editor, Day select | `move_activity` |
| Activity editor, Delete | `delete_activity` |
| (agents only) | `get_activity` |

The open trip and day pages poll every 10 seconds and refetch on window focus, so changes made
by agents show up without a reload. Status changes are optimistic and roll back with a toast
showing the API's `detail` if they fail.

Design choices and assumptions are in [DECISIONS.md](DECISIONS.md).
