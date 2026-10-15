// S23-PL2 F7 · the filter toolbar: search, status, owner (deal or account by
// tab), business unit, date and more filters. Every control changes the
// workspace query through the page's transitions (workspaceState.ts).
// Also home to the right-drawer shell every Pipeline dialog uses (F17: Radix
// gives the focus trap, Escape and focus return).
import { clsx } from "clsx";
import { useEffect, useState, type ReactNode } from "react";

import type { WorkspaceStatus } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../../ui-v2/primitives/sheet";
import type { WorkspaceUrlState } from "./workspaceState";

const SELECT_BASE =
  "h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus disabled:opacity-60";

/** Native select styled like the kit's Input (full width, for dialog forms). */
export const SELECT_CLASS = `${SELECT_BASE} w-full`;

/** Shared props of every drawer the page opens. */
export interface DrawerControlProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The page returns focus to the control that opened the drawer. */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * A form label with the kit Label's look. The kit's `Label` passes its classes
 * through tailwind-merge, which drops the custom font size (`text-secondary`)
 * next to a colour class; a plain label keeps both.
 */
export function FieldLabel({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-secondary font-medium text-text-secondary">
      {children}
    </label>
  );
}

export interface PipelineDrawerProps extends DrawerControlProps {
  kicker?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}

/** The right-side drawer every Pipeline dialog opens in (prototype §8). */
export function PipelineDrawer({
  open,
  onOpenChange,
  onCloseAutoFocus,
  kicker,
  title,
  description,
  children,
}: PipelineDrawerProps) {
  const describedBy = description ? {} : { "aria-describedby": undefined };
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="flex flex-col gap-5 overflow-y-auto sm:max-w-[530px]"
        onCloseAutoFocus={onCloseAutoFocus}
        {...describedBy}
      >
        <SheetHeader className="pr-10">
          {kicker ? <p className="font-mono text-label uppercase text-primary-text">{kicker}</p> : null}
          <SheetTitle>
            <span className="text-section text-text">{title}</span>
          </SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        {children}
      </SheetContent>
    </Sheet>
  );
}

const STATUS_OPTIONS: { value: WorkspaceStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "all", label: "All statuses" },
  { value: "won", label: "Closed won" },
  { value: "lost", label: "Closed lost" },
  { value: "hold", label: "On hold only" },
];

const FILTER_BUTTON =
  "inline-flex h-10 items-center gap-1 rounded-control border px-3 text-body whitespace-nowrap focus-visible:outline-focus disabled:opacity-60";

function filterButtonClass(active: boolean): string {
  return clsx(
    FILTER_BUTTON,
    active
      ? "border-primary bg-primary-subtle text-primary-text"
      : "border-input-border bg-surface text-text hover:bg-primary-subtle",
  );
}

export interface FilterToolbarProps {
  state: WorkspaceUrlState;
  /** False until the first workspace arrives: the owner and business-unit lists come from it. */
  ready: boolean;
  onSearch: (q: string) => void;
  onStatus: (status: WorkspaceStatus) => void;
  onOpenOwner: () => void;
  onOpenBusinessUnit: () => void;
  onOpenDate: () => void;
  onOpenMore: () => void;
}

export function FilterToolbar({
  state,
  ready,
  onSearch,
  onStatus,
  onOpenOwner,
  onOpenBusinessUnit,
  onOpenDate,
  onOpenMore,
}: FilterToolbarProps) {
  const q = state.query;
  // The URL keeps the trimmed search; the box keeps what is typed (a trailing
  // space between words), and follows the URL when it changes elsewhere.
  const [draft, setDraft] = useState(q.q);
  useEffect(() => {
    setDraft((current) => (current.trim() === q.q.trim() ? current : q.q));
  }, [q.q]);

  const clients = q.tab === "clients";
  const owners = clients ? q.account_owner : q.owner;
  const ownerLabel = `${clients ? "Account owner" : "Deal owner"}${owners.length ? ` · ${owners.length}` : ""}`;
  const buLabel = `Business unit${q.bu.length ? ` · ${q.bu.length}` : ""}`;
  const moreCount = [q.sow, q.attention, q.missing, q.group, q.watching].filter(Boolean).length;

  return (
    <section
      aria-label="Pipeline filters"
      className="flex flex-wrap items-center gap-2 rounded-card border border-border bg-surface p-3"
    >
      <div className="relative min-w-full flex-1 sm:min-w-[240px]">
        <span aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary">
          ⌕
        </span>
        <Input
          type="search"
          value={draft}
          maxLength={120}
          onChange={(event) => {
            setDraft(event.target.value);
            onSearch(event.target.value);
          }}
          placeholder="Search deals, clients, owners or next actions…"
          aria-label="Search deals, clients, owners or next actions"
          className="pl-8"
        />
      </div>
      <select
        aria-label="Deal status"
        value={q.status}
        onChange={(event) => onStatus(event.target.value as WorkspaceStatus)}
        className={SELECT_BASE}
      >
        {STATUS_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        aria-haspopup="dialog"
        disabled={!ready}
        onClick={onOpenOwner}
        className={filterButtonClass(owners.length > 0)}
      >
        {ownerLabel}
        <span aria-hidden> ⌄</span>
      </button>
      <button
        type="button"
        aria-haspopup="dialog"
        disabled={!ready}
        onClick={onOpenBusinessUnit}
        className={filterButtonClass(q.bu.length > 0)}
      >
        {buLabel}
        <span aria-hidden> ⌄</span>
      </button>
      <button
        type="button"
        aria-haspopup="dialog"
        disabled={!ready}
        onClick={onOpenDate}
        className={filterButtonClass(q.date_preset !== "any")}
      >
        Date
        <span aria-hidden> ⌄</span>
      </button>
      <Button
        variant="secondary"
        aria-haspopup="dialog"
        disabled={!ready}
        onClick={onOpenMore}
        className={clsx(moreCount > 0 && "border-primary bg-primary-subtle")}
      >
        More filters
        {moreCount ? <span className="font-mono text-primary-text">{moreCount}</span> : null}
      </Button>
    </section>
  );
}
