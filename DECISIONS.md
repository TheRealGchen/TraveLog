# Decisions and assumptions

Where the plan was ambiguous, the simplest option was picked and recorded here.

## Stack and tooling

- **Python version.** The stack table says 3.15+, Phase 1 says 3.12. The project uses 3.15
  (`requires-python >= 3.15`, `.python-version` = 3.15) because the stack table is the
  more specific source of truth.
- **Local MongoDB.** Atlas is the target, but `just mongo` starts `mongo:8` in Docker for local
  work, and the tests use a throwaway container via testcontainers. `MONGODB_DB` (default
  `travel_planner`) was added next to the four variables in the plan so tests and e2e can use
  their own databases.
- **One `.env` at the repo root.** The justfile loads and exports it to every recipe, and
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
- **CI** is a GitHub Actions workflow: `just test` (lint, types, contract drift, API tests, web
  unit tests) plus the Playwright smoke test against a MongoDB service.

## Days (the trip as a collection of days)

- **One document per day** in a `days` collection, replacing the `activities` collection.
  Activities are embedded in their day. The document `_id` is `<tripId>_<date>`, so a trip
  can't have two documents for the same date. The API addresses days by date and never exposes
  `_id`.
- **Days are created with the trip** (one per date). Changing the trip's dates adds the new days
  and deletes the dropped ones. A trip with no day documents (made before this change) gets
  them the first time they're read; that is the "migrate on read" path.
- **No unscheduled activities.** Every activity belongs to a day. Statuses `idea | planned |
  done` remain (`idea` now means "maybe"), default `planned`, and never change on their own.
- **The day owns the date.** An activity's `time.startAt` must fall on its day in the trip's
  timezone (422 otherwise, pointing to `move_activity`); `endAt` may run past midnight.
- **Range and timezone changes never move or delete plans silently.** `update_trip` returns 409
  if new dates would drop a day that has lodging, a start location, or activities, or if a new
  timezone would make a timed activity start on a different day (instants are kept in UTC).
  The detail lists what to move or clear first.
- **Activity routes stay flat** (`/trips/{tripId}/activities/{activityId}`) so callers don't need
  the date to edit an activity; only `add_activity` is nested under a day. Every Activity
  response includes its `date`. Activity mutations return the activity; `update_day` returns
  the day.
- **ETags.** A day's `updatedAt` changes whenever the day or any of its activities changes, and
  each activity has its own `updatedAt`. Both work with `If-Match`.
- **Moving across days** writes two documents: it adds the activity to the target day first and
  then removes it from the source. The removal is conditional on the activity being unchanged;
  if that fails, the copy is removed and the move retried, up to three times. A crash between
  the two writes leaves a duplicate, never a lost activity. Moving within a day is one update.
- **The old `activities` collection is not migrated** (it only held test data). It is no longer
  read and can be dropped.

## API behavior

- **PATCH replaces nested objects.** `time`, `location`, `lodging`, and `startLocation` are
  replaced as a whole, so a PATCH never needs to read the current value.
- **PATCH fields that cannot be null** (title, name, status, travelerIds, timezone, dates,
  traveler color) may be omitted but not sent as null; the OpenAPI schema marks them as
  non-nullable and optional. `add_activity`'s `status` works the same way (default `planned`).
- **`move_activity`.** Without `startAt`, each wall-clock time is kept in the trip's timezone on
  the new day (correct across DST changes). With `startAt` and no `endAt`, the duration is
  kept; `endAt: null` clears it.
- **Atomic writes.** Each write is one atomic single-document operation (`$set`, `$push`,
  `$pull`, `arrayFilters`; pipeline updates wrap user values in `$literal`). Validation reads
  (the trip's timezone, travelers, and dates) happen before writes. `move_activity` across days
  is the one two-document write (see above).
- **Cross-collection effects are not transactional.** Deleting a trip, removing a traveler, and
  changing the dates each touch the trip and then its days in a second operation. A crash
  between the two leaves orphaned or missing days (missing days are recreated on read);
  acceptable at this scale.
- **Pinned links live in the trip document** (`links[]`, at most 50, each URL once), like
  travelers. Each link stores your optional `title` separately from the page's `pageTitle`, so
  clearing your title shows the page's title again.
- **Link previews are fetched by the API when a link is pinned** (or its URL changes), not by
  the browser.
  - The API reads `og:title`/`<title>`, `og:image`/`twitter:image`, and an icon (apple touch
    icon, then `rel=icon`, then `/favicon.ico`). If the fetch fails, the link is still pinned
    without a preview.
  - Guarding against server-side request forgery:
    - only http(s) URLs whose host resolves only to public (global) addresses are fetched;
    - every redirect hop (at most 3) is checked again;
    - non-HTML responses are ignored;
    - the timeout is 5 seconds and at most 512 KB is read.
  - Remaining risk: DNS could change between the address check and the connection (DNS
    rebinding). Acceptable for a single-user app; a fetch proxy would close it.
  - Previews aren't refreshed automatically. Changing the URL refetches them.
  - `LINK_PREVIEWS=false` turns fetching off. The tests swap in an offline fetcher, and the
    Playwright run disables fetching.
  - The browser loads preview images and icons straight from their sites, with
    `referrerPolicy="no-referrer"`. A broken image falls back to the icon, then to a globe.
- **Traveler email and passport number** are optional and nullable; only `name` is required.
  - Emails are trimmed, lowercased, and checked with a simple `local@domain.tld` pattern (no
    email-validation dependency).
  - Passport numbers have spaces and dashes removed, are uppercased, and must be 5-20 letters
    or digits. There is no per-country format check.
  - Each must be unique within a trip (422 naming the traveler who already has it).
  - Travelers stored before these fields existed read as null (migrate on read in
    `repository/trips.py:_trip`).
- **Passport numbers are returned in full** wherever travelers appear, including `list_trips`,
  and are stored as plain text, as requested. Masking or encryption can come with user
  accounts.
- **Bulk add (`add_travelers`)** takes 1-50 travelers and is all or nothing.
  - Format errors are caught when the request is validated. Duplicates (within the batch or
    against the trip) are checked next. Both report per-row paths such as
    `body.travelers.1.email`, which the UI maps back to the pasted lines.
  - The append is a single `$reduce` pipeline update. Its filter rejects the write if any
    existing traveler already has one of the new emails or passport numbers, so concurrent adds
    can't create duplicates.
  - `add_traveler` is a batch of one through the same code.
- **New travelers get the first palette color not already used on the trip** (including colors
  assigned earlier in the same batch), cycling when all are used, computed in the same atomic
  update.
- **Traveler mutations return the whole trip** (the resource that changed); `add_traveler`
  returns 201 and the new traveler is the last element of `travelers`.
- **Deletes return 204** with no body (`delete_trip`, `delete_activity`). `remove_traveler`
  returns the updated trip.
- **ETags** are the quoted `updatedAt` in epoch milliseconds. `If-Match` accepts one or more
  ETags or `*`. A mismatch returns 412 with the current version in the problem's `current`
  member and its `ETag` header. Timestamps are truncated to milliseconds (MongoDB's precision)
  so stored and returned values always match.
- **Unknown IDs.** Path IDs return 404 naming the ID, and so does a date outside the trip. A `travelerId` filter on
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
- **Day cards and day pages.** The trip page shows one large card per day (date, lodging, start
  location, an activity preview). A card opens `/trips/{tripId}/days/{date}`. There, lodging and
  start location are always-editable fields that save on Enter or blur. A quick-add box creates
  an activity from just a title. Activity cards expand in place into an editor instead of
  opening a modal.
- **End time at or before start time** in the activity editor is read as the next day
  (22:00 to 01:00).
- **Editors send only changed fields**, so a save doesn't clobber an agent's concurrent edit to
  another field. The UI doesn't send `If-Match`.
- **Traveler colors** are edited with the native color input; automatic colors are assigned by
  the API. Email and passport number are edited in the traveler's chip popover; clearing a field
  sends null.
- **Link chips** sit on the trip page below the travelers row, above the Days and Things to do
  tabs. Clicking a chip opens the link in a new tab; its pencil opens an editor for the title
  and URL, with an Unpin button. The row wraps on wider screens and scrolls sideways on phones.
- **Bulk add** is a paste box: one traveler per line as `Name, email, passport`, with tabs also
  accepted for spreadsheet pastes. The UI only splits lines for the preview; the API does all
  validation.
- **Status** is shown as a small picker on every card (optimistic `update_activity`), rather
  than a done/undone checkbox, so the UI doesn't need status rules of its own.
- **Drag and drop was removed** with the itinerary list. Moving an activity is done with the Day
  select in its editor (`move_activity`).
- **Things to do** links each activity to its day page with `?activity=<id>`, which opens that
  activity's editor.
- **`get_activity`** isn't used by the UI (days and lists already include full activities); it
  exists for agents.
- **Playwright** runs its own API (port 8100, database `travel_planner_e2e`) and a production
  build of the web app (port 3100), with the browser in `America/Los_Angeles` and the trip in
  `Asia/Tokyo`.

## Deployment

- **Target:** a single Ubuntu/Debian node, provisioned from a clone of the repo with
  `just provision <domain> <email>` (`deploy/provision.sh`). It is safe to re-run. `just deploy`
  updates a provisioned node.
- **Services:**
  - the API runs under systemd with uvicorn's `--proxy-headers`, on `127.0.0.1:8000`;
  - the web app runs under systemd as a production Next.js build (`next start`), on
    `127.0.0.1:3001`;
  - both run as the provisioning user and read the repo's `.env` (mode 600).
- **One domain, routed by path.** nginx sends `/v1/`, `/openapi.json`, `/llms.txt`, `/docs`,
  and `/redoc` to the API and everything else to the web app. The browser therefore calls the
  API on the same origin, with no CORS and one certificate. `API_URL` is that domain and is
  baked into the web build, so `just build` must run after `.env` changes (provision and
  deploy both do).
- **HTTPS:**
  - certbot's nginx plugin (`--redirect --keep-until-expiring`) adds TLS and the HTTP→HTTPS
    redirect to the site nginx serves;
  - the `certbot.timer` from the apt package renews the certificate;
  - re-provisioning re-renders the plain-HTTP site and certbot reinstalls the existing
    certificate.
- **Caching:** `/_next/static/` assets are content-hashed, so nginx serves them as cacheable
  for a year and immutable. It replaces Next's header rather than adding a second one, and
  hides `X-Powered-By`.
- **MongoDB** runs in Docker on the node with `--restart unless-stopped`, data in the
  `travel-mongo-data` volume, and the port bound to `127.0.0.1` only. Docker's published ports
  bypass ufw, so binding to all interfaces would expose the unauthenticated database.
  `just mongo` uses the same settings for local development.
- **Root is allowed.** `provision.sh` runs as root or as a sudo user. The services run as
  whoever provisions, and all privileged steps go through an `as_root` helper, because
  minimal root images often have no `sudo`. Running everything as root is accepted for an
  ephemeral server.
- **Automatic deploys** are the `deploy` job in `.github/workflows/ci.yml`:
  - it runs only on `main` (on push, or the manual button), and only after the tests and
    the Playwright run pass;
  - it uses the `production` environment's secrets, so approvals can be required there;
  - `concurrency: production` makes deploys queue rather than overlap or cancel midway;
  - it calls the runner's plain `ssh` (no third-party SSH action handles the key), with the
    host key pinned from a secret (`StrictHostKeyChecking=yes`), and runs `just deploy`;
  - the recommended `authorized_keys` line forces the command and disables PTY and
    forwarding, so a leaked CI key can only redeploy. Tested in a container: other
    commands, shells, and port forwards are refused;
  - `just deploy` restarts the services, without sudo when root, then waits up to 30s for
    `/llms.txt` on the API and `/` on the web app. A broken release fails the job;
  - no automatic rollback: revert on `main`.
- **No access protection**, by choice: the site is open, and the bearer token is visible in the
  web app's JavaScript. HTTP basic auth on the web routes (leaving `/v1` on bearer auth) is
  the simple upgrade when needed.
- **Toolchain** (`scripts/install-tools.sh`, run by `just setup` and by `just provision`):
  - Node 24 from NodeSource;
  - pnpm 10 via npm (without sudo when Node lives in a user directory, as with nvm);
  - uv from Astral's installer (it downloads the Python version the API pins);
  - Docker from apt (`docker.io`), adding the user to the `docker` group;
  - each tool is skipped if already present, so the script is safe on a dev machine;
  - installing needs apt and sudo; elsewhere it says what to install by hand;
  - nginx and certbot are installed by `provision.sh` only;
  - `just` itself must be installed first (`apt-get install just`).
