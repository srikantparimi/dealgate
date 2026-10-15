// S23-PL2 · display formatting for the Pipeline page. Formatting only: every
// number arrives computed by the API; nothing here adds amounts together.
import type { DecimalStr, ISODate, ISODateTime } from "../../../api/client";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const PIPELINE_TIMEZONE = "America/Los_Angeles";

/** "deal" / "deals" by count. */
export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** A deal's currency code, or null when the deal has none (HubSpot sent no currency). */
export function currencyCode(currency: string | null | undefined): string | null {
  return currency?.trim() || null;
}

/**
 * The marks around an amount. A total passes no currency: every total is USD ("$"). A deal
 * passes its own: "$" for USD, "EUR " for another code, and for none (null or blank) no
 * symbol and " · no currency" after it, since the API leaves such a deal out of every USD total.
 */
function currencyMarks(currency: string | null | undefined): { prefix: string; suffix: string } {
  if (currency === undefined) return { prefix: "$", suffix: "" };
  const code = currencyCode(currency);
  if (!code) return { prefix: "", suffix: " · no currency" };
  return { prefix: code === "USD" ? "$" : `${code} `, suffix: "" };
}

/**
 * Compact money: "$21.60m", "$538k", "$533.5k", "$950", "$0"; "EUR 120k" in another currency;
 * "542k · no currency" for a deal without one. Missing → `missing`.
 */
export function shortMoney(
  value: DecimalStr | null | undefined,
  opts: { currency?: string | null; missing?: string } = {},
): string {
  const missing = opts.missing ?? "Not entered";
  if (value === null || value === undefined || value === "") return missing;
  const n = Number(value);
  if (!Number.isFinite(n)) return missing;
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  const { prefix, suffix } = currencyMarks(opts.currency);
  if (a >= 999_950) return `${sign}${prefix}${(a / 1_000_000).toFixed(2)}m${suffix}`;
  if (a >= 1000) {
    const k = Math.round(a / 100) / 10;
    return `${sign}${prefix}${Number.isInteger(k) ? k.toFixed(0) : k.toFixed(1)}k${suffix}`;
  }
  return `${sign}${prefix}${Math.round(a)}${suffix}`;
}

/**
 * Full money: "$542,000", "$21,596,444.14"; "EUR 120,000"; "542,000 · no currency" for a deal
 * without one. Missing → `missing`.
 */
export function fullMoney(
  value: DecimalStr | null | undefined,
  opts: { currency?: string | null; missing?: string } = {},
): string {
  const missing = opts.missing ?? "Not entered";
  if (value === null || value === undefined || value === "") return missing;
  const n = Number(value);
  if (!Number.isFinite(n)) return missing;
  const body = new Intl.NumberFormat("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(
    Math.abs(n),
  );
  const { prefix, suffix } = currencyMarks(opts.currency);
  return `${n < 0 ? "-" : ""}${prefix}${body}${suffix}`;
}

/** Calendar date "Dec 28" (the year is added when it is not `today`'s year). No time-zone drift. */
export function calendarDate(value: ISODate | null | undefined, today?: ISODate, missing = "Not set"): string {
  if (!value) return missing;
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d) return missing;
  const base = `${MONTHS[m - 1]} ${d}`;
  return today && today.slice(0, 4) !== value.slice(0, 4) ? `${base}, ${y}` : base;
}

/** "Oct 14, 2026" for a calendar date. */
export function longCalendarDate(value: ISODate): string {
  const [y, m, d] = value.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** "Oct 14, 2:10 AM PT" for an instant, in America/Los_Angeles. */
export function pacificDateTime(value: ISODateTime | null | undefined, missing = "Never"): string {
  if (!value) return missing;
  const t = new Date(value);
  if (Number.isNaN(t.getTime())) return missing;
  const text = t.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: PIPELINE_TIMEZONE,
  });
  return `${text} PT`;
}

/** Whole hours between an instant and now (display only). */
export function hoursSince(value: ISODateTime | null | undefined, now: Date = new Date()): number | null {
  if (!value) return null;
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((now.getTime() - t) / 3_600_000));
}

/** Two-letter initials for an avatar. */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}
