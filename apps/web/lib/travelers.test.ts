import assert from "node:assert/strict";
import { test } from "node:test";

import { errorsByRow, parseTravelerLines } from "./travelers.ts";

test("parses comma-separated lines with optional fields", () => {
  assert.deepEqual(
    parseTravelerLines("Sam Lee, sam@example.com, X12345678\n\n  Ana Ruiz , ana@example.com\nKai\n"),
    [
      { name: "Sam Lee", email: "sam@example.com", passportNumber: "X12345678" },
      { name: "Ana Ruiz", email: "ana@example.com" },
      { name: "Kai" },
    ],
  );
});

test("parses tab-separated rows pasted from a spreadsheet", () => {
  assert.deepEqual(parseTravelerLines("Sam\tsam@example.com\tX1 2345\r\nKai\t\tP99999"), [
    { name: "Sam", email: "sam@example.com", passportNumber: "X1 2345" },
    { name: "Kai", passportNumber: "P99999" },
  ]);
});

test("groups API errors by row", () => {
  const rows = errorsByRow([
    { path: "body.travelers.1.email", message: "bad" },
    { path: "body.travelers.1.passportNumber", message: "worse" },
    { path: "body.travelers", message: "too many" },
    { path: "body.travelers.2.passportNumber", message: "passport number X1 is already used" },
  ]);
  assert.deepEqual(rows.get(1), ["email: bad", "passportNumber: worse"]);
  assert.deepEqual(rows.get(2), ["passport number X1 is already used"]);
  assert.deepEqual(rows.get(-1), ["too many"]);
});
