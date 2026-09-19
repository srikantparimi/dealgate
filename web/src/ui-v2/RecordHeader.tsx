import type { ReactNode } from "react";
import { cn } from "../lib/cn";

/**
 * Persistent workspace header for SOW / opportunity records (spec §8).
 * Shows client → record name breadcrumb, key identity, and a right-slot
 * for the "next valid step" primary action.
 */
export interface RecordHeaderProps {
  eyebrow?: ReactNode;
  title: ReactNode;
  identity?: ReactNode;
  status?: ReactNode;
  primaryAction?: ReactNode;
  className?: string;
}

export function RecordHeader({
  eyebrow,
  title,
  identity,
  status,
  primaryAction,
  className,
}: RecordHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 border-b border-divider pb-4",
        "sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-secondary text-text-secondary uppercase tracking-wide">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-1 text-page-mobile sm:text-page text-text truncate">
          {title}
        </h1>
        {identity ? (
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-secondary text-text-secondary">
            {identity}
          </div>
        ) : null}
        {status ? <div className="mt-3 flex flex-wrap gap-2">{status}</div> : null}
      </div>
      {primaryAction ? (
        <div className="flex items-center gap-2">{primaryAction}</div>
      ) : null}
    </header>
  );
}
