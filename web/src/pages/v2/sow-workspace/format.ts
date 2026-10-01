/**
 * Presentation-only formatters for the SOW workspace. No business math
 * happens here (CLAUDE.md rule 2). Every helper accepts an already-
 * validated string from the API and returns a display string.
 */

/**
 * Format USD with cents only when present, or a caller-specified precision. Returns
 * ``null`` when the input is missing so the caller can render an honest
 * "Unavailable" state rather than a fake zero (spec §4).
 */
export function formatUsd(value: string | null | undefined, digits?: number): string | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return parsed.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits ?? (Number.isInteger(parsed) ? 0 : 2),
    maximumFractionDigits: digits ?? 2,
  });
}

/**
 * Format a Decimal string like "0.3450" as "34.5%". Only display code — the
 * underlying comparison against a floor is a server responsibility.
 */
export function formatPercent(
  value: string | null | undefined,
  digits = 1,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return `${(parsed * 100).toFixed(digits)}%`;
}

/** Short ISO date → "2026-09-19". Bail to `null` on missing input. */
export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.slice(0, 10);
}

/**
 * S21 item 4 · single display format for a SOW term — "Oct 12, 2026 –
 * Apr 12, 2027". Both ends get the same format with an explicit year.
 * The old header path concatenated two different formats ("10/12/2026
 * to April 12th") because `formatDate` returns ISO-truncated and the
 * end was parsed by `toLocaleDateString`. Returns null when neither
 * side is present; "Oct 12, 2026 – (open)" when only start is present.
 */
export function formatTermRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  const asDate = (v: string | null | undefined): Date | null => {
    if (!v) return null;
    const d = new Date(v.length === 10 ? `${v}T00:00:00Z` : v);
    return Number.isFinite(d.getTime()) ? d : null;
  };
  const fmt = (d: Date): string =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  const s = asDate(start);
  const e = asDate(end);
  if (!s && !e) return null;
  if (s && !e) return `${fmt(s)} – (open)`;
  if (!s && e) return `(open) – ${fmt(e)}`;
  return `${fmt(s!)} – ${fmt(e!)}`;
}

/** UUID → short suffix used in the record header (last 8 chars). */
export function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(-8);
}

/** Format a quantity (hours, seats, count) with thousand separators. */
export function formatQuantity(value: string | null | undefined): string | null {
  if (value == null || value === "" || !Number.isFinite(Number(value))) return null;
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Format a rate — dollars with 2 decimals. */
export function formatRate(value: string | null | undefined): string | null {
  return formatUsd(value, 2);
}

/** Strip trailing zeros / dots from a raw decimal for a text input's value.
 * A stored "800.000000000" becomes "800" so the input does not display the
 * raw padding while still round-tripping numerically on save. */
export function decimalInput(value: string | null | undefined): string {
  if (!value) return "";
  if (!value.includes(".")) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
}
