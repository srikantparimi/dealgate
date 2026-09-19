/**
 * Time-travel helper for E2E specs.
 *
 * Several API paths (renewals scheduler, SLA escalation, forecast
 * grouping) honour the `DEALGATE_NOW` env var when computing "now". The
 * FastAPI process reads the var lazily per request via `os.environ.get`
 * (see `api/app/services/forecast.py`, alerts scheduler), so a spec can
 * mutate it before triggering a scheduler tick and restore it after.
 *
 * The var is set on the *server* process, which means specs need a way
 * to reach into the running FastAPI to change it. We expose a tiny
 * admin-only POST endpoint (`/admin/test/now`) in the dev backend for
 * this — when the API is not built with that endpoint the helper
 * fails soft and the spec skips via a `test.skip`.
 */
import { apiFetch } from "./api";

export interface TimeTravelResult {
  supported: boolean;
  previous?: string | null;
}

/**
 * Set the server's clock override. Returns `supported=false` if the
 * dev endpoint is missing, letting the spec skip cleanly.
 */
export async function setServerNow(iso: string): Promise<TimeTravelResult> {
  const res = await apiFetch<{ previous: string | null }>(
    "SystemAdmin",
    "POST",
    "/admin/test/now",
    { iso },
    { allowNon2xx: true },
  );
  if (res.status === 404) return { supported: false };
  if (!res.ok) throw new Error(`setServerNow: unexpected ${res.status} ${res.text}`);
  return { supported: true, previous: res.json?.previous ?? null };
}

/** Clear the override so subsequent specs see real wall-clock time. */
export async function clearServerNow(): Promise<void> {
  await apiFetch("SystemAdmin", "POST", "/admin/test/now", { iso: null }, {
    allowNon2xx: true,
  });
}

/** Nudge the alerts scheduler (renewals + SLA). Same soft-fail contract
 * as `setServerNow` — if the endpoint isn't exposed, the caller should
 * `test.skip`. */
export async function tickScheduler(): Promise<TimeTravelResult> {
  const res = await apiFetch(
    "SystemAdmin",
    "POST",
    "/admin/test/scheduler-tick",
    {},
    { allowNon2xx: true },
  );
  if (res.status === 404) return { supported: false };
  if (!res.ok) throw new Error(`tickScheduler: unexpected ${res.status} ${res.text}`);
  return { supported: true };
}
