import { defineConfig, devices } from "@playwright/test";

// The smoke test runs its own API (port 8100, database travel_planner_e2e) and a production
// build of the web app (port 3100), so it never touches dev data. MongoDB must be running
// (`just mongo`, or MONGODB_URI pointing elsewhere).
const API_PORT = 8100;
const WEB_PORT = 3100;
const TOKEN = "e2e-token";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    // A browser timezone different from the trip's, to catch timezone leaks.
    timezoneId: "America/Los_Angeles",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run uvicorn travel_api.main:create_app --factory --port ${API_PORT}`,
      cwd: "../api",
      url: `http://localhost:${API_PORT}/llms.txt`,
      env: {
        MONGODB_URI: process.env.MONGODB_URI ?? "mongodb://localhost:27017",
        MONGODB_DB: "travel_planner_e2e",
        API_TOKEN: TOKEN,
        WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
        // Keep the test offline: links are pinned without fetching a preview.
        LINK_PREVIEWS: "false",
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `pnpm exec next build && pnpm exec next start --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      env: { API_URL: `http://localhost:${API_PORT}`, API_TOKEN: TOKEN },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
