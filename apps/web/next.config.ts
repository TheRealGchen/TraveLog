import path from "node:path";
import type { NextConfig } from "next";

// One .env at the repo root serves the API and the web app.
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../../.env"));
} catch {
  // No root .env: rely on the process environment.
}

const nextConfig: NextConfig = {
  // The web app is a pure client of the public API: the URL and token go to the browser.
  env: {
    NEXT_PUBLIC_API_URL: process.env.API_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_API_TOKEN: process.env.API_TOKEN ?? "",
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
