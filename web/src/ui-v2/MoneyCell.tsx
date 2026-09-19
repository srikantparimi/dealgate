import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface MoneyCellProps {
  /** Pre-formatted monetary string. Never a number — formatting is a
   *  caller responsibility so currency/units stay explicit. */
  value: ReactNode;
  /** Distinct label for the "not calculated" state; renders as
   *  Secondary text instead of a fake zero (spec §4). */
  unavailableLabel?: string;
  /** True when the underlying value is a validated zero, not missing data. */
  isValidatedZero?: boolean;
  className?: string;
}

/**
 * Right-aligned tabular-nums cell for financial columns. NEVER performs
 * math; that lives in `api/app/gm`. A missing amount is `Unavailable`,
 * never a silent zero (spec §1 non-negotiable, §4 state copy).
 */
export function MoneyCell({
  value,
  unavailableLabel = "Unavailable",
  isValidatedZero,
  className,
}: MoneyCellProps) {
  const isEmpty =
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "");

  if (isEmpty && !isValidatedZero) {
    return (
      <span
        className={cn(
          "block text-right text-secondary text-text-secondary",
          className,
        )}
      >
        {unavailableLabel}
      </span>
    );
  }

  return (
    <span className={cn("block text-right tnum text-text", className)}>
      {value}
    </span>
  );
}
