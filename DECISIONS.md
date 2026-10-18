# Decisions and assumptions

Where the plan was ambiguous, the simplest option was picked and recorded here.

## Stack and tooling

- **Python version.** The stack table says 3.15+, Phase 1 says 3.12. The project uses 3.15
  (`requires-python >= 3.15`, `.python-version` = 3.15) because the stack table is the
  more specific source of truth.
- **Local MongoDB.** Atlas is the target, but `make mongo` starts `mongo:8` in Docker for local
  work, and the tests use a throwaway container via testcontainers. `MONGODB_DB` (default
  `travel_planner`) was added next to the four variables in the plan so tests and e2e can use
  their own databases.
- **One `.env` at the repo root.** The Makefile exports it to every recipe, and
  `apps/web/next.config.ts` loads it with Node's `process.loadEnvFile`, mapping `API_URL` and
  `API_TOKEN` to `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_API_TOKEN`.
- **The token reaches the browser.** "Token read from an env var" in a pure client app means
  the bearer token is inlined into the JS bundle. That is fine for a single-user, local app;
  per-user tokens replace it when accounts arrive (auth is one dependency, `auth.py`).
- **Web port 3001**, API port 8000. 3000 is often taken by other local tools.
- **Next.js 16 `cacheComponents` is off.** The app is a pure client of the API, so server
  caching adds nothing.
- **Frontend unit tests use `node:test`** (Node 24 runs TypeScript directly), so no extra test
  runner was added. `lib/time.test.ts` runs twice, under `America/Los_Angeles` and
  `Pacific/Kiritimati` (UTC+14).
- **Framer Motion** is imported from its current package name, `motion` (`motion/react`).
- **shadcn/ui** (Radix base, Nova preset). Its CLI now depends on `cn`, shadcn's own
  class-merging package, instead of `clsx` + `tailwind-merge`.
- **CI** is a GitHub Actions workflow: `make test` (lint, types, contract drift, API tests, web
  unit tests) plus the Playwright smoke test against a MongoDB service.

## API behavior

- **Activity days must fall inside the trip** (the plan offered reject or warn): add, update,
  and move reject an out-of-range day with 422. To keep this an invariant, `update_trip`
  rejects date or timezone changes that would strand a scheduled activity with **409**, listing
  each one; move or unschedule them first.
- **`date` and `startAt` that disagree** (the `startAt` falls on another day in the trip's
  timezone) are rejected with 422 rather than silently overwritten.
- **PATCH replaces nested objects.** `schedule` and `location` are replaced as a whole, so a
  PATCH never needs to read the current value. `"schedule": null` unschedules.
- **PATCH fields that cannot be null** (title, name, status, travelerIds, timezone, dates,
  traveler color) may be omitted but not sent as null; the OpenAPI schema marks them as
  non-nullable and optional.
- **Status rules.** New activities default to `planned` with a day and `idea` without one.
  When a write changes the schedule and does not set `status`, an `idea` that gets a day
  becomes `planned` and a `planned` activity that loses its day becomes `idea`; `done` never
  changes on its own.
- **`move_activity`.** Without `startAt`, each wall-clock time is kept in the trip's timezone on
  the new day (correct across DST changes). With `startAt` and no `endAt`, the duration is
  kept; `endAt: null` clears it. `date: null` clears times as well.
- **Atomic writes.** Every write is one atomic single-document operation (`$set`, `$push` via
  `$concatArrays`, `$pull`, `arrayFilters`). User-supplied values in pipeline updates are wrapped
  in `$literal`. Two exceptions, both safe:
  - `move_activity` must read the current times to compute the new ones. It writes with a
    compare-and-set on `updatedAt` and retries up to three times, so a concurrent change is
    never overwritten.
  - Validation reads (the trip's timezone, travelers, and date range) happen before writes.
- **Cross-collection effects are not transactional.** Deleting a trip, removing a traveler, and
  changing the timezone each touch the trip and then its activities in a second operation.
  A crash between the two leaves orphans or stale days; acceptable at this scale.
- **New travelers get the first palette color not already used on the trip**, cycling when all
  are used, computed in the same atomic update.
- **Traveler mutations return the whole trip** (the resource that changed); `add_traveler`
  returns 201 and the new traveler is the last element of `travelers`.
- **Deletes return 204** with no body (`delete_trip`, `delete_activity`). `remove_traveler`
  returns the updated trip.
- **ETags** are the quoted `updatedAt` in epoch milliseconds. `If-Match` accepts one or more
  ETags or `*`. A mismatch returns 412 with the current version in the problem's `current`
  member and its `ETag` header. Timestamps are truncated to milliseconds (MongoDB's precision)
  so stored and returned values always match.
- **Unknown IDs.** Path IDs return 404 naming the ID. A `travelerId` filter on
  `list_activities` that is not on the trip is also 404; unknown IDs in a request body
  (`travelerIds`) are a 422 validation error with the path of the bad entry.
- **Problem types** are relative URIs such as `/problems/validation-error`.
- **`list_trips`** filters by status and sorts in Python, because status depends on each trip's
  timezone. No pagination yet.
- **Creates return a `Location` header** as well as the resource.
- **Schema names.** `separate_input_output_schemas=False` keeps one OpenAPI schema per model.
  Response models declare every field required, so the generated TypeScript types are exact.
- **`schemaVersion` migrations** run in `repository/documents.py:from_document` on read.

## Frontend behavior

- **Countdown text** ("12 days to go", "Today!", "In progress", "Completed") is formatting of
  the API's `daysUntilStart` and `status`; the numbers and status come from the API.
- **End time at or before start time** in the activity dialog is read as the next day
  (22:00 to 01:00).
- **Dialogs send only changed fields**, so a save doesn't clobber an agent's concurrent edit to
  another field. The UI doesn't send `If-Match`.
- **Traveler colors** are edited with the native color input; automatic colors are assigned by
  the API.
- **Status** is shown as a small picker on every card (optimistic `update_activity`), rather
  than a done/undone checkbox, so the UI doesn't need status rules of its own.
- **Drag and drop** uses dnd-kit with `pointerWithin` collision detection (the drop target is
  under the pointer) and a 6px activation distance, so a click still opens the dialog.
- **`get_activity`** isn't used by the UI (the itinerary and lists already include full
  activities); it exists for agents.
- **Playwright** runs its own API (port 8100, database `travel_planner_e2e`) and a production
  build of the web app (port 3100), with the browser in `America/Los_Angeles` and the trip in
  `Asia/Tokyo`.
