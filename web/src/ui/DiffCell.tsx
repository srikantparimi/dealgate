import { useState } from "react";

/**
 * Inline "…" cell that expands to show a JSON diff of before/after payloads.
 * Purely presentational — no formatting rules beyond `JSON.stringify`.
 */
export function DiffCell({
  before,
  after,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}) {
  const [open, setOpen] = useState(false);
  const empty = before === null && after === null;
  if (empty) return <span>—</span>;
  return (
    <span>
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Hide diff" : "Show diff"}
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "1px solid #e5e7eb",
          borderRadius: 4,
          padding: "0 8px",
          cursor: "pointer",
          fontSize: 12,
          color: "#374151",
        }}
      >
        {open ? "hide" : "…"}
      </button>
      {open ? (
        <pre
          style={{
            marginTop: 6,
            padding: 8,
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 4,
            fontSize: 12,
            maxWidth: 360,
            overflowX: "auto",
            whiteSpace: "pre-wrap",
          }}
          aria-label="Diff details"
        >
          {"before: " + (before ? JSON.stringify(before) : "null") + "\n" +
            "after:  " + (after ? JSON.stringify(after) : "null")}
        </pre>
      ) : null}
    </span>
  );
}
