import type { ReactNode } from "react";

/**
 * Row of filter controls placed under a `PageHeader`. Purely a layout
 * primitive so pages don't hand-roll inline flex containers.
 */
export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div
      role="group"
      aria-label="Filters"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        alignItems: "center",
        marginBottom: 16,
      }}
    >
      {children}
    </div>
  );
}

export function Pager({
  page,
  pageCount,
  onChange,
}: {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
}) {
  const disabledPrev = page <= 1;
  const disabledNext = page >= pageCount;
  return (
    <div
      role="navigation"
      aria-label="Pagination"
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        marginTop: 12,
        justifyContent: "flex-end",
        fontSize: 14,
        color: "#374151",
      }}
    >
      <button
        type="button"
        onClick={() => onChange(page - 1)}
        disabled={disabledPrev}
        style={{
          padding: "4px 10px",
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          background: "white",
          cursor: disabledPrev ? "not-allowed" : "pointer",
          color: disabledPrev ? "#9ca3af" : "#111827",
        }}
      >
        Prev
      </button>
      <span>
        Page {page} of {Math.max(1, pageCount)}
      </span>
      <button
        type="button"
        onClick={() => onChange(page + 1)}
        disabled={disabledNext}
        style={{
          padding: "4px 10px",
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          background: "white",
          cursor: disabledNext ? "not-allowed" : "pointer",
          color: disabledNext ? "#9ca3af" : "#111827",
        }}
      >
        Next
      </button>
    </div>
  );
}
