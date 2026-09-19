/**
 * Presentation-only formatters for the SOW workspace. No business math
 * happens here (CLAUDE.md rule 2). Every helper accepts an already-
 * validated string from the API and returns a display string.
 */

/**
 * Format a decimal string (or null) as USD to the nearest dollar. Returns
 * ``null`` when the input is missing so the caller can render an honest
 * "Unavailable" state rather than a fake zero (spec §4).
 */
export function formatUsd(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return parsed.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
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

/** UUID → short suffix used in the record header (last 8 chars). */
export function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(-8);
}
