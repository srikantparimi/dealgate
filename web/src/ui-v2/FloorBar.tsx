/**
 * FloorBar — DealGate v2.1 prototype (lines 147–152).
 *
 * A 10 px track spanning 0 – 60 %. The floor is a text-colored 2 px line
 * that overshoots the track by 4 px at the top and bottom (per prototype
 * `.floorbar .mark`), with the label positioned above the line via
 * `.mark::after` translate.
 *
 * The fill is `success` at or above the floor, `danger` below. A trailing
 * chip reads "Fails by 7.2 pts" or "Passes by 4.3 pts" so the gap to
 * policy is visible in one glance.
 *
 * `value` and `floor` are Decimal strings — no floats in this codebase.
 * Parsing happens inside the primitive for display; arithmetic remains
 * a display-only calculation of the gap in percentage points.
 */
import type { HTMLAttributes } from "react";
import { cn } from "../lib/cn";

const SCALE_MAX = 60;

export interface FloorBarProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  /** Achieved margin as a Decimal string, e.g. "0.278" or "27.8". */
  value: string;
  /** Floor as a Decimal string, e.g. "0.35" or "35". */
  floor: string;
  /** Optional accessible label prefix (e.g. "US component"). */
  label?: string;
  /** Set to `false` to hide the trailing "Fails/Passes by N pts" chip. */
  showChip?: boolean;
  /** Set to `false` to hide the "0%" / "60%" scale labels either side. */
  showScale?: boolean;
  /** Policy outcomes and gaps supplied by the Decimal engine. */
  passes?: boolean;
  delta?: string | null;
}

function toPct(s: string): number {
  const n = Number(s);
  if (!Number.isFinite(n)) return 0;
  return n <= 1 ? n * 100 : n;
}

function clampToScale(pct: number): number {
  if (pct <= 0) return 0;
  if (pct >= SCALE_MAX) return SCALE_MAX;
  return pct;
}

export function FloorBar({
  value,
  floor,
  label,
  showChip = true,
  showScale = true,
  passes,
  delta,
  className,
  ...rest
}: FloorBarProps) {
  const valuePct = toPct(value);
  const floorPct = toPct(floor);
  const gap = delta != null ? Number(delta) * 100 : valuePct - floorPct;
  const pass = passes ?? gap >= 0;

  const fillWidthPct = (clampToScale(valuePct) / SCALE_MAX) * 100;
  const floorLeftPct = (clampToScale(floorPct) / SCALE_MAX) * 100;

  const accessibleLabel = label
    ? `${label} — ${valuePct.toFixed(1)}% vs floor ${floorPct.toFixed(1)}%`
    : `${valuePct.toFixed(1)}% vs floor ${floorPct.toFixed(1)}%`;

  return (
    <div
      className={cn("grid grid-cols-[auto_1fr_auto] items-center gap-[10px] text-[13px]", className)}
      role="group"
      aria-label={accessibleLabel}
      {...rest}
    >
      {showScale ? (
        <span className="tnum text-text-secondary">0%</span>
      ) : null}
      <div
        className="relative h-[10px] w-full overflow-visible rounded-avatar bg-surface-sunken"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={SCALE_MAX}
        aria-valuenow={Number(valuePct.toFixed(1))}
        aria-label={`Achieved ${valuePct.toFixed(1)} percent, floor ${floorPct.toFixed(1)} percent`}
      >
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-avatar",
            pass ? "bg-success" : "bg-danger",
          )}
          style={{ width: `${fillWidthPct}%` }}
          data-testid="floorbar-fill"
        />
        {/* 2px mark line with 4px overshoot at top and bottom per prototype. */}
        <div
          className="absolute -top-1 -bottom-1 w-[2px] bg-text"
          style={{ left: `${floorLeftPct}%` }}
          data-testid="floorbar-marker"
          aria-hidden
        />
        {/* Label sits 16px above the mark line, centered on it. */}
        <span
          className="absolute -top-4 -translate-x-1/2 whitespace-nowrap text-[10px] text-text-muted tnum"
          style={{ left: `${floorLeftPct}%` }}
        >
          {floorPct.toFixed(0)}% floor
        </span>
      </div>
      {showScale ? (
        <span className="tnum text-text-secondary">{SCALE_MAX}%</span>
      ) : null}
      {showChip ? (
        <span
          className={cn(
            "col-span-3 mt-1 inline-flex items-center gap-[6px] rounded-chip",
            "h-[22px] px-2 text-[12px] font-medium tnum w-max",
            pass
              ? "bg-success-surface text-success"
              : "bg-danger-surface text-danger",
          )}
          data-testid="floorbar-chip"
        >
          <span
            aria-hidden
            className={cn(
              "inline-block h-[6px] w-[6px] rounded-avatar",
              pass ? "bg-success" : "bg-danger",
            )}
          />
          {pass ? "Passes by" : "Fails by"} {Math.abs(gap).toFixed(1)} pts
        </span>
      ) : null}
    </div>
  );
}
