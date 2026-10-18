import { createApiClient, type Problem } from "@travel/client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** The only way the web app reaches data: the generated client over HTTP. */
export const api = createApiClient({
  baseUrl: API_URL,
  token: process.env.NEXT_PUBLIC_API_TOKEN ?? "",
});

/** An API failure carrying the problem+json body, whose `detail` is shown to the user. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly problem?: Problem,
  ) {
    super(message);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Await an openapi-fetch call and return its data, or throw an ApiError with the detail. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError(`Can't reach the API at ${API_URL}. Is it running?`, 0);
  }
  const { data, error, response } = result;
  if (!response.ok) {
    const problem = (error && typeof error === "object" ? error : undefined) as Problem | undefined;
    throw new ApiError(
      problem?.detail ?? `${response.status} ${response.statusText}`,
      response.status,
      problem,
    );
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
