// Run with a TZ that differs from every trip timezone used here (see the "test" script), so a
// helper that leaks the machine's timezone fails.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  countdownLabel,
  dateParts,
  formatDateOnly,
  formatDateRange,
  formatDayHeader,
  formatLongDate,
  formatTimeRange,
  localRangeToUtc,
  localToUtc,
  parseDateOnly,
  utcToLocalDate,
  utcToLocalTime,
} from "./time.ts";

test("runs in a timezone other than the trip timezones", () => {
  const machine = Intl.DateTimeFormat().resolvedOptions().timeZone;
  assert.notEqual(machine, "Asia/Tokyo");
  assert.notEqual(machine, "UTC");
});

test("UTC instants display in the trip timezone", () => {
  assert.equal(utcToLocalTime("2027-04-03T01:00:00.000Z", "Asia/Tokyo"), "10:00");
  assert.equal(utcToLocalTime("2027-04-03T01:00:00.000Z", "America/New_York"), "21:00");
  assert.equal(utcToLocalDate("2027-04-03T23:30:00.000Z", "Asia/Tokyo"), "2027-04-04");
  assert.equal(utcToLocalDate("2027-04-03T01:00:00.000Z", "America/New_York"), "2027-04-02");
});

test("local picks convert back to UTC", () => {
  assert.equal(localToUtc("2027-04-03", "10:00", "Asia/Tokyo"), "2027-04-03T01:00:00.000Z");
  assert.equal(localToUtc("2027-04-04", "00:30", "Asia/Tokyo"), "2027-04-03T15:30:00.000Z");
  // DST in New York: 19:00 is 00:00Z before 14 Mar 2027 and 23:00Z after.
  assert.equal(localToUtc("2027-03-12", "19:00", "America/New_York"), "2027-03-13T00:00:00.000Z");
  assert.equal(localToUtc("2027-03-15", "19:00", "America/New_York"), "2027-03-15T23:00:00.000Z");
});

test("round trip is stable", () => {
  const iso = localToUtc("2027-11-07", "01:30", "Europe/Paris");
  assert.equal(utcToLocalTime(iso, "Europe/Paris"), "01:30");
  assert.equal(utcToLocalDate(iso, "Europe/Paris"), "2027-11-07");
});

test("an end time before the start time is on the next day", () => {
  assert.deepEqual(localRangeToUtc("2027-04-03", "22:00", "01:00", "Asia/Tokyo"), {
    startAt: "2027-04-03T13:00:00.000Z",
    endAt: "2027-04-03T16:00:00.000Z",
  });
  assert.deepEqual(localRangeToUtc("2027-04-03", "10:00", null, "Asia/Tokyo"), {
    startAt: "2027-04-03T01:00:00.000Z",
    endAt: null,
  });
});

test("time ranges", () => {
  const tz = "Asia/Tokyo";
  assert.equal(formatTimeRange(null, null, tz), "Any time");
  assert.equal(formatTimeRange("2027-04-03T01:00:00.000Z", null, tz), "10:00");
  assert.equal(
    formatTimeRange("2027-04-03T01:00:00.000Z", "2027-04-03T03:00:00.000Z", tz),
    "10:00 – 12:00",
  );
  assert.equal(
    formatTimeRange("2027-04-03T13:00:00.000Z", "2027-04-03T16:00:00.000Z", tz),
    "22:00 – 01:00 (+1)",
  );
});

test("calendar dates never shift", () => {
  const d = parseDateOnly("2027-04-04");
  assert.equal(d.getDate(), 4);
  assert.equal(formatDateOnly(d), "2027-04-04");
  assert.equal(formatDayHeader(3, "2027-04-04"), "Day 3, Sun Apr 4");
  assert.equal(formatLongDate("2027-04-04"), "Sunday, April 4, 2027");
  assert.deepEqual(dateParts("2027-04-04"), { weekday: "Sun", day: "4", month: "Apr" });
  assert.equal(formatDateRange("2027-04-02", "2027-04-14"), "Apr 2 – 14, 2027");
  assert.equal(formatDateRange("2027-04-28", "2027-05-03"), "Apr 28 – May 3, 2027");
  assert.equal(formatDateRange("2027-12-30", "2028-01-02"), "Dec 30, 2027 – Jan 2, 2028");
});

test("countdown labels", () => {
  assert.equal(countdownLabel(12, "upcoming"), "12 days to go");
  assert.equal(countdownLabel(1, "upcoming"), "1 day to go");
  assert.equal(countdownLabel(0, "ongoing"), "Today!");
  assert.equal(countdownLabel(-3, "ongoing"), "In progress");
  assert.equal(countdownLabel(-30, "past"), "Completed");
});
