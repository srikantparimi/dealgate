import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type MetricTrend = "up" | "down" | "flat";

export interface MetricProps {
  label: ReactNode;
  value: ReactNode;
  trend?: {
    direction: MetricTrend;
    label: ReactNode;
  };
  basis?: ReactNode;
  className?: string;
}

/**
 * KPI tile — spec §2 defines the 30/36 weight-600 value. Values are
 * always tabular so a row of numbers aligns vertically.
 *
 * IMPORTANT: this component never computes anything. Callers pass in an
 * already-formatted string. Business math lives on the server.
 */
export function Metric({ label, value, trend, basis, className }: MetricProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-panel border border-divider bg-surface p-4",
        className,
      )}
    >
      <span className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </span>
      <span className="text-metric text-text tnum">{value}</span>
      {trend ? (
        <span
          className={cn(
            "mt-1 inline-flex items-center gap-1 text-secondary",
            trend.direction === "up" && "text-success",
            trend.direction === "down" && "text-danger",
            trend.direction === "flat" && "text-text-secondary",
          )}
        >
          {trend.direction === "up" && <ArrowUpRight className="h-3 w-3" />}
          {trend.direction === "down" && <ArrowDownRight className="h-3 w-3" />}
          {trend.direction === "flat" && <Minus className="h-3 w-3" />}
          {trend.label}
        </span>
      ) : null}
      {basis ? (
        <span className="mt-1 text-secondary text-text-secondary">{basis}</span>
      ) : null}
    </div>
  );
}
