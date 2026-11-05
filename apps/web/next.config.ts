import { execSync } from "node:child_process";
import path from "node:path";
import type { NextConfig } from "next";

// One .env at the repo root serves the API and the web app.
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../../.env"));
} catch {
  // No root .env: rely on the process environment.
}

/** The short git commit being built, sent with feedback tickets; empty outside a git clone. */
function gitBuild(): string {
  try {
    return execSync("git rev-parse --short HEAD", { encoding: "utf8", stdio: "pipe" }).trim();
  } catch {
    return "";
  }
}

const nextConfig: NextConfig = {
  // The web app is a pure client of the public API: the URL and token go to the browser.
  env: {
    NEXT_PUBLIC_API_URL: process.env.API_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_API_TOKEN: process.env.API_TOKEN ?? "",
    NEXT_PUBLIC_BUILD: gitBuild(),
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
