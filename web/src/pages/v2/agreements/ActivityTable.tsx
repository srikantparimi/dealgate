// S24-AG1 F9/B15 · the Activity tab: agreement events read from the audit log,
// newest first: When (Pacific date), Who (a person's name) and What (the
// server's sentence). A client id never shows; every value is a text node.
import { cn } from "../../../lib/cn";
import type { ActivityRow } from "../../../api/agreements";
import { InlineLabel, cellClass } from "../pipeline/DealsTable";
import { pacificDate } from "./agreementsFormat";

const HEADERS = ["When", "Who", "What"];

export function ActivityTable({ rows }: { rows: ActivityRow[] }) {
  return (
    <div className="sm:overflow-x-auto">
      <table aria-label="Activity" className="block w-full text-table sm:table sm:min-w-[640px] sm:border-collapse">
        <thead className="hidden bg-surface-sunken sm:table-header-group">
          <tr>
            {HEADERS.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={`${i === 0 ? "pl-4 pr-2" : i === HEADERS.length - 1 ? "pl-2 pr-4" : "px-2"} py-2 text-left text-secondary font-medium text-text-secondary`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="block sm:table-row-group">
          {rows.map((row, i) => (
            <tr
              key={`${row.at}-${i}`}
              className={cn(
                "grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border p-4 first:border-t-0",
                "sm:table-row sm:border-t-0 sm:p-0 sm:hover:bg-surface-sunken",
              )}
            >
              <td className={cn(cellClass, "sm:w-[150px] sm:pl-4")}>
                <InlineLabel>When</InlineLabel>
                <span className="whitespace-nowrap text-table text-text">{pacificDate(row.at)}</span>
              </td>
              <td className={cn("sm:w-[200px]", cellClass)}>
                <InlineLabel>Who</InlineLabel>
                <span className="text-table text-text [overflow-wrap:anywhere]">{row.by}</span>
              </td>
              <td className={cn(cellClass, "col-span-2 sm:pr-4")}>
                <InlineLabel>What</InlineLabel>
                <span className="text-table text-text [overflow-wrap:anywhere]">{row.text}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
