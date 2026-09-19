/**
 * GateSteps — v2.1 spec `components.gateSteps`.
 *
 * A row of six clickable stage chips. Each step reports one of four
 * states:
 *   - done    (success — the gate cleared)
 *   - now     (progress — the gate the package is currently at)
 *   - pending (neutral — a future gate)
 *   - hold    (danger-tinted — reads "Will trigger" for a gate that
 *              hasn't been reached yet, so Sales can see the CEO
 *              consequence while building the GM, not after submitting)
 */
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type GateState = "done" | "now" | "pending" | "hold";

export interface GateStep {
  id: string;
  label: string;
  state: GateState;
  /** Optional handler; when omitted the step still renders but is inert. */
  onSelect?: () => void;
  /** Optional inline hint shown below the label (e.g. reviewer name). */
  hint?: ReactNode;
}

export interface GateStepsProps {
  steps: GateStep[];
  /** Accessible label for the wrapping `<nav>`. */
  ariaLabel?: string;
  className?: string;
}

const STATE_CLASSES: Record<GateState, string> = {
  done: "bg-success-surface text-success border-success/30",
  now: "bg-primary-subtle text-primaryText border-primary/40 font-semibold",
  pending: "bg-surface text-text-secondary border-border",
  hold: "bg-danger-surface text-danger border-danger/30",
};

const STATE_MICROCOPY: Record<GateState, string> = {
  done: "Cleared",
  now: "In review",
  pending: "Not started",
  hold: "Will trigger",
};

export function GateSteps({
  steps,
  ariaLabel = "Gate progress",
  className,
}: GateStepsProps) {
  return (
    <nav
      aria-label={ariaLabel}
      className={cn(
        "flex w-full rounded-card border border-border bg-surface overflow-hidden",
        className,
      )}
    >
      {steps.map((step, i) => {
        const Cmp: "button" | "div" = step.onSelect ? "button" : "div";
        const cellClass = cn(
          "flex-1 min-w-0 flex flex-col items-start justify-center gap-1",
          "px-3 py-2 text-left transition-motion",
          i > 0 && "border-l border-border",
          STATE_CLASSES[step.state],
          step.onSelect &&
            "hover:brightness-95 focus-visible:outline-focus cursor-pointer",
        );
        const content = (
          <>
            <span className="text-[11px] uppercase tracking-wide tnum">
              Gate {i + 1}
            </span>
            <span className="truncate text-[13px] font-medium">
              {step.label}
            </span>
            <span className="text-[11px] opacity-80">
              {STATE_MICROCOPY[step.state]}
            </span>
            {step.hint ? (
              <span className="text-[11px] opacity-70">{step.hint}</span>
            ) : null}
          </>
        );
        return Cmp === "button" ? (
          <button
            key={step.id}
            type="button"
            className={cellClass}
            onClick={step.onSelect}
            aria-current={step.state === "now" ? "step" : undefined}
            data-state={step.state}
            data-testid={`gate-step-${step.id}`}
          >
            {content}
          </button>
        ) : (
          <div
            key={step.id}
            className={cellClass}
            aria-current={step.state === "now" ? "step" : undefined}
            data-state={step.state}
            data-testid={`gate-step-${step.id}`}
          >
            {content}
          </div>
        );
      })}
    </nav>
  );
}
