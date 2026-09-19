/**
 * FloorBar — v2.1 spec `components.floorBar`.
 *
 * A 10 px track spanning 0 – 60 %. The floor is a text-colored 2 px line
 * with the label above it. The fill is `success` at or above the floor,
 * `danger` below. The trailing chip reads "Fails by 7.2 pts" or "Passes
 * by 4.3 pts" so the gap to policy is visible in one glance.
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
}

/**
 * Coerce a Decimal string to a percentage number for display only.
 * Accepts both fraction (0.278) and percentage (27.8) forms.
 */
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
  className,
  ...rest
}: FloorBarProps) {
  const valuePct = toPct(value);
  const floorPct = toPct(floor);
  const gap = valuePct - floorPct;
  const pass = gap >= 0;

  const fillWidthPct = (clampToScale(valuePct) / SCALE_MAX) * 100;
  const floorLeftPct = (clampToScale(floorPct) / SCALE_MAX) * 100;

  const accessibleLabel = label
    ? `${label} — ${valuePct.toFixed(1)}% vs floor ${floorPct.toFixed(1)}%`
    : `${valuePct.toFixed(1)}% vs floor ${floorPct.toFixed(1)}%`;

  return (
    <div
      className={cn("flex flex-col gap-2", className)}
      role="group"
      aria-label={accessibleLabel}
      {...rest}
    >
      <div
        className="relative h-[10px] w-full rounded-avatar bg-surface-sunken"
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
        <div
          className="absolute top-[-6px] bottom-[-6px] w-[2px] bg-text"
          style={{ left: `${floorLeftPct}%` }}
          data-testid="floorbar-marker"
          aria-hidden
        />
        <span
          className="absolute -top-5 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium text-text tnum"
          style={{ left: `${floorLeftPct}%` }}
        >
          {floorPct.toFixed(0)}% floor
        </span>
      </div>
      <div className="flex items-center justify-between text-secondary text-text-secondary">
        <span className="tnum">0%</span>
        {showChip ? (
          <span
            className={cn(
              "inline-flex items-center gap-[6px] rounded-chip border h-[22px] px-2 text-[12px] font-medium tnum",
              pass
                ? "bg-success-surface text-success border-success/20"
                : "bg-danger-surface text-danger border-danger/20",
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
        <span className="tnum">{SCALE_MAX}%</span>
      </div>
    </div>
  );
}
