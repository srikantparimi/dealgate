/**
 * SOWConfirm — two-column PDF viewer + field confirmation panel (s3-e5).
 *
 * Layout:
 *   ┌────────────┬────────────────────────────────┐
 *   │  <embed>   │ Field list (14 fields).        │
 *   │  PDF       │  Each row: label · value · chip│
 *   │            │  · [Confirm] [Override] [Dispute]
 *   │            │  · page-ref link (scrolls PDF).│
 *   └────────────┴────────────────────────────────┘
 *
 * A full PDF plugin (react-pdf etc.) is out of scope; `<embed>` on the
 * S3 download URL is what the story asks for and hands scrolling to the
 * browser's native PDF viewer via `#page=N` fragments.
 *
 * "Submit for GM build" is disabled until every field carries
 * `status === "confirmed"`. Manual-required mode (Bedrock unavailable)
 * seeds every field with a null value + disputed chip; the same UI
 * handles both paths — the user just has to type each value in.
 */

import { useCallback, useMemo, useState } from "react";
import type { SowFieldName, SowVersion } from "../api/client";
import {
  ApiError,
  SOW_FIELDS,
  confirmSowField,
  submitSowVersion,
} from "../api/client";
import { StatusChip } from "../ui/StatusChip";

const FIELD_LABELS: Record<SowFieldName, string> = {
  scope_summary: "Scope summary",
  price: "Price",
  currency: "Currency",
  billing_basis: "Billing basis",
  term_start: "Term start",
  term_end: "Term end",
  notice_date: "Notice date",
  deliverables: "Deliverables",
  milestones: "Milestones",
  acceptance_criteria: "Acceptance criteria",
  assumptions: "Assumptions",
  exclusions: "Exclusions",
  signatories: "Signatories",
  engagement_type_suggested: "Engagement type (suggested)",
};

function chipTone(
  status: string,
): "ok" | "warn" | "block" | "neutral" {
  if (status === "confirmed") return "ok";
  if (status === "disputed") return "block";
  if (status === "unconfirmed") return "warn";
  return "neutral";
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export interface SOWConfirmProps {
  version: SowVersion;
  onVersionChanged: (version: SowVersion) => void;
  /** When false, the panel renders in read-only mode (governance viewer). */
  canEdit: boolean;
}

interface FieldRowProps {
  name: SowFieldName;
  entry: { value: unknown; page_ref: number; status: string } | undefined;
  canEdit: boolean;
  onScrollTo: (page: number) => void;
  onConfirm: (name: SowFieldName, value: unknown) => Promise<void>;
  onDispute: (name: SowFieldName) => void;
  disputed: boolean;
  savingField: SowFieldName | null;
}

function FieldRow({
  name,
  entry,
  canEdit,
  onScrollTo,
  onConfirm,
  onDispute,
  disputed,
  savingField,
}: FieldRowProps) {
  const initialValue = stringify(entry?.value);
  const [draft, setDraft] = useState<string>(initialValue);
  const [dirty, setDirty] = useState<boolean>(false);
  const busy = savingField === name;
  const status = disputed ? "disputed" : entry?.status ?? "unconfirmed";

  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: 12,
        marginBottom: 8,
        background: "white",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 6,
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>
          {FIELD_LABELS[name]}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <StatusChip tone={chipTone(status)}>{status}</StatusChip>
          {entry ? (
            <button
              type="button"
              onClick={() => onScrollTo(entry.page_ref)}
              style={{
                background: "none",
                border: "none",
                color: "#2563eb",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
              }}
              aria-label={`Go to page ${entry.page_ref} for ${FIELD_LABELS[name]}`}
            >
              p.{entry.page_ref}
            </button>
          ) : null}
        </div>
      </div>
      <textarea
        aria-label={`${FIELD_LABELS[name]} value`}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setDirty(true);
        }}
        readOnly={!canEdit}
        rows={
          draft.length > 60 || draft.includes("\n") ? 3 : 1
        }
        style={{
          width: "100%",
          padding: 6,
          fontSize: 13,
          fontFamily: "inherit",
          border: "1px solid #e5e7eb",
          borderRadius: 4,
          background: canEdit ? "white" : "#f9fafb",
        }}
      />
      {canEdit ? (
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 8,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={() => onDispute(name)}
            disabled={busy}
            aria-label={`Dispute ${FIELD_LABELS[name]}`}
            style={{
              background: "white",
              color: "#991b1b",
              border: "1px solid #fecaca",
              padding: "4px 10px",
              borderRadius: 4,
              fontSize: 12,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            Dispute
          </button>
          <button
            type="button"
            onClick={async () => {
              await onConfirm(name, draft);
              setDirty(false);
            }}
            disabled={busy || (!dirty && entry?.status === "confirmed")}
            aria-label={`${dirty ? "Override" : "Confirm"} ${FIELD_LABELS[name]}`}
            style={{
              background: dirty ? "#1d4ed8" : "#111827",
              color: "white",
              border: "none",
              padding: "4px 10px",
              borderRadius: 4,
              fontSize: 12,
              cursor: busy ? "wait" : "pointer",
              opacity: busy ? 0.6 : 1,
            }}
          >
            {busy ? "Saving…" : dirty ? "Override" : "Confirm"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function SOWConfirm({ version, onVersionChanged, canEdit }: SOWConfirmProps) {
  const [error, setError] = useState<string | null>(null);
  const [savingField, setSavingField] = useState<SowFieldName | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Local override to flag a field as disputed without hitting the API —
  // the API model only tracks confirmed/unconfirmed/disputed at write time.
  const [localDisputes, setLocalDisputes] = useState<Set<SowFieldName>>(
    () => new Set(),
  );
  const [pdfSrc, setPdfSrc] = useState<string>(version.download_url ?? "");

  const scrollTo = useCallback(
    (page: number) => {
      if (!version.download_url) return;
      // Reset then set to force `<embed>` to re-navigate even on same page.
      setPdfSrc("");
      requestAnimationFrame(() => {
        setPdfSrc(`${version.download_url}#page=${page}`);
      });
    },
    [version.download_url],
  );

  const onConfirm = useCallback(
    async (name: SowFieldName, value: unknown) => {
      setSavingField(name);
      setError(null);
      try {
        const updated = await confirmSowField(version.id, name, value);
        // Clear any local dispute flag now that we've written a value.
        setLocalDisputes((prev) => {
          const next = new Set(prev);
          next.delete(name);
          return next;
        });
        onVersionChanged(updated);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      } finally {
        setSavingField(null);
      }
    },
    [version.id, onVersionChanged],
  );

  const onDispute = useCallback((name: SowFieldName) => {
    setLocalDisputes((prev) => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, []);

  const missing = useMemo(() => {
    return SOW_FIELDS.filter((name) => {
      if (localDisputes.has(name)) return true;
      const entry = version.extracted_fields?.[name];
      return !entry || entry.status !== "confirmed";
    });
  }, [version.extracted_fields, localDisputes]);

  const allConfirmed = missing.length === 0;

  const onSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await submitSowVersion(version.id);
      onVersionChanged(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }, [version.id, onVersionChanged]);

  const submittedAlready = version.confirmed_at !== null;

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "flex-start",
        }}
      >
        <div style={{ flex: "0 0 45%", minWidth: 320 }}>
          {version.download_url ? (
            <embed
              key={pdfSrc || version.download_url}
              src={pdfSrc || version.download_url}
              type="application/pdf"
              width="100%"
              height="640px"
              aria-label="SOW PDF preview"
            />
          ) : (
            <div
              role="status"
              style={{
                border: "1px dashed #e5e7eb",
                borderRadius: 6,
                padding: 24,
                textAlign: "center",
                color: "#6b7280",
              }}
            >
              PDF unavailable
            </div>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <div>
              <StatusChip tone={chipTone(version.extract_status === "complete" ? "confirmed" : "warn")}>
                {version.extract_status}
              </StatusChip>{" "}
              {submittedAlready ? (
                <StatusChip tone="ok">submitted</StatusChip>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canEdit || !allConfirmed || submitting || submittedAlready}
              aria-label="Submit for GM build"
              style={{
                background: allConfirmed && canEdit ? "#065f46" : "#9ca3af",
                color: "white",
                border: "none",
                padding: "8px 16px",
                borderRadius: 6,
                cursor:
                  !canEdit || !allConfirmed || submitting || submittedAlready
                    ? "not-allowed"
                    : "pointer",
                fontSize: 13,
              }}
            >
              {submitting ? "Submitting…" : "Submit for GM build"}
            </button>
          </div>
          {version.extract_status === "manual_required" ? (
            <div
              role="note"
              style={{
                background: "#fef3c7",
                color: "#92400e",
                border: "1px solid #fde68a",
                borderRadius: 4,
                padding: 8,
                marginBottom: 8,
                fontSize: 13,
              }}
            >
              Bedrock model access is not enabled — the extract did not run.
              Enter each field manually below before submitting.
            </div>
          ) : null}
          {!allConfirmed ? (
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
              {missing.length} field(s) still need confirmation.
            </div>
          ) : null}
          {error ? (
            <div
              role="alert"
              style={{
                background: "#fef2f2",
                color: "#991b1b",
                border: "1px solid #fecaca",
                borderRadius: 4,
                padding: 8,
                marginBottom: 8,
                fontSize: 13,
              }}
            >
              {error}
            </div>
          ) : null}
          {SOW_FIELDS.map((name) => (
            <FieldRow
              key={name}
              name={name}
              entry={version.extracted_fields?.[name]}
              canEdit={canEdit && !submittedAlready}
              onScrollTo={scrollTo}
              onConfirm={onConfirm}
              onDispute={onDispute}
              disputed={localDisputes.has(name)}
              savingField={savingField}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
