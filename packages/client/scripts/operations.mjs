// Write src/operations.ts, mapping "METHOD /path" to each operation's operationId, from the root
// openapi.json. With --check, fail if the file is out of date instead of writing it.
import { readFileSync, writeFileSync } from "node:fs";

const spec = JSON.parse(readFileSync(new URL("../../../openapi.json", import.meta.url), "utf8"));
const target = new URL("../src/operations.ts", import.meta.url);

const entries = Object.entries(spec.paths).flatMap(([path, methods]) =>
  Object.entries(methods).map(([method, op]) => `  "${method.toUpperCase()} ${path}": "${op.operationId}",`),
);
const source = `// Generated from openapi.json by scripts/operations.mjs (\`just gen-client\`); never edit it.

/** The operationId of each operation, keyed by "METHOD /schema/path". */
export const operationIds: Record<string, string> = {
${entries.join("\n")}
};
`;

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(target, "utf8");
  } catch {}
  if (current !== source) {
    console.error("packages/client/src/operations.ts is out of date. Run just gen-client and commit it.");
    process.exit(1);
  }
} else {
  writeFileSync(target, source);
}
