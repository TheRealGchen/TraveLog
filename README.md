# Travel Planner

An API-first travel planner. The web app is a pure client of a public HTTP API, so anything you
can do in the UI, an AI agent can do through the same API with the same token.

```
apps/api         FastAPI + Pydantic + PyMongo (uv project). The only code that touches MongoDB.
apps/web         Next.js (App Router, client only), Tailwind, shadcn/ui, TanStack Query
packages/client  TypeScript client generated from openapi.json (openapi-typescript + openapi-fetch)
openapi.json     The committed API contract, exported from the Pydantic models
```

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node 24+, pnpm 10, Docker (for tests and a
local MongoDB), and make.

```bash
cp .env.example .env
```

```bash
make install
```

```bash
make mongo
```

```bash
make dev
```

Then open http://localhost:3001. The API is at http://localhost:8000; its spec is at
http://localhost:8000/openapi.json, interactive docs at http://localhost:8000/docs, and an
agent-oriented guide at http://localhost:8000/llms.txt.

To use MongoDB Atlas instead of `make mongo`, set `MONGODB_URI` to your Atlas connection string.

### Environment variables

All of them live in one `.env` at the repo root (see `.env.example`). The Makefile exports it,
and the web app's `next.config.ts` reads it.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `MONGODB_URI` | API | MongoDB connection string (Atlas or `mongodb://localhost:27017`). Required. |
| `MONGODB_DB` | API | Database name. Default `travel_planner`. |
| `API_TOKEN` | API, web | The bearer token every caller must send. Required. |
| `API_URL` | web | Where the browser reaches the API. Default `http://localhost:8000`. |
| `WEB_ORIGIN` | API | Origin(s) allowed by CORS, comma-separated. Default `http://localhost:3001`. |

## Commands

| Command | What it does |
| --- | --- |
| `make dev` | API (with reload) and web app together |
| `make test` | Lint, type-check, contract drift checks, API tests, web unit tests |
| `make e2e` | Playwright smoke test (starts its own API and a production web build) |
| `make openapi` | Re-export `openapi.json` from the API |
| `make gen-client` | Regenerate `packages/client/src/schema.ts` from `openapi.json` |

When you change an API model or route, run `make openapi gen-client` and commit both files.
`make test` (and CI) fails if either is stale.

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

Add a traveler (the response is the trip; the new traveler is last in `travelers`):

```bash
curl -s -X POST $API/trips/$TRIP/travelers -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name": "Sam"}'
```

Add an activity from 10:00 to 12:00 Tokyo time (stored as 01:00Z to 03:00Z; `date` is derived):

```bash
curl -s -X POST $API/trips/$TRIP/activities -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"title": "teamLab Planets", "schedule": {"startAt": "2027-04-03T10:00:00+09:00", "endAt": "2027-04-03T12:00:00+09:00"}, "location": {"name": "Toyosu"}, "travelerIds": ["'$TRAVELER'"]}'
```

Move it to April 5, keeping 10:00 to 12:00 local time:

```bash
curl -s -X POST $API/trips/$TRIP/activities/$ACTIVITY/move -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"date": "2027-04-05"}'
```

Read the day-by-day itinerary (every day of the trip, plus `unscheduled`):

```bash
curl -s $API/trips/$TRIP/itinerary -H "Authorization: Bearer $TOKEN"
```

Errors are `application/problem+json` and say how to fix the request, for example a timestamp
without an offset:

```json
{
  "type": "/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "detail": "1 validation error: body.schedule.startAt: must include a UTC offset or 'Z', for example 2027-04-03T10:00:00+09:00 (got '2027-04-03T10:00:00', which has no offset)",
  "errors": [{ "path": "body.schedule.startAt", "message": "must include a UTC offset or 'Z', ..." }]
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
| Itinerary tab | `get_itinerary` |
| Add traveler | `add_traveler` |
| Traveler chip, Save (name, color) | `update_traveler` |
| Traveler chip, Remove | `remove_traveler` |
| Things to do tab and its status and traveler filters | `list_activities` |
| Add activity / Add on a day / Add idea, then save | `add_activity` |
| Activity dialog, Save; status picker on a card | `update_activity` |
| Drag a card to another day or to Unscheduled | `move_activity` |
| Activity dialog, Delete | `delete_activity` |
| (agents only) | `get_activity` |

The open trip polls every 10 seconds and refetches on window focus, so changes made by agents
show up without a reload. Moves and status changes are optimistic and roll back with a toast
showing the API's `detail` if they fail.

Design choices and assumptions are in [DECISIONS.md](DECISIONS.md).
