/**
 * GateSteps — DealGate v2.1 prototype (lines 153–162, 427–434).
 *
 * A row of six clickable stage chips inside a single rounded card
 * (12px radius) with a single border. Each step reports one of four
 * states:
 *   - done    (success — the gate cleared; the "n · Done" number is `--ok`)
 *   - now     (progress — primary-subtle background, primary text)
 *   - pending (neutral — plain surface, muted text)
 *   - hold    (danger-tinted — bad-fill background, bad text; reads
 *              "Will trigger" so Sales can see the CEO consequence while
 *              building the GM, not after submitting)
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

const STATE_NUMBER_CLASS: Record<GateState, string> = {
  done: "text-success",
  now: "text-primaryText",
  pending: "text-text-muted",
  hold: "text-danger",
};

const STATE_CELL_CLASS: Record<GateState, string> = {
  done: "bg-surface",
  now: "bg-primary-subtle",
  pending: "bg-surface",
  hold: "bg-danger-surface",
};

const STATE_LABEL_CLASS: Record<GateState, string> = {
  done: "text-text",
  now: "text-primaryText",
  pending: "text-text",
  hold: "text-danger",
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
        "flex w-full overflow-hidden rounded-card border border-border bg-surface",
        className,
      )}
    >
      {steps.map((step, i) => {
        const Cmp: "button" | "div" = step.onSelect ? "button" : "div";
        const cellClass = cn(
          "flex-1 min-w-0 flex flex-col gap-[2px] px-[14px] py-[10px]",
          "text-left transition-motion",
          i > 0 && "border-l border-border",
          STATE_CELL_CLASS[step.state],
          step.onSelect &&
            "hover:brightness-95 focus-visible:outline-focus cursor-pointer",
        );
        const suffix =
          step.state === "hold"
            ? "Will trigger"
            : step.state === "done"
              ? "Done"
              : step.state === "now"
                ? "Now"
                : null;
        const content = (
          <>
            <span
              className={cn(
                "text-[11px] tnum truncate",
                STATE_NUMBER_CLASS[step.state],
              )}
            >
              <span className="tnum">{i + 1}</span>
              {suffix ? (
                <>
                  {" · "}
                  <span>{suffix}</span>
                </>
              ) : null}
            </span>
            <span
              className={cn(
                "truncate text-[13px] font-medium",
                STATE_LABEL_CLASS[step.state],
              )}
            >
              {step.label}
            </span>
            {step.hint ? (
              <span className="text-[11px] text-text-muted truncate">
                {step.hint}
              </span>
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
