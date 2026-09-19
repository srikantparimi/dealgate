/**
 * Presentation-only formatters for the CEO exception page. Mirrors the
 * SOW workspace helpers so both compositions display numbers the same
 * way.
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

export function formatPercent(
  value: string | null | undefined,
  digits = 1,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return `${(parsed * 100).toFixed(digits)}%`;
}

/** Percentage-points gap between value and floor. Both Decimal strings. */
export function formatPpGap(
  value: string | null | undefined,
  floor: string | null | undefined,
): string | null {
  if (value == null || floor == null) return null;
  const v = Number(value);
  const f = Number(floor);
  if (!Number.isFinite(v) || !Number.isFinite(f)) return null;
  const pp = (f - v) * 100;
  const sign = pp > 0 ? "+" : "";
  return `${sign}${pp.toFixed(1)} pp`;
}
