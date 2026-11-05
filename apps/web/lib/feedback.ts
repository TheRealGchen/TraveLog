/**
 * Context for feedback tickets: what the web app knows about where the person was and what
 * went wrong just before they opened the feedback dialog. Pure functions and module state, no
 * React, so it runs under node:test. The API stores these items without interpreting them.
 */
import type { TicketContextInput } from "@travel/client";

/** Matches the API's prefixed IDs (`trip_...`, `act_...`); same pattern as `entity` items. */
const ENTITY_ID = /^[a-z]{2,10}_[0-9A-Za-z]{1,40}$/;
/** How many recent errors and failed requests to keep. */
const KEEP = 5;
/** The API's limit on context items per ticket. */
const MAX_ITEMS = 20;

export interface ApiFailure {
  operationId: string;
  status: number;
  problemType?: string;
  errorPaths: string[];
}

export interface PageError {
  message: string;
  stack?: string;
}

/** A part of the screen, from its `data-feedback*` attributes. */
export interface FeedbackElement {
  component: string;
  label?: string;
  entityId?: string;
}

export interface PageInfo {
  pathname: string;
  params: Record<string, string | string[] | undefined>;
  viewport?: string;
  theme?: "light" | "dark";
  build?: string;
}

/** A context item with a short description, so the person can see and remove it. */
export interface ContextChoice {
  key: string;
  label: string;
  item: TicketContextInput;
}

let failures: ApiFailure[] = [];
let errors: PageError[] = [];
let etags = new Map<string, string>();
let element: { value: FeedbackElement; pathname: string } | null = null;

/** Forget everything recorded so far (for tests). */
export function resetFeedbackState() {
  failures = [];
  errors = [];
  etags = new Map();
  element = null;
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function isEntityId(value: string): boolean {
  return ENTITY_ID.test(value);
}

export function recordApiFailure(failure: ApiFailure) {
  failures = [...failures, failure].slice(-KEEP);
}

export function recordPageError(error: PageError) {
  if (errors.at(-1)?.message === error.message) return;
  errors = [...errors, error].slice(-KEEP);
}

/** Remember the ETag of a response whose path ends in a record ID, e.g. `/v1/trips/trip_01J`. */
export function recordEtag(path: string, etag: string) {
  const last = path.split("/").at(-1) ?? "";
  if (isEntityId(last)) etags.set(last, etag);
}

/** Remember the part of the screen the person last touched on this page (null to forget). */
export function recordElement(value: FeedbackElement | null, pathname: string) {
  element = value && { value, pathname };
}

/** The element last touched on `pathname`, if any. */
export function lastElement(pathname: string): FeedbackElement | null {
  return element?.pathname === pathname ? element.value : null;
}

/** Read an element's `data-feedback`, `data-feedback-label`, and `data-feedback-id`. */
export function elementFromDataset(dataset: DOMStringMap): FeedbackElement | null {
  if (!dataset.feedback) return null;
  return {
    component: dataset.feedback,
    label: dataset.feedbackLabel || undefined,
    entityId: dataset.feedbackId || undefined,
  };
}

/** The route pattern of a path: each segment filled by a param becomes `[name]`. */
export function routePattern(pathname: string, params: PageInfo["params"]): string {
  const names = new Map<string, string>();
  for (const [name, value] of Object.entries(params)) {
    if (typeof value === "string") names.set(value, `[${name}]`);
    else if (Array.isArray(value)) value.forEach((v) => names.set(v, `[...${name}]`));
  }
  const segments: string[] = [];
  for (const raw of pathname.split("/")) {
    let segment = raw;
    try {
      segment = decodeURIComponent(raw);
    } catch {}
    const name = names.get(segment);
    // A catch-all param spans several segments; show its placeholder once.
    if (name?.startsWith("[...") && segments.at(-1) === name) continue;
    segments.push(name ?? raw);
  }
  return segments.join("/") || "/";
}

/** Everything worth attaching to a ticket filed from this page right now. */
export function collectContext(page: PageInfo, picked: FeedbackElement | null): ContextChoice[] {
  const route = routePattern(page.pathname, page.params);
  const choices: ContextChoice[] = [
    {
      key: "page",
      label: `Page ${route}`,
      item: {
        type: "web.page",
        route: clip(route, 300),
        path: clip(page.pathname, 2048),
        viewport: page.viewport ?? null,
        theme: page.theme ?? null,
        build: page.build ?? null,
      },
    },
  ];
  if (picked) {
    choices.push({
      key: "element",
      label: picked.label ? `${picked.component} “${picked.label}”` : picked.component,
      item: {
        type: "web.element",
        component: clip(picked.component, 100),
        label: picked.label ? clip(picked.label, 200) : null,
      },
    });
  }
  errors.forEach((error, i) =>
    choices.push({
      key: `error-${i}`,
      label: `Error: ${clip(error.message, 60)}`,
      item: {
        type: "web.error",
        message: clip(error.message, 1000),
        stack: error.stack ? clip(error.stack, 3000) : null,
      },
    }),
  );
  failures.forEach((failure, i) =>
    choices.push({
      key: `request-${i}`,
      label: `Failed ${failure.operationId} (${failure.status})`,
      item: {
        type: "api.request",
        operationId: clip(failure.operationId, 100),
        status: failure.status,
        problemType: failure.problemType ? clip(failure.problemType, 200) : null,
        errorPaths: failure.errorPaths.slice(0, 20).map((p) => clip(p, 200)),
      },
    }),
  );
  const ids = [
    ...Object.values(page.params).flat(),
    ...(picked?.entityId ? [picked.entityId] : []),
  ].filter((v): v is string => typeof v === "string" && isEntityId(v));
  for (const id of new Set(ids)) {
    choices.push({
      key: `entity-${id}`,
      label: `Record ${id}`,
      item: { type: "entity", id, etag: etags.get(id) ?? null },
    });
  }
  return choices.slice(0, MAX_ITEMS);
}
