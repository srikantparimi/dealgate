/**
 * Sticky progress rail (spec §13.2). Shows all five steps; a completed
 * step is clickable and returns the user to it with state preserved
 * (the reducer never wipes fields on back-nav).
 */
import { Check } from "lucide-react";
import { cn } from "../../../lib/cn";
import { STEPS, canRevisitStep, type StepId, type StudioState } from "./steps";

export interface ProgressRailProps {
  state: StudioState;
  onNavigate: (id: StepId) => void;
}

export function ProgressRail({ state, onNavigate }: ProgressRailProps) {
  const currentIdx = STEPS.findIndex((s) => s.id === state.step);
  return (
    <nav
      aria-label="SOW studio progress"
      className="sticky top-0 z-10 -mx-4 border-b border-divider bg-canvas/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-panel sm:border sm:bg-surface"
    >
      <ol className="flex flex-wrap items-center gap-2">
        {STEPS.map((step, idx) => {
          const isCurrent = state.step === step.id;
          const isComplete = idx < currentIdx;
          const canRevisit = canRevisitStep(state, step.id);
          return (
            <li key={step.id} className="flex items-center gap-2">
              <button
                type="button"
                disabled={!canRevisit}
                onClick={() => onNavigate(step.id)}
                aria-current={isCurrent ? "step" : undefined}
                data-testid={`step-nav-${step.id}`}
                className={cn(
                  "flex items-center gap-2 rounded-control border px-3 py-1 text-secondary transition-motion",
                  "focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60",
                  isCurrent
                    ? "border-primary bg-primary text-primary-fg"
                    : isComplete
                      ? "border-success/40 bg-success-surface text-success"
                      : "border-input-border bg-surface text-text",
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full text-secondary tnum",
                    isCurrent
                      ? "bg-primary-fg text-primary"
                      : isComplete
                        ? "bg-success text-white"
                        : "bg-divider text-text",
                  )}
                  aria-hidden
                >
                  {isComplete ? <Check className="h-3 w-3" /> : step.index}
                </span>
                <span className="font-medium">{step.short}</span>
              </button>
              {idx < STEPS.length - 1 ? (
                <span aria-hidden className="text-text-secondary">
                  ›
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
