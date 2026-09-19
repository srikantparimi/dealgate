import { AlertOctagon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface ErrorStateProps {
  title: ReactNode;
  description?: ReactNode;
  retryLabel?: string;
  onRetry?: () => void;
  supportRef?: ReactNode;
  className?: string;
}

/**
 * Full-panel error placeholder. Spec §4: name the problem and the
 * recovery; keep filters. Errors in one dashboard module never hide
 * the healthy ones — callers scope this to the failing region.
 */
export function ErrorState({
  title,
  description,
  retryLabel = "Retry",
  onRetry,
  supportRef,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-panel border border-danger/40 bg-danger-surface p-6 text-center",
        className,
      )}
    >
      <AlertOctagon className="h-8 w-8 text-danger" aria-hidden />
      <div>
        <h3 className="text-section text-text">{title}</h3>
        {description ? (
          <p className="mt-1 text-body text-text-secondary">{description}</p>
        ) : null}
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-control bg-surface px-3 py-1 text-body text-text border border-input-border focus-visible:outline-focus"
        >
          {retryLabel}
        </button>
      ) : null}
      {supportRef ? (
        <p className="text-secondary text-text-secondary">{supportRef}</p>
      ) : null}
    </div>
  );
}
