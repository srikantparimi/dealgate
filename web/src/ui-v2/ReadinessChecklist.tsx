import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { StatusBadge, type StatusTone } from "./StatusBadge";

export interface ReadinessItem {
  id: string;
  label: ReactNode;
  status: StatusTone;
  statusLabel: string;
  owner?: ReactNode;
  due?: ReactNode;
  hint?: ReactNode;
}

export interface ReadinessChecklistProps {
  items: ReadinessItem[];
  title?: ReactNode;
  className?: string;
}

/**
 * Readiness checklist — the side-panel that always explains why the
 * primary action is disabled (spec §8). No item may be "green" without
 * an accompanying label; the server owns the underlying truth.
 */
export function ReadinessChecklist({
  items,
  title,
  className,
}: ReadinessChecklistProps) {
  return (
    <section
      className={cn(
        "rounded-panel border border-divider bg-surface p-4",
        className,
      )}
      aria-label={typeof title === "string" ? title : "Readiness"}
    >
      {title ? (
        <h2 className="text-section text-text mb-3">{title}</h2>
      ) : null}
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.id} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-body text-text">{item.label}</span>
              <StatusBadge tone={item.status} label={item.statusLabel} />
            </div>
            {(item.owner || item.due || item.hint) && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-secondary text-text-secondary">
                {item.owner ? <span>Owner: {item.owner}</span> : null}
                {item.due ? <span>Due: {item.due}</span> : null}
                {item.hint ? <span>{item.hint}</span> : null}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
