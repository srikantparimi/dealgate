// S23-PL2 D11/B9 · paging for the Pipeline records: 25 / 50 / 100 rows only.
// The deals board shows every filtered deal, so it gets a summary, not pager
// controls that could not change anything.
import { useId } from "react";

import { WORKSPACE_PAGE_SIZES, type WorkspacePageSize, type WorkspaceTab } from "../../../api/pipelineWorkspace";
import { cn } from "../../../lib/cn";
import { plural } from "./format";

export interface PaginationProps {
  tab: WorkspaceTab;
  totalRows: number;
  /** The page and size of the rows on screen. */
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: WorkspacePageSize) => void;
}

export function pageCount(totalRows: number, pageSize: number): number {
  return Math.max(1, Math.ceil(totalRows / Math.max(1, pageSize)));
}

const footerClass =
  "flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-secondary text-text-secondary";
const arrowClass = cn(
  "inline-flex h-8 w-8 items-center justify-center rounded-control border border-input-border bg-surface text-text",
  "transition-motion hover:bg-primary-subtle focus-visible:outline-focus disabled:pointer-events-none disabled:opacity-60",
);

export function Pagination({ tab, totalRows, page, pageSize, onPage, onPageSize }: PaginationProps) {
  const rowsId = useId();
  const pages = pageCount(totalRows, pageSize);
  const first = totalRows === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, totalRows);
  const noun = tab === "deals" ? plural(totalRows, "opportunity", "opportunities") : plural(totalRows, "client", "clients");
  return (
    <div className={footerClass}>
      <span className="tnum">{`${first}–${last} of ${totalRows} ${noun}`}</span>
      <span className="flex items-center gap-2">
        <label htmlFor={rowsId}>Rows</label>
        <select
          id={rowsId}
          value={String(pageSize)}
          onChange={(e) => onPageSize(Number(e.target.value) as WorkspacePageSize)}
          className="h-8 rounded-control border border-input-border bg-surface px-2 text-table text-text focus-visible:outline-focus"
        >
          {WORKSPACE_PAGE_SIZES.map((size) => (
            <option key={size} value={String(size)}>
              {size}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className={arrowClass}
        >
          <span aria-hidden="true">←</span>
        </button>
        <span className="font-mono tnum">{`${Math.min(page, pages)} / ${pages}`}</span>
        <button
          type="button"
          aria-label="Next page"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          className={arrowClass}
        >
          <span aria-hidden="true">→</span>
        </button>
      </span>
    </div>
  );
}

/** "109 opportunities across 7 stages" · "All filtered deals". */
export function BoardSummary({ totalRows, lanes }: { totalRows: number; lanes: number }) {
  return (
    <div className={footerClass}>
      <span className="tnum">
        {`${totalRows} ${plural(totalRows, "opportunity", "opportunities")} across ${lanes} ${plural(lanes, "stage", "stages")}`}
      </span>
      <span>All filtered deals</span>
    </div>
  );
}
