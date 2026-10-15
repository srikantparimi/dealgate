// S23-PL2 F9/F16 · the Clients list (spec §4): a table from `sm` up, stacked
// cards with inline labels below. Flags come from the client's matching open
// deals only (B13); a client without matching deals shows reasons, not zeros
// standing in for values.
import { clsx } from "clsx";

import type { ClientRow } from "../../../api/pipelineWorkspace";
import { cn } from "../../../lib/cn";
import type { ClientRef } from "./ClientPreview";
import { InlineLabel, cellClass, linkButtonClass } from "./DealsTable";
import { calendarDate, plural, shortMoney } from "./format";
import { AgreementTags, ClientFlagsText, CompanyMark, Glyph, OwnerChip, openDealsText } from "./tags";

export interface ClientsTableProps {
  rows: ClientRow[];
  today: string;
  /** Passes the row's facts, so the preview of a client without deals still shows them. */
  onOpenClient: (client: ClientRef) => void;
}

const HEADERS = ["Client", "Account owner", "Matching / open", "Matching value", "Agreements", "Attention", "Last activity"];

export function ClientsTable({ rows, today, onOpenClient }: ClientsTableProps) {
  return (
    <div className="sm:overflow-x-auto">
      <table className="block w-full text-table sm:table sm:min-w-[925px] sm:border-collapse">
        <thead className="hidden bg-surface-sunken sm:table-header-group">
          <tr>
            {HEADERS.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={`${i === 0 ? "pl-4 pr-2" : "px-2"} py-2 text-left text-secondary font-medium text-text-secondary`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="block sm:table-row-group">
          {rows.map((c) => {
            const facts = { account_owner: c.account_owner, agreements: c.agreements };
            const open = () => onOpenClient({ id: c.id, name: c.name, facts });
            return (
              <tr
                key={c.id}
                className={cn(
                  "grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border p-4 first:border-t-0",
                  "sm:table-row sm:border-t-0 sm:p-0 sm:hover:bg-surface-sunken",
                )}
              >
                <td className={cn("col-span-2 sm:pl-4", cellClass)}>
                  <span className="flex items-start gap-3">
                    <CompanyMark name={c.name} />
                    <span className="flex flex-col items-start">
                      <button
                        type="button"
                        onClick={open}
                        className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus"
                      >
                        {c.name}
                      </button>
                      <span className="text-secondary text-text-secondary">{openDealsText(c.open_deals)}</span>
                    </span>
                  </span>
                </td>
                <td className={cellClass}>
                  <InlineLabel>Account owner</InlineLabel>
                  <OwnerChip owner={c.account_owner} />
                </td>
                <td className={cellClass}>
                  <InlineLabel>Matching / open</InlineLabel>
                  <strong className="font-mono text-body font-semibold text-text tnum">
                    {c.matching_deals} <span className="font-normal text-text-muted">{`/ ${c.open_deals}`}</span>
                  </strong>
                </td>
                <td className={cellClass}>
                  <InlineLabel>Matching value</InlineLabel>
                  <MatchingValue row={c} />
                </td>
                <td className={cellClass}>
                  <InlineLabel>Agreements</InlineLabel>
                  <AgreementTags agreements={c.agreements} />
                </td>
                <td className={cellClass}>
                  <InlineLabel>Attention</InlineLabel>
                  <ClientFlagsText flags={c.flags} />
                </td>
                <td className={cn("col-span-2 sm:pr-4", cellClass)}>
                  <div className="flex items-start justify-between gap-3 sm:flex-col sm:justify-start sm:gap-1">
                    <InlineLabel>Last activity</InlineLabel>
                    <LastActivity row={c} today={today} />
                    <button
                      type="button"
                      onClick={open}
                      aria-label={`Preview ${c.name}`}
                      className={clsx(linkButtonClass, "shrink-0 text-table font-semibold")}
                    >
                      Preview
                      <Glyph>→</Glyph>
                    </button>
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

function MatchingValue({ row }: { row: ClientRow }) {
  if (row.matching_deals === 0) {
    return <span className="text-table text-text-secondary">No matching deals</span>;
  }
  return (
    <span className="flex flex-col">
      <strong className="font-mono text-body font-semibold text-text tnum">{shortMoney(row.matching_value_usd)}</strong>
      {row.matching_value_usd !== null ? (
        <span className="text-secondary text-text-secondary">USD · unweighted</span>
      ) : null}
    </span>
  );
}

function LastActivity({ row, today }: { row: ClientRow; today: string }) {
  if (!row.last_activity_date) {
    return <span className="text-table text-text-secondary">No matching activity</span>;
  }
  return (
    <span className="flex flex-col">
      <span className="text-table text-text">{calendarDate(row.last_activity_date, today)}</span>
      {row.days_since_activity !== null ? (
        <span className="text-secondary text-text-secondary">
          {`${row.days_since_activity} ${plural(row.days_since_activity, "day", "days")} ago`}
        </span>
      ) : null}
    </span>
  );
}
