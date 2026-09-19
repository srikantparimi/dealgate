/**
 * Section shell — one card per confirmation-screen block.
 *
 * Cards use a 1px border and a 12px radius; no shadow (v2.1 addendum).
 * The header exposes a jump anchor so the "What's still needed" list
 * can scroll to the exact section that owns a missing field.
 */
import type { ReactNode } from "react";
import { cn } from "../../../../lib/cn";

export interface SectionProps {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Section({
  id,
  title,
  description,
  actions,
  children,
  className,
}: SectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn(
        "rounded-card border border-border bg-surface p-4 scroll-mt-20",
        className,
      )}
    >
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2
            id={`${id}-title`}
            className="text-section text-text"
          >
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-body text-text-secondary">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex items-center gap-2">{actions}</div>
        ) : null}
      </header>
      {children}
    </section>
  );
}
