import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import {
  collectContext,
  elementFromDataset,
  lastElement,
  recordApiFailure,
  recordElement,
  recordEtag,
  recordPageError,
  resetFeedbackState,
  routePattern,
} from "./feedback.ts";

const DAY_PAGE = {
  pathname: "/trips/trip_01ABC/days/2027-04-03",
  params: { tripId: "trip_01ABC", date: "2027-04-03" },
};

beforeEach(resetFeedbackState);

test("route patterns replace param values with their names", () => {
  assert.equal(routePattern(DAY_PAGE.pathname, DAY_PAGE.params), "/trips/[tripId]/days/[date]");
  assert.equal(routePattern("/", {}), "/");
  assert.equal(routePattern("/trips/a%20b", { tripId: "a b" }), "/trips/[tripId]");
  assert.equal(routePattern("/docs/a/b", { slug: ["a", "b"] }), "/docs/[...slug]");
});

test("the page and its records are always attached", () => {
  const choices = collectContext({ ...DAY_PAGE, viewport: "390x844", theme: "dark" }, null);
  assert.deepEqual(
    choices.map((c) => c.item),
    [
      {
        type: "web.page",
        route: "/trips/[tripId]/days/[date]",
        path: DAY_PAGE.pathname,
        viewport: "390x844",
        theme: "dark",
        build: null,
      },
      { type: "entity", id: "trip_01ABC", etag: null },
    ],
  );
  assert.equal(choices[0].label, "Page /trips/[tripId]/days/[date]");
});

test("a picked element adds itself and its record, with a remembered ETag", () => {
  recordEtag("/v1/trips/trip_01ABC/activities/act_01XYZ", '"17"');
  recordEtag("/v1/trips/trip_01ABC/days/2027-04-03", '"99"');
  const element = elementFromDataset({
    feedback: "ActivityCard",
    feedbackLabel: "teamLab",
    feedbackId: "act_01XYZ",
  });
  const items = collectContext(DAY_PAGE, element).map((c) => c.item);
  assert.deepEqual(items[1], { type: "web.element", component: "ActivityCard", label: "teamLab" });
  assert.deepEqual(items.at(-1), { type: "entity", id: "act_01XYZ", etag: '"17"' });
  // A day's ETag isn't mistaken for the trip's: the path doesn't end in an ID.
  assert.deepEqual(items.at(-2), { type: "entity", id: "trip_01ABC", etag: null });
});

test("untagged elements are ignored", () => {
  assert.equal(elementFromDataset({}), null);
});

test("the last element only counts on the page it was touched on", () => {
  recordElement({ component: "DayCard" }, "/trips/trip_01ABC");
  assert.deepEqual(lastElement("/trips/trip_01ABC"), { component: "DayCard" });
  assert.equal(lastElement("/"), null);
  recordElement(null, "/trips/trip_01ABC");
  assert.equal(lastElement("/trips/trip_01ABC"), null);
});

test("recent errors and failed requests are kept, five of each, newest last", () => {
  for (let i = 0; i < 7; i++) {
    recordPageError({ message: `boom ${i}` });
    recordApiFailure({ operationId: "update_activity", status: 400 + i, errorPaths: [] });
  }
  recordPageError({ message: "boom 6" }); // repeated: not kept twice
  const items = collectContext({ pathname: "/", params: {} }, null).map((c) => c.item);
  const errors = items.filter((i) => i.type === "web.error");
  const requests = items.filter((i) => i.type === "api.request");
  assert.deepEqual(
    errors.map((e) => e.message),
    ["boom 2", "boom 3", "boom 4", "boom 5", "boom 6"],
  );
  assert.deepEqual(
    requests.map((r) => r.status),
    [402, 403, 404, 405, 406],
  );
});

test("long values are clipped to the API's limits", () => {
  recordPageError({ message: "x".repeat(5000), stack: "y".repeat(5000) });
  const [, error] = collectContext({ pathname: "/", params: {} }, null);
  assert.equal(error.item.type, "web.error");
  if (error.item.type !== "web.error") return;
  assert.equal(error.item.message.length, 1000);
  assert.equal(error.item.stack?.length, 3000);
});
