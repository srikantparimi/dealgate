import { CheckCircle2, CircleDashed, MinusCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { cn } from "../../../lib/cn";
import type { RailStep } from "./readiness";

/**
 * Six-step progress rail (spec §8). Each step is clickable when the
 * user is allowed to visit that tab. `skipped` renders with a
 * de-emphasised icon so an omitted CEO exception does not look like an
 * outstanding blocker.
 */
export function ProgressRail({ rail }: { rail: RailStep[] }) {
  const nav = useNavigate();
  const { id } = useParams<{ id: string }>();
  return (
    <nav
      aria-label="SOW progress"
      className="flex flex-wrap items-center gap-2 rounded-panel border border-divider bg-surface p-3"
    >
      {rail.map((step, idx) => {
        const clickable = step.href && step.state !== "upcoming" && step.state !== "skipped";
        const Icon =
          step.state === "done"
            ? CheckCircle2
            : step.state === "skipped"
              ? MinusCircle
              : CircleDashed;
        return (
          <button
            key={step.key}
            type="button"
            disabled={!clickable}
            aria-current={step.state === "current" ? "step" : undefined}
            onClick={() => {
              if (!clickable || !step.href || !id) return;
              nav(`/sows/${id}/${step.href}`);
            }}
            className={cn(
              "inline-flex items-center gap-2 rounded-control px-3 py-1 text-body",
              "focus-visible:outline-focus transition-motion",
              step.state === "done" && "text-success",
              step.state === "current" && "text-primary font-medium",
              step.state === "upcoming" && "text-text-secondary",
              step.state === "skipped" && "text-text-secondary opacity-70",
              clickable && "hover:bg-primary-subtle",
              !clickable && "cursor-default",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span>
              {idx + 1}. {step.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
