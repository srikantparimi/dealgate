/**
 * FunctionMark — DealGate v2.1 prototype (lines 212–216).
 *
 * A 22 × 18 chip carrying one of the four function letters (Delivery /
 * HR / Finance / Legal) and one of four states:
 *   - pending  (grey, not yet reached; keeps a 1px border to stay visible)
 *   - progress (violet, currently reviewing)
 *   - ok       (green, approved)
 *   - bad      (red, rejected)
 *
 * The colored states have no border (per prototype `border-color:transparent`).
 * The mark row is always followed by "n/4 reviews" text — see the
 * `FunctionMarkRow` helper below.
 */
import type { HTMLAttributes } from "react";
import { cn } from "../lib/cn";

export type FunctionLetter = "D" | "H" | "F" | "L";
export type FunctionState = "pending" | "progress" | "ok" | "bad";

const FUNCTION_LETTERS: FunctionLetter[] = ["D", "H", "F", "L"];
const FUNCTION_LABEL: Record<FunctionLetter, string> = {
  D: "Delivery",
  H: "HR",
  F: "Finance",
  L: "Legal",
};

const STATE_CLASSES: Record<FunctionState, string> = {
  pending: "bg-surface-sunken text-text-muted border border-border",
  progress: "bg-primary-subtle text-primaryText border border-transparent",
  ok: "bg-success-surface text-success border border-transparent",
  bad: "bg-danger-surface text-danger border border-transparent",
};

const STATE_LABEL: Record<FunctionState, string> = {
  pending: "pending",
  progress: "in review",
  ok: "approved",
  bad: "rejected",
};

export interface FunctionMarkProps extends HTMLAttributes<HTMLSpanElement> {
  letter: FunctionLetter;
  state: FunctionState;
}

export function FunctionMark({
  letter,
  state,
  className,
  ...rest
}: FunctionMarkProps) {
  return (
    <span
      aria-label={`${FUNCTION_LABEL[letter]} ${STATE_LABEL[state]}`}
      className={cn(
        "inline-flex items-center justify-center rounded-chip",
        "font-bold text-[10px] leading-none",
        "w-[22px] h-[18px]",
        STATE_CLASSES[state],
        className,
      )}
      {...rest}
    >
      {letter}
    </span>
  );
}

export interface FunctionMarkRowProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  /** State per function letter. Missing keys render as `pending`. */
  states: Partial<Record<FunctionLetter, FunctionState>>;
  /**
   * Optional explicit count for the trailing "n/4 reviews" copy. If
   * omitted, the count is the number of `ok` states.
   */
  count?: number;
}

export function FunctionMarkRow({
  states,
  count,
  className,
  ...rest
}: FunctionMarkRowProps) {
  const resolved = FUNCTION_LETTERS.map((l) => ({
    letter: l,
    state: (states[l] ?? "pending") as FunctionState,
  }));
  const okCount = count ?? resolved.filter((r) => r.state === "ok").length;
  return (
    <div
      className={cn(
        "flex items-center gap-2 text-[12px] text-text-muted",
        className,
      )}
      title="Delivery · HR · Finance · Legal"
      {...rest}
    >
      <div className="flex items-center gap-1">
        {resolved.map((r) => (
          <FunctionMark key={r.letter} letter={r.letter} state={r.state} />
        ))}
      </div>
      <span className="tnum">{okCount}/4 reviews</span>
    </div>
  );
}
