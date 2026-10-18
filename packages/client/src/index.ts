/**
 * Configured openapi-fetch client for the Travel Planner API.
 * `schema.ts` is generated from the root openapi.json by `just gen-client`; never edit it.
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, operations, paths } from "./schema";

type Schemas = components["schemas"];
export type Trip = Schemas["TripResponse"];
export type TripSummary = Schemas["TripSummary"];
export type Traveler = Schemas["Traveler"];
export type Activity = Schemas["Activity"];
export type ActivityStatus = Schemas["Activity"]["status"];
export type ActivityTime = Schemas["ActivityTime"];
export type Day = Schemas["Day"];
export type DayList = Schemas["DayList"];
export type Location = Schemas["Location"];
export type Problem = Schemas["Problem"];
export type CreateTripRequest = Schemas["CreateTripRequest"];
export type UpdateTripRequest = Schemas["UpdateTripRequest"];
export type AddActivityRequest = Schemas["AddActivityRequest"];
export type UpdateActivityRequest = Schemas["UpdateActivityRequest"];
export type UpdateDayRequest = Schemas["UpdateDayRequest"];
export type AddTravelerRequest = Schemas["AddTravelerRequest"];
export type UpdateTravelerRequest = Schemas["UpdateTravelerRequest"];
export type MoveActivityRequest = Schemas["MoveActivityRequest"];

export interface ApiClientOptions {
  /** API origin, e.g. http://localhost:8000 (paths already include /v1). */
  baseUrl: string;
  /** Bearer token (API_TOKEN). */
  token: string;
}

export function createApiClient({ baseUrl, token }: ApiClientOptions) {
  const client = createClient<paths>({ baseUrl });
  client.use({
    onRequest({ request }) {
      request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  });
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
