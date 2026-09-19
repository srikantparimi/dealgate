import { InboxIcon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: LucideIcon;
  className?: string;
}

/**
 * Neutral empty state — spec §4 requires an honest "no records yet"
 * message plus a permitted recovery action. Never used to mask a failure.
 */
export function EmptyState({
  title,
  description,
  action,
  icon: Icon = InboxIcon,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-panel border border-dashed border-divider p-8 text-center",
        className,
      )}
    >
      <Icon className="h-8 w-8 text-text-secondary" aria-hidden />
      <div>
        <h3 className="text-section text-text">{title}</h3>
        {description ? (
          <p className="mt-1 text-body text-text-secondary">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
