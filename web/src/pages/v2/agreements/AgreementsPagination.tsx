// S24-AG1 F1/F8/F9 · paging for the Clients, Documents and Activity lists:
// 25 / 50 / 100 rows only (the API answers 422 for any other size), the
// prototype's "1–25 of 208" and "1 / 9".
import { useId } from "react";

import { AGREEMENTS_PAGE_SIZES, type AgreementsPageSize } from "../../../api/agreements";
import { cn } from "../../../lib/cn";

export interface AgreementsPaginationProps {
  total: number;
  page: number;
  pageSize: AgreementsPageSize;
  onPage: (page: number) => void;
  onPageSize: (size: AgreementsPageSize) => void;
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}

const arrowClass = cn(
  "inline-flex h-8 w-8 items-center justify-center rounded-control border border-input-border bg-surface text-text",
  "transition-motion hover:bg-primary-subtle focus-visible:outline-focus disabled:pointer-events-none disabled:opacity-60",
);

export function AgreementsPagination({ total, page, pageSize, onPage, onPageSize }: AgreementsPaginationProps) {
  const rowsId = useId();
  const pages = pageCount(total, pageSize);
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-secondary text-text-secondary">
      <span className="tnum">{`${Math.min(first, total)}–${last} of ${total}`}</span>
      <span className="flex items-center gap-2">
        <label htmlFor={rowsId}>Rows</label>
        <select
          id={rowsId}
          value={String(pageSize)}
          onChange={(e) => onPageSize(Number(e.target.value) as AgreementsPageSize)}
          className="h-8 rounded-control border border-input-border bg-surface px-2 text-table text-text focus-visible:outline-focus"
        >
          {AGREEMENTS_PAGE_SIZES.map((size) => (
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
