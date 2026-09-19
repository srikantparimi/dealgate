/**
 * Display formatters for Projects & actuals.
 *
 * Business math lives on the server (blueprint §2, CLAUDE.md rule 2).
 * These helpers only shape strings for human eyes. `null` in ⇒ `null` out
 * so callers can render "Unavailable" (spec §4 state copy).
 */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function fmtMoney(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return USD.format(n);
}

export function fmtPercent(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return `${(n * 100).toFixed(1)}%`;
}

/**
 * Absolute percentage-point difference between two ratios (spec §15
 * "variance in percentage points"). Server does not pre-compute this
 * for the portfolio view so we shape it once here for display; the
 * inputs are already Decimal strings on the wire.
 */
export function fmtVariancePp(
  approved: string | null | undefined,
  forecast: string | null | undefined,
): string | null {
  if (approved === null || approved === undefined || approved === "") return null;
  if (forecast === null || forecast === undefined || forecast === "") return null;
  const a = Number(approved);
  const f = Number(forecast);
  if (!Number.isFinite(a) || !Number.isFinite(f)) return null;
  const delta = (f - a) * 100;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)} pts`;
}

export function fmtCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-US").format(n);
}
