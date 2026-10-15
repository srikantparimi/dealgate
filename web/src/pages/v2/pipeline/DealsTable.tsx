// S23-PL2 F8/F13/F16 · the Opportunities list (spec §3). One table: from the
// `sm` breakpoint up it is a table (min 925 px, scrolling inside its panel);
// below it every row becomes a stacked card with inline labels (spec §9).
import { clsx } from "clsx";
import type { ReactNode } from "react";

import type { DealRow } from "../../../api/pipelineWorkspace";
import { cn } from "../../../lib/cn";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { calendarDate, shortMoney } from "./format";
import {
  AgreementTags,
  BusinessUnitLine,
  DealFlags,
  Glyph,
  OwnerChip,
  SowTag,
  StageProgress,
  StageTag,
  WatchStar,
  isOpenDeal,
} from "./tags";

export interface DealsTableProps {
  rows: DealRow[];
  today: string;
  selected: ReadonlySet<string>;
  onSelectedChange: (next: Set<string>) => void;
  /** The star state on screen (the row's, or the one the user just set). */
  isWatching: (deal: DealRow) => boolean;
  isWatchBusy: (deal: DealRow) => boolean;
  onToggleWatch: (deal: DealRow) => void;
  onOpenDeal: (deal: DealRow) => void;
  onOpenClient: (client: { id: string; name: string }) => void;
}

const HEADERS = [
  "Opportunity / client",
  "Sales stage",
  "Value / business unit",
  "Deal owner",
  "Close / activity",
  "SOW / agreements",
  "Next action",
];

/** Shown only on the phone, where the column headers are hidden. */
export function InlineLabel({ children }: { children: ReactNode }) {
  return <span className="mb-1 block text-label uppercase text-text-muted sm:hidden">{children}</span>;
}

export const cellClass = "min-w-0 break-words align-top sm:table-cell sm:border-t sm:border-border sm:px-2 sm:py-3";
export const linkButtonClass =
  "rounded-control text-left text-primary hover:underline focus-visible:outline-focus";

export function DealsTable({
  rows,
  today,
  selected,
  onSelectedChange,
  isWatching,
  isWatchBusy,
  onToggleWatch,
  onOpenDeal,
  onOpenClient,
}: DealsTableProps) {
  const pageIds = rows.map((d) => d.id);
  const pageSelected = pageIds.filter((id) => selected.has(id)).length;
  const allSelected = rows.length > 0 && pageSelected === rows.length;

  const togglePage = () => {
    const next = new Set(selected);
    if (allSelected) pageIds.forEach((id) => next.delete(id));
    else pageIds.forEach((id) => next.add(id));
    onSelectedChange(next);
  };
  const toggleRow = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  };

  return (
    <div className="sm:overflow-x-auto">
      <table className="block w-full text-table sm:table sm:min-w-[925px] sm:border-collapse">
        <thead className="hidden bg-surface-sunken sm:table-header-group">
          <tr>
            <th scope="col" className="w-10 py-2 pl-4 pr-2 text-left">
              <Checkbox
                aria-label="Select current page"
                checked={allSelected ? true : pageSelected > 0 ? "indeterminate" : false}
                onCheckedChange={togglePage}
                disabled={rows.length === 0}
              />
            </th>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-2 py-2 text-left text-secondary font-medium text-text-secondary">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="block sm:table-row-group">
          {rows.map((deal) => {
            const open = isOpenDeal(deal);
            const watching = isWatching(deal);
            return (
              <tr
                key={deal.id}
                className={cn(
                  "grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border p-4 first:border-t-0",
                  "sm:table-row sm:border-t-0 sm:p-0 sm:hover:bg-surface-sunken",
                  selected.has(deal.id) && "bg-primary-subtle",
                )}
              >
                <td className={cn("hidden w-10 sm:pl-4", cellClass)}>
                  <Checkbox
                    aria-label={`Select ${deal.title}`}
                    checked={selected.has(deal.id)}
                    onCheckedChange={() => toggleRow(deal.id)}
                  />
                </td>
                <td className={cn("col-span-2", cellClass)}>
                  <div className="flex flex-col items-start gap-1">
                    <button
                      type="button"
                      onClick={() => onOpenDeal(deal)}
                      className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus"
                    >
                      {deal.title}
                    </button>
                    {deal.client.id && deal.client.name ? (
                      <button
                        type="button"
                        onClick={() => onOpenClient({ id: deal.client.id!, name: deal.client.name! })}
                        className="rounded-control text-left text-secondary text-text-secondary hover:underline focus-visible:outline-focus"
                      >
                        {deal.client.name}
                        <Glyph>↗</Glyph>
                      </button>
                    ) : (
                      <span className="text-secondary text-text-secondary">No client</span>
                    )}
                    <DealFlags deal={deal} />
                  </div>
                </td>
                <td className={cellClass}>
                  <InlineLabel>Sales stage</InlineLabel>
                  <StageTag deal={deal} />
                  <StageProgress deal={deal} />
                </td>
                <td className={cellClass}>
                  <InlineLabel>Value / business unit</InlineLabel>
                  <span className="block font-mono text-body font-semibold text-text tnum">
                    {shortMoney(deal.amount, { currency: deal.currency })}
                  </span>
                  <BusinessUnitLine deal={deal} />
                </td>
                <td className={cellClass}>
                  <InlineLabel>Deal owner</InlineLabel>
                  <OwnerChip owner={deal.deal_owner} warnWhenNone={open} />
                </td>
                <td className={cn("sm:min-w-[7.5rem]", cellClass)}>
                  <InlineLabel>Close / activity</InlineLabel>
                  <CloseDate deal={deal} today={today} />
                  <span className="block text-secondary text-text-secondary">{activityText(deal)}</span>
                </td>
                <td className={cellClass}>
                  <InlineLabel>SOW / agreements</InlineLabel>
                  <span className="flex flex-col items-start gap-1">
                    <SowTag deal={deal} />
                    <AgreementTags agreements={deal.agreements} />
                  </span>
                </td>
                <td className={cn("col-span-2 sm:min-w-[9.5rem] sm:pr-4", cellClass)}>
                  <div className="flex items-start justify-between gap-2 sm:flex-col sm:justify-start sm:gap-1">
                    <NextActionCell deal={deal} open={open} today={today} onOpenDeal={onOpenDeal} />
                    <WatchStar
                      title={deal.title}
                      watching={watching}
                      busy={isWatchBusy(deal)}
                      onToggle={() => onToggleWatch(deal)}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CloseDate({ deal, today }: { deal: DealRow; today: string }) {
  if (!deal.close_date) return <span className="block text-table text-text-secondary">Not set</span>;
  const passed = deal.flags.includes("close_passed");
  return (
    <span className={clsx("block text-table", passed ? "font-medium text-warning" : "text-text")}>
      {passed ? `${calendarDate(deal.close_date, today)} · passed` : calendarDate(deal.close_date, today)}
    </span>
  );
}

export function activityText(deal: Pick<DealRow, "last_activity_date" | "days_since_activity">): string {
  if (!deal.last_activity_date) return "No activity recorded";
  return deal.days_since_activity !== null ? `${deal.days_since_activity}d since activity` : deal.last_activity_date;
}

function NextActionCell({
  deal,
  open,
  today,
  onOpenDeal,
}: {
  deal: DealRow;
  open: boolean;
  today: string;
  onOpenDeal: (deal: DealRow) => void;
}) {
  const action = deal.next_action;
  if (action) {
    const overdue = deal.flags.includes("action_overdue");
    return (
      <span className="flex min-w-0 flex-col items-start gap-1">
        <button type="button" onClick={() => onOpenDeal(deal)} className={clsx(linkButtonClass, "text-table font-medium")}>
          {action.text}
          <Glyph>→</Glyph>
        </button>
        <span className={clsx("text-secondary", overdue ? "font-medium text-warning" : "text-text-secondary")}>
          {action.due_on
            ? overdue
              ? `${calendarDate(action.due_on, today)} · overdue`
              : calendarDate(action.due_on, today)
            : "No due date"}
        </span>
      </span>
    );
  }
  if (open) {
    return (
      <button type="button" onClick={() => onOpenDeal(deal)} className={clsx(linkButtonClass, "text-table font-medium")}>
        Set next action
        <Glyph>→</Glyph>
      </button>
    );
  }
  return <span className="text-secondary text-text-secondary">—</span>;
}
