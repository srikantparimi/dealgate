import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface MarginCellProps {
  /** Pre-formatted percentage string (e.g. "34.5%"). Server rounds, UI
   *  displays. */
  value: ReactNode;
  /** Semantic evaluation of the value — driven by policy tests on the
   *  server, never inferred client-side. */
  outcome?: "pass" | "fail" | "unavailable";
  className?: string;
}

/**
 * Right-aligned margin cell. Colour is supplementary — the outcome word
 * lives beside the number so a policy fail is never conveyed by colour
 * alone (spec §2, §20).
 */
export function MarginCell({ value, outcome, className }: MarginCellProps) {
  if (outcome === "unavailable" || value === null || value === undefined) {
    return (
      <span
        className={cn(
          "block text-right text-secondary text-text-secondary",
          className,
        )}
      >
        Not validated
      </span>
    );
  }
  return (
    <span
      className={cn(
        "block text-right tnum",
        outcome === "pass" && "text-success",
        outcome === "fail" && "text-danger",
        !outcome && "text-text",
        className,
      )}
    >
      {value}
    </span>
  );
}
