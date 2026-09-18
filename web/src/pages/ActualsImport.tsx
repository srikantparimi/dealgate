/**
 * Actuals CSV import (S6 E9, Finance/SystemAdmin).
 *
 * One dropzone, one preview table, one submit button. The preview parses
 * the CSV in the browser purely so Finance can eyeball row status; the
 * REAL validation runs server-side, and any per-row error the API
 * returns (unknown resource_line_id, missing actual_cost, etc.) is
 * rendered against the same row numbers. Zero business math lives here.
 */

import { useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import {
  ApiError,
  importActualsCsv,
  type ActualBatch,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

const CSV_TYPES = new Set([
  "text/csv",
  "application/csv",
  "application/vnd.ms-excel",
  "",
]);

const REQUIRED_COLUMNS = [
  "sow_ref",
  "resource_line_id",
  "period_month",
  "actual_hours",
  "actual_cost",
  "actual_revenue",
] as const;

type ClientRowStatus = "ok" | "warn" | "error";

interface PreviewRow {
  id: number; // row_number (1 = header, so first data row = 2)
  sow_ref: string;
  resource_line_id: string;
  period_month: string;
  actual_hours: string;
  actual_cost: string;
  actual_revenue: string;
  status: ClientRowStatus;
  message: string;
  serverError?: string;
}

export function ActualsImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [batch, setBatch] = useState<ActualBatch | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<
    Array<Record<string, unknown>>
  >([]);

  const previewColumns: Column<PreviewRow>[] = useMemo(
    () => [
      { key: "row", header: "Row", render: (r) => String(r.id) },
      { key: "sow_ref", header: "sow_ref", render: (r) => r.sow_ref || "-" },
      {
        key: "resource_line_id",
        header: "resource_line_id",
        render: (r) => (
          <span style={{ fontFamily: "monospace", fontSize: 12 }}>
            {r.resource_line_id || "-"}
          </span>
        ),
      },
      { key: "period", header: "period_month", render: (r) => r.period_month || "-" },
      { key: "hours", header: "hours", render: (r) => r.actual_hours || "-" },
      { key: "cost", header: "cost", render: (r) => r.actual_cost || "-" },
      { key: "revenue", header: "revenue", render: (r) => r.actual_revenue || "-" },
      {
        key: "status",
        header: "Status",
        render: (r) => (
          <StatusChip
            tone={
              r.status === "error"
                ? "block"
                : r.status === "warn"
                  ? "warn"
                  : "ok"
            }
          >
            {r.serverError ?? r.message}
          </StatusChip>
        ),
      },
    ],
    [],
  );

  function stagePreview(f: File) {
    setFile(f);
    setBatch(null);
    setSubmitError(null);
    setServerErrors([]);
    setPreviewError(null);
    parseCsvFile(f)
      .then((rows) => setPreview(rows))
      .catch((e) => {
        setPreview([]);
        setPreviewError(e instanceof Error ? e.message : String(e));
      });
  }

  async function submit() {
    if (!file) return;
    setSubmitting(true);
    setSubmitError(null);
    setServerErrors([]);
    try {
      const res = await importActualsCsv(file);
      setBatch(res);
    } catch (err) {
      if (err instanceof ApiError) {
        // FastAPI wraps HTTPException(detail=...) in ``{"detail": ...}``.
        // Accept either shape so this code survives a router refactor.
        const raw = err.detail as
          | {
              detail?: { message?: string; errors?: Array<Record<string, unknown>> };
              message?: string;
              errors?: Array<Record<string, unknown>>;
            }
          | null;
        const detail =
          raw && typeof raw === "object" && "detail" in raw && raw.detail
            ? raw.detail
            : raw ?? {};
        setSubmitError(detail?.message ?? err.message);
        if (detail && Array.isArray(detail.errors)) {
          setServerErrors(detail.errors);
          // Overlay per-row error onto the preview so the user sees red rows.
          setPreview((prev) =>
            prev.map((row) => {
              const match = detail.errors!.find(
                (e) => Number(e.row) === row.id,
              );
              return match
                ? {
                    ...row,
                    status: "error",
                    serverError: `${match.column ?? "?"}: ${match.error ?? "invalid"}`,
                  }
                : row;
            }),
          );
        }
      } else {
        setSubmitError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setFile(null);
    setPreview([]);
    setPreviewError(null);
    setBatch(null);
    setSubmitError(null);
    setServerErrors([]);
  }

  const rowCount = preview.length;
  const badRows = preview.filter((r) => r.status === "error").length;
  const canSubmit = !!file && rowCount > 0 && !submitting && !batch;

  return (
    <div>
      <PageHeader
        title="Actuals import"
        subtitle={
          "Drop the month-end CSV of actual hours and cost per resource line. " +
          "Any invalid row rejects the whole file (§2)."
        }
      />

      <SingleFileDropzone
        label="Drop the actuals CSV here (or click to choose)."
        accept={Array.from(CSV_TYPES).filter(Boolean)}
        onFile={stagePreview}
        disabled={submitting}
      />

      {previewError ? (
        <div role="alert" style={errorBox}>{previewError}</div>
      ) : null}

      {file && rowCount > 0 ? (
        <section
          aria-label="CSV preview"
          style={{ marginTop: 16 }}
        >
          <div style={previewHeader}>
            <strong>{file.name}</strong>
            <span style={{ color: "#6b7280" }}>
              {rowCount} row{rowCount === 1 ? "" : "s"}
              {badRows > 0
                ? ` — ${badRows} error${badRows === 1 ? "" : "s"}`
                : ""}
            </span>
          </div>
          <Table
            ariaLabel="Actuals CSV preview"
            rows={preview}
            columns={previewColumns}
          />
        </section>
      ) : file ? (
        <EmptyState
          title="Empty CSV"
          hint="No data rows detected. Check the header row and required columns."
        />
      ) : (
        <EmptyState
          title="No file yet"
          hint={`Drop a CSV with columns: ${REQUIRED_COLUMNS.join(", ")}.`}
        />
      )}

      {submitError ? (
        <div role="alert" style={errorBox}>{submitError}</div>
      ) : null}

      {batch ? (
        <div style={{ marginTop: 16 }}>
          <StatusChip
            tone={batch.status === "committed" ? "ok" : "warn"}
          >
            Batch {batch.status} — {batch.row_count} row
            {batch.row_count === 1 ? "" : "s"}
          </StatusChip>
        </div>
      ) : null}

      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <button
          type="button"
          aria-label="Import CSV"
          onClick={submit}
          disabled={!canSubmit}
          style={primaryBtn}
        >
          {submitting ? "Importing…" : "Import"}
        </button>
        <button
          type="button"
          aria-label="Reset"
          onClick={reset}
          disabled={submitting}
          style={secondaryBtn}
        >
          Reset
        </button>
      </div>

      {serverErrors.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <strong style={{ color: "#991b1b" }}>
            {serverErrors.length} validation error
            {serverErrors.length === 1 ? "" : "s"}
          </strong>
        </div>
      ) : null}
    </div>
  );
}

// --- CSV parsing ---------------------------------------------------------

async function parseCsvFile(file: File): Promise<PreviewRow[]> {
  const text = await file.text();
  return parseCsvText(text);
}

/**
 * Client-side preview parser. Deliberately naive — the server does the
 * real validation. We only surface obvious shape problems (missing
 * required columns, blank required cells) so Finance can eyeball the
 * grid before clicking Import.
 */
export function parseCsvText(text: string): PreviewRow[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").filter((l) => l.length > 0);
  if (lines.length === 0) return [];
  const header = splitCsvLine(lines[0]!).map((h) => h.trim().toLowerCase());
  const idx: Record<string, number> = {};
  for (const col of REQUIRED_COLUMNS) {
    const at = header.indexOf(col);
    if (at < 0) {
      throw new Error(`Missing required column: ${col}`);
    }
    idx[col] = at;
  }
  const out: PreviewRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]!);
    if (cells.every((c) => c.trim() === "")) continue;
    const row: PreviewRow = {
      id: i + 1, // header = 1 in the API's row numbering
      sow_ref: (cells[idx.sow_ref!] ?? "").trim(),
      resource_line_id: (cells[idx.resource_line_id!] ?? "").trim(),
      period_month: (cells[idx.period_month!] ?? "").trim(),
      actual_hours: (cells[idx.actual_hours!] ?? "").trim(),
      actual_cost: (cells[idx.actual_cost!] ?? "").trim(),
      actual_revenue: (cells[idx.actual_revenue!] ?? "").trim(),
      status: "ok",
      message: "queued",
    };
    // Cheap client hints — the server is authoritative on validation.
    if (!row.actual_cost) {
      row.status = "error";
      row.message = "actual_cost missing";
    } else if (!row.resource_line_id) {
      row.status = "error";
      row.message = "resource_line_id missing";
    } else if (!row.period_month) {
      row.status = "warn";
      row.message = "period_month missing";
    }
    out.push(row);
  }
  return out;
}

/** Minimal CSV cell splitter — supports double-quoted cells with commas. */
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (inQuote) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuote = false;
        }
      } else {
        cur += ch;
      }
    } else {
      if (ch === ",") {
        out.push(cur);
        cur = "";
      } else if (ch === '"') {
        inQuote = true;
      } else {
        cur += ch;
      }
    }
  }
  out.push(cur);
  return out;
}

// --- primitives ----------------------------------------------------------

function SingleFileDropzone({
  label,
  accept,
  onFile,
  disabled,
}: {
  label: string;
  accept: string[];
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const [hover, setHover] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(file: File | null | undefined) {
    if (!file) return;
    onFile(file);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setHover(false);
    if (disabled) return;
    pick(e.dataTransfer.files[0]);
  }

  function onChange(e: ChangeEvent<HTMLInputElement>) {
    pick(e.target.files?.[0]);
    e.target.value = "";
  }

  return (
    <div>
      <div
        role="button"
        aria-label={label}
        aria-disabled={disabled}
        tabIndex={0}
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setHover(true);
        }}
        onDragLeave={() => setHover(false)}
        style={{
          border: `2px dashed ${hover ? "#111827" : "#d1d5db"}`,
          borderRadius: 8,
          padding: 24,
          textAlign: "center",
          background: hover ? "#f3f4f6" : "#fafafa",
          color: "#374151",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.6 : 1,
        }}
      >
        {label}
      </div>
      <input
        ref={inputRef}
        type="file"
        aria-label="Actuals CSV"
        accept={accept.length > 0 ? accept.join(",") : ".csv"}
        onChange={onChange}
        style={{ display: "none" }}
      />
    </div>
  );
}

// --- styles --------------------------------------------------------------

const primaryBtn: React.CSSProperties = {
  background: "#111827",
  color: "white",
  border: "1px solid #111827",
  padding: "8px 12px",
  borderRadius: 6,
  cursor: "pointer",
};

const secondaryBtn: React.CSSProperties = {
  background: "white",
  color: "#111827",
  border: "1px solid #e5e7eb",
  padding: "8px 12px",
  borderRadius: 6,
  cursor: "pointer",
};

const errorBox: React.CSSProperties = {
  background: "#fef2f2",
  color: "#991b1b",
  border: "1px solid #fecaca",
  padding: 8,
  borderRadius: 4,
  fontSize: 13,
  marginTop: 8,
};

const previewHeader: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: 8,
};
