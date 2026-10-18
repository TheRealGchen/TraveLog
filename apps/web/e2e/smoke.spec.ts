import { expect, test } from "@playwright/test";

/** "YYYY-MM-DD" for today plus `days`, in the trip's timezone (Asia/Tokyo). */
function tokyoDate(days: number): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo" }).format(new Date());
  const d = new Date(`${today}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

test("create a trip, pin a link, bulk-add travelers, plan a day, check the day cards", async ({
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

  // Pin a link; it shows as a chip below the travelers (no preview offline, so the host shows).
  await page.getByRole("button", { name: "Pin link" }).click();
  await page.getByLabel("URL").fill("https://www.example.com/ryokan-booking");
  await page.getByRole("button", { name: "Pin", exact: true }).click();
  const chip = page.getByRole("link", { name: /example\.com/ });
  await expect(chip).toHaveAttribute("href", "https://www.example.com/ryokan-booking");

  // Add two travelers at once through the bulk dialog.
  await page.getByRole("button", { name: "Add traveler" }).click();
  await page.getByRole("button", { name: "Add multiple…" }).click();
  const bulk = page.getByRole("dialog", { name: "Add multiple travelers" });
  await bulk.getByRole("textbox", { name: "Travelers", exact: true }).fill(
    "Sam Lee, sam@example.com, X1234 5678\nAna Ruiz, ana@example.com",
  );
  await bulk.getByRole("button", { name: "Add 2 travelers" }).click();
  await expect(page.getByRole("button", { name: "SL Sam Lee" })).toBeVisible();
  await expect(page.getByRole("button", { name: "AR Ana Ruiz" })).toBeVisible();

  // Open day 2 from its card, set lodging, and quick-add a timed activity.
  await page.getByRole("link", { name: /^Day 2,/ }).click();
  await expect(page).toHaveURL(/\/days\/\d{4}-\d{2}-\d{2}$/);
  await page.getByLabel("Staying tonight").fill("Hotel Gracery");
  await page.getByLabel("Staying tonight").press("Enter");
  await page.getByLabel("New activity").fill("teamLab Planets");
  await page.getByLabel("New activity").press("Enter");
  const editor = page.getByRole("form", { name: "Edit teamLab Planets" });
  await editor.getByLabel("Start").fill("10:00");
  await editor.getByLabel("End").fill("12:00");
  await editor.getByLabel("Location").fill("Toyosu");
  await editor.getByRole("button", { name: "Sam Lee" }).click();
  await editor.getByRole("button", { name: "Save" }).click();

  // Times show in Tokyo time even though the browser is in LA.
  const card = page.getByRole("button", { name: "Open teamLab Planets" });
  await expect(card).toContainText("10:00 – 12:00");
  await expect(card).toContainText("Toyosu");
  await expect(card).toContainText("Planned");

  // Back on the trip, the day 2 card shows its date, lodging, and the activity.
  await page.getByRole("link", { name }).click();
  const day2 = page.getByRole("link", { name: /^Day 2,/ });
  await expect(day2).toContainText(String(Number(tokyoDate(11).slice(8))));
  await expect(day2).toContainText("Staying at Hotel Gracery");
  await expect(day2).toContainText("10:00");
  await expect(day2).toContainText("teamLab Planets");
  await expect(page.getByRole("link", { name: /^Day 1,/ })).toContainText("Plan this day");

  // Dark mode: the toggle switches themes and the choice survives a reload.
  const html = page.locator("html");
  const startDark = (await html.getAttribute("class"))?.includes("dark") ?? false;
  await page.getByRole("button", { name: "Toggle dark mode" }).click();
  await expect(html).toHaveClass(startDark ? /\blight\b/ : /\bdark\b/);
  await page.reload();
  await expect(html).toHaveClass(startDark ? /\blight\b/ : /\bdark\b/);
});
