import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // API-first boundary: the web app talks to the API over HTTP only.
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "mongodb",
              message: "apps/web must not touch the database. Call the API via @travel/client.",
            },
          ],
          patterns: [
            {
              group: ["mongodb/*"],
              message: "apps/web must not touch the database. Call the API via @travel/client.",
            },
          ],
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
