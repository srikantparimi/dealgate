/**
 * API helpers for E2E specs.
 *
 * Every request carries an `X-Test-User: <role>@smartek21.com` header. The
 * FastAPI dev auth backend (`api/app/auth/deps.py::current_user`) accepts
 * this header when `DEALGATE_ENV=local`, and the process-wide
 * `DEALGATE_TEST_GROUPS` env var (set in the workflow) grants every role
 * so specs can freely switch identities per request.
 */
import { request } from "@playwright/test";

export type Role =
  | "SystemAdmin"
  | "Sales"
  | "SalesLeader"
  | "Delivery"
  | "Presales"
  | "Finance"
  | "Legal"
  | "HR"
  | "CEO"
  | "Marketing";

/** Local-friendly email helper — matches the "@smartek21.com" convention
 * every existing pytest AC uses. */
export function emailFor(role: Role): string {
  return `${role.toLowerCase()}@smartek21.com`;
}

/**
 * Root API base — defaults to `http://localhost:8000` (FastAPI dev).
 * Override with `E2E_API_BASE` in CI or when pointing at staging.
 */
export function apiBase(): string {
  return process.env.E2E_API_BASE ?? "http://localhost:8000";
}

export interface ApiFetchOptions {
  /** Optional query string params */
  query?: Record<string, string | number | boolean | undefined>;
  /** Extra headers to merge over the defaults */
  headers?: Record<string, string>;
  /** Expect a non-2xx JSON response (still validates its content type). */
  allowNon2xx?: boolean;
}

export interface ApiFetchResult<T> {
  status: number;
  ok: boolean;
  json: T;
  text: string;
}

/**
 * Low-level fetch used across specs + seed helpers. Uses Playwright's
 * request context so the assertions and traces live inside the test run.
 */
export async function apiFetch<T = unknown>(
  role: Role | string,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  opts: ApiFetchOptions = {},
): Promise<ApiFetchResult<T>> {
  const ctx = await request.newContext({
    baseURL: apiBase(),
    extraHTTPHeaders: {
      "X-Test-User":
        typeof role === "string" && role.includes("@") ? role : emailFor(role as Role),
      "Content-Type": "application/json",
      ...(opts.headers ?? {}),
    },
  });
  try {
    const qs = opts.query
      ? "?" +
        new URLSearchParams(
          Object.entries(opts.query)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    const res = await ctx.fetch(`${path}${qs}`, {
      method,
      data: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const status = res.status();
    const contentType = res.headers()["content-type"] ?? "";
    const isJson = contentType.split(";", 1)[0].trim().toLowerCase() === "application/json";
    // DELETE endpoints legitimately return 204 without representation headers.
    const noContent = (status === 204 || status === 205) && text === "";
    if (!isJson && !(noContent && contentType === "")) {
      throw new Error(
        `apiFetch ${method} ${path} -> ${status}: expected application/json, got ${contentType || "<missing>"}: ${text.slice(0, 400)}`,
      );
    }
    let json: T;
    try {
      json = noContent ? null as T : JSON.parse(text) as T;
    } catch {
      throw new Error(
        `apiFetch ${method} ${path} -> ${status}: invalid JSON response: ${text.slice(0, 400)}`,
      );
    }
    if (!res.ok() && !opts.allowNon2xx) {
      throw new Error(
        `apiFetch ${method} ${path} -> ${status}: ${text.slice(0, 400)}`,
      );
    }
    return { status, ok: res.ok(), json, text };
  } finally {
    await ctx.dispose();
  }
}
