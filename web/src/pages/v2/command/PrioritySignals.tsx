/**
 * Priority signals — spec §5 item 2.
 *
 * Three clickable regions (one CEO exception, one MSA awaiting signature,
 * one approaching renewal). Each card is one big anchor so an assistive
 * technology reader hears the whole card as a single destination.
 *
 * The parent decides which signals to hydrate; missing signals render an
 * honest empty card that still points at the right module (spec §4).
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, type LucideIcon } from "lucide-react";
import { cn } from "../../../lib/cn";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";

export interface PrioritySignal {
  id: string;
  kind: "ceo_exception" | "msa_signature" | "renewal";
  title: string;
  client: string;
  reason: string;
  owner?: string | null;
  deadline?: string | null;
  href: string;
  statusLabel: string;
  statusTone: StatusTone;
  icon?: LucideIcon;
  testId?: string;
}

export interface PrioritySignalsProps {
  signals: PrioritySignal[];
  emptyMessage?: ReactNode;
}

export function PrioritySignals({ signals, emptyMessage }: PrioritySignalsProps) {
  if (signals.length === 0) {
    return (
      <section aria-label="Priority signals">
        <h2 className="text-section text-text mb-3">Priority signals</h2>
        <div
          role="status"
          className={cn(
            "rounded-panel border border-dashed border-divider bg-surface p-6",
            "text-body text-text-secondary",
          )}
        >
          {emptyMessage ?? "No signals need attention right now."}
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Priority signals">
      <h2 className="text-section text-text mb-3">Priority signals</h2>
      <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {signals.map((s) => (
          <li key={s.id}>
            <Link
              to={s.href}
              data-testid={s.testId ?? `signal-${s.kind}`}
              aria-label={`${s.title} — ${s.client}. ${s.reason}`}
              className={cn(
                "group flex h-full flex-col gap-3 rounded-panel border border-divider bg-surface p-4",
                "transition-motion hover:border-primary/40 hover:shadow-menu",
                "focus-visible:outline-focus",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-secondary uppercase tracking-wide text-text-secondary">
                    {s.title}
                  </p>
                  <p className="mt-1 text-section text-text truncate">
                    {s.client}
                  </p>
                </div>
                <StatusBadge
                  tone={s.statusTone}
                  label={s.statusLabel}
                  icon={s.icon}
                />
              </div>
              <p className="text-body text-text-secondary line-clamp-2">
                {s.reason}
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-secondary text-text-secondary">
                {s.owner ? <span>Owner: {s.owner}</span> : null}
                {s.deadline ? <span>Due: {s.deadline}</span> : null}
                <span className="ml-auto inline-flex items-center gap-1 text-primary group-hover:underline">
                  Open
                  <ArrowRight className="h-3 w-3" aria-hidden />
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
