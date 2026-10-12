/**
 * Shared pieces for the Portfolio & Forecast screens (S22).
 *
 * The prototype (docs/reference/prototype/dealgate-portfolio.html) is the
 * approved layout; these map its classes onto DealGate v2.1 tokens:
 *   .panel → Panel, .pill → StatusPill, input.in (yellow editable) → cellInput,
 *   td.n (numeric) → numCell, tr.tot → totalsRow, td.calc → calcCell.
 */

import type { ReactNode } from "react";
import { useAuth } from "../../../auth/AuthProvider";
import { cn } from "../../../lib/cn";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import type { ForecastStatus } from "../../../api/engagements";

export const WRITE_ROLES = ["Delivery", "Finance", "SystemAdmin", "Sales", "SalesLeader"];
export const SETTINGS_WRITE_ROLES = ["SystemAdmin", "Finance"];
export const COST_ROLES = ["Delivery", "HR", "Finance", "CEO", "SystemAdmin"];

export function useGroups(): string[] {
  const { user } = useAuth();
  return user?.groups ?? [];
}

export function hasAny(groups: readonly string[], roles: readonly string[]): boolean {
  return roles.some((role) => groups.includes(role));
}

/** Yellow editable cell — the sheet's input colour, on the warning-surface token. */
export const cellInput =
  "min-h-control-compact w-full rounded-control border border-input-border bg-warning-surface px-2 py-1 text-table text-text tnum focus-visible:outline-focus disabled:bg-surface-sunken disabled:text-text-muted";
export const numCell = "px-3 py-2 text-right tnum whitespace-nowrap";
export const textCell = "px-3 py-2 whitespace-nowrap";
export const calcCell = "text-text-secondary";
export const headCell =
  "sticky top-0 bg-surface-sunken px-3 py-2 text-left text-label uppercase tracking-wide text-text-secondary whitespace-nowrap border-b border-divider";
export const headCellNum = cn(headCell, "text-right");
export const totalsRow = "bg-surface-sunken font-semibold";
export const tableWrap = "overflow-x-auto rounded-card border border-divider bg-surface";
export const table = "w-full border-collapse text-table [&_tbody_tr]:border-t [&_tbody_tr]:border-divider";

export function Panel({
  title,
  hint,
  children,
  className,
  id,
}: {
  title?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("rounded-card border border-divider bg-surface p-4", className)} aria-label={typeof title === "string" ? title : undefined}>
      {title ? <h2 className="text-section font-semibold text-text">{title}</h2> : null}
      {hint ? <p className="mt-1 text-secondary text-text-secondary">{hint}</p> : null}
      <div className={title || hint ? "mt-3" : undefined}>{children}</div>
    </section>
  );
}

export function StatusPill({ status, className }: { status: ForecastStatus; className?: string }) {
  const tone = status === "PASS" ? "success" : status === "BELOW FLOOR" ? "danger" : "warning";
  return <StatusBadge tone={tone} label={status} className={className} />;
}

export function Problems({ problems }: { problems: string[] | null }) {
  if (!problems || problems.length === 0) return null;
  return (
    <p role="alert" className="text-secondary text-danger">
      Missing: {problems.join(", ")}
    </p>
  );
}

export function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** Commit-on-blur text/number input for a yellow cell. */
export function CellInput({
  value,
  onCommit,
  type = "text",
  className,
  disabled,
  placeholder,
  title,
  step,
  min,
  max,
  ariaLabel,
}: {
  value: string;
  onCommit: (next: string) => void;
  type?: "text" | "number" | "date";
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  title?: string;
  step?: string | number;
  min?: string | number;
  max?: string | number;
  ariaLabel: string;
}) {
  return (
    <input
      key={value}
      type={type}
      defaultValue={value}
      aria-label={ariaLabel}
      className={cn(cellInput, type === "number" ? "w-24 text-right" : type === "date" ? "w-36" : "w-36", className)}
      disabled={disabled}
      placeholder={placeholder}
      title={title}
      step={step}
      min={min}
      max={max}
      onBlur={(event) => {
        if (event.target.value !== value) onCommit(event.target.value);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") (event.target as HTMLInputElement).blur();
      }}
    />
  );
}

export function CellSelect({
  value,
  onCommit,
  options,
  className,
  disabled,
  ariaLabel,
}: {
  value: string;
  onCommit: (next: string) => void;
  options: { value: string; label: string }[];
  className?: string;
  disabled?: boolean;
  ariaLabel: string;
}) {
  return (
    <select
      value={value}
      aria-label={ariaLabel}
      disabled={disabled}
      className={cn(cellInput, "w-auto min-w-[6rem]", className)}
      onChange={(event) => onCommit(event.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
