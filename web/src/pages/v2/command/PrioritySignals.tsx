/**
 * Priority signals — DealGate v2.1 prototype (lines 194–200, 360–373).
 *
 * Three clickable `.sig` cards laid out on a three-column grid. Each
 * card has:
 *   - Left icon tile (36×36) tinted `bad / warn / prog`.
 *   - Title row combining a bold heading and an inline StatusBadge.
 *   - Description paragraph (14px, text-2).
 *   - Meta row with owner / age / version bits (12px, text-3).
 *
 * Whole card is one anchor so screen readers hear a single destination.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { cn } from "../../../lib/cn";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";

export interface PrioritySignal {
  id: string;
  kind: "ceo_exception" | "msa_signature" | "renewal";
  /** Bold heading (e.g. "Northstar Health · CEO exception"). */
  title: string;
  /** Optional secondary line used only when title needs a client anchor. */
  client?: string;
  /** Description paragraph (spec §5). */
  reason: string;
  owner?: string | null;
  deadline?: string | null;
  version?: string | null;
  href: string;
  statusLabel: string;
  statusTone: StatusTone;
  /** Icon rendered inside the left tile. */
  icon?: LucideIcon;
  /** Tint for the icon tile — `bad | warn | prog`. */
  iconTone?: "bad" | "warn" | "prog";
  testId?: string;
}

export interface PrioritySignalsProps {
  signals: PrioritySignal[];
  emptyMessage?: ReactNode;
}

const ICON_TILE_CLASSES: Record<"bad" | "warn" | "prog", string> = {
  bad: "bg-danger-surface text-danger",
  warn: "bg-warning-surface text-warning",
  prog: "bg-primary-subtle text-primaryText",
};

function iconToneForStatus(tone: StatusTone): "bad" | "warn" | "prog" {
  if (tone === "danger") return "bad";
  if (tone === "warning" || tone === "warn") return "warn";
  return "prog";
}

export function PrioritySignals({ signals, emptyMessage }: PrioritySignalsProps) {
  if (signals.length === 0) {
    return (
      <section aria-label="Priority signals">
        <div
          role="status"
          className={cn(
            "rounded-card border border-dashed border-border bg-surface p-6",
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
      <ul
        className={cn(
          "grid gap-3",
          "md:grid-cols-2 lg:grid-cols-3",
        )}
      >
        {signals.map((s) => {
          const Icon = s.icon;
          const iconTone = s.iconTone ?? iconToneForStatus(s.statusTone);
          return (
            <li key={s.id}>
              <Link
                to={s.href}
                data-testid={s.testId ?? `signal-${s.kind}`}
                aria-label={`${s.title}. ${s.reason}`}
                className={cn(
                  "grid grid-cols-[auto_1fr] gap-3 rounded-card border border-border",
                  "bg-surface p-4",
                  "transition-motion hover:border-borderStrong",
                  "focus-visible:outline-focus",
                  "text-text",
                )}
              >
                <div
                  aria-hidden
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-[8px]",
                    ICON_TILE_CLASSES[iconTone],
                  )}
                >
                  {Icon ? <Icon className="h-[18px] w-[18px]" /> : null}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-body font-semibold text-text">
                      {s.title}
                    </p>
                    <StatusBadge tone={s.statusTone} label={s.statusLabel} />
                  </div>
                  <p className="mt-1 text-secondary text-text-secondary">
                    {s.reason}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-text-muted">
                    {s.owner ? <span>Owner: {s.owner}</span> : null}
                    {s.deadline ? <span>{s.deadline}</span> : null}
                    {s.version ? <span>{s.version}</span> : null}
                  </div>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
