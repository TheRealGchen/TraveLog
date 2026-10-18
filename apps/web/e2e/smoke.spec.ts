import { expect, test } from "@playwright/test";

/** "YYYY-MM-DD" for today plus `days`, in the trip's timezone (Asia/Tokyo). */
function tokyoDate(days: number): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo" }).format(new Date());
  const d = new Date(`${today}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

test("create a trip, add a traveler and an activity, check countdown and itinerary", async ({
  page,
}) => {
  const name = `Smoke ${Date.now()}`;
  const start = tokyoDate(10);
  const end = tokyoDate(13);

  await page.goto("/");
  await page.getByRole("button", { name: "New trip" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Destination").fill("Tokyo");
  await page.getByLabel("Timezone").click();
  await page.getByPlaceholder("Search timezones…").fill("Tokyo");
  await page.getByRole("option", { name: "Asia/Tokyo" }).click();
  await page.getByLabel("Dates").click();
  const calendar = page.locator("[data-slot=popover-content]");
  const day = (iso: string) => calendar.locator(`td[data-day="${iso}"]:not([data-outside]) button`);
  // Move forward a month if the start day isn't shown yet.
  if ((await day(start).count()) === 0) await calendar.getByRole("button", { name: /next/i }).click();
  await day(start).click();
  if ((await day(end).count()) === 0) await calendar.getByRole("button", { name: /next/i }).click();
  await day(end).click();
  await calendar.getByRole("button", { name: "Done" }).click();
  await page.getByRole("button", { name: "Create trip" }).click();

  // Trip page with the countdown computed by the API.
  await expect(page).toHaveURL(/\/trips\/trip_/);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("days to go")).toBeVisible();
  await expect(page.getByText("10", { exact: true })).toBeVisible();

  // Add a traveler.
  await page.getByRole("button", { name: "Add traveler" }).click();
  await page.getByLabel("Name").fill("Sam Lee");
  await page.locator("[data-slot=popover-content]").getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("button", { name: "SL Sam Lee" })).toBeVisible();

  // Add a timed activity on day 2.
  const day2 = page.getByRole("region", { name: /^Day 2,/ });
  await day2.getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Title").fill("teamLab Planets");
  await page.getByLabel("Start time").fill("10:00");
  await page.getByLabel("End time").fill("12:00");
  await page.getByLabel("Location").fill("Toyosu");
  await page.getByRole("dialog").getByRole("button", { name: "Sam Lee" }).click();
  await page.getByRole("button", { name: "Add activity" }).last().click();

  // The itinerary shows it on day 2 at 10:00 Tokyo time, even though the browser is in LA.
  const card = day2.getByRole("button", { name: "Open teamLab Planets" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("10:00 – 12:00");
  await expect(card).toContainText("Toyosu");
  await expect(card).toContainText("Planned");
  await expect(page.getByRole("region", { name: /^Day 1,/ })).toContainText("Nothing planned");
});
