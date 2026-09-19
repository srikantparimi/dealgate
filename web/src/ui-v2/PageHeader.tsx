import type { ReactNode } from "react";
import { cn } from "../lib/cn";

/**
 * Working page header — title, optional subtitle, right-slot actions.
 * Spec §2: page heading is 32/38 (28/34 on narrow). One primary button
 * per page or decision region.
 */
export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 pb-6 sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="text-page-mobile sm:text-page text-text truncate">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-body text-text-secondary">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
