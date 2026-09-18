/**
 * AgreementsPanel — the Legal NDA/MSA view rendered inside `ClientDetail`.
 *
 * Agent J's `ClientDetail` page owns the slot; this file exports the
 * component so J can drop it in via `<AgreementsPanel legalEntityId={...} />`.
 * Kept self-contained so nothing in the client page needs to know about
 * agreement shape.
 *
 * Flows:
 *  - Table lists agreements for the given legal entity.
 *  - "Add agreement" opens a Modal → POST /agreements.
 *  - Row click opens a Drawer:
 *      * edit state / dates / next action → PATCH /agreements/{id}
 *      * upload evidence: POST /evidence-upload-url → PUT to S3 → PATCH
 *        the agreement row with the returned s3_key.
 *
 * No business math here — the panel formats dates and renders the
 * server-owned state via `StatusChip`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  AgreementKind,
  AgreementRow,
  AgreementState,
  CreateAgreementBody,
  PatchAgreementBody,
  UUID,
} from "../api/client";
import {
  ApiError,
  createAgreement,
  getDownloadUrl,
  getUploadUrl,
  listAgreements,
  patchAgreement,
} from "../api/client";
import { Drawer } from "../ui/Drawer";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { FileDropzone } from "../ui/FileDropzone";
import { Modal } from "../ui/Modal";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

const ALL_STATES: AgreementState[] = [
  "missing",
  "requested",
  "drafting",
  "under_review",
  "sent",
  "partially_signed",
  "executed",
  "expired",
  "terminated",
  "superseded",
];

const KIND_OPTIONS: AgreementKind[] = ["NDA", "MSA"];

const CONTENT_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

function stateTone(state: AgreementState): "ok" | "warn" | "block" | "neutral" {
  if (state === "executed") return "ok";
  if (state === "drafting" || state === "sent" || state === "under_review" || state === "partially_signed") {
    return "warn";
  }
  if (state === "expired" || state === "missing" || state === "terminated") {
    return "block";
  }
  return "neutral";
}

function fmt(date: string | null): string {
  return date ?? "—";
}

// --- Add-agreement modal ---------------------------------------------------

function AddAgreementModal({
  open,
  onClose,
  legalEntityId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  legalEntityId: UUID;
  onCreated: (row: AgreementRow) => void;
}) {
  const [kind, setKind] = useState<AgreementKind>("NDA");
  const [state, setState] = useState<AgreementState>("drafting");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setKind("NDA");
    setState("drafting");
    setOwnerEmail("");
    setNextAction("");
    setDueDate("");
    setError(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const body: CreateAgreementBody = {
        legal_entity_id: legalEntityId,
        type: kind,
        state,
        owner_email: ownerEmail.trim() || null,
        next_action: nextAction.trim() || null,
        due_date: dueDate || null,
      };
      const created = await createAgreement(body);
      onCreated(created);
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create agreement");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Add agreement"
      onClose={handleClose}
      footer={
        <>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            style={{
              background: "white",
              color: "#374151",
              border: "1px solid #e5e7eb",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
              opacity: submitting ? 0.6 : 1,
            }}
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Type</span>
          <select
            aria-label="Type"
            value={kind}
            onChange={(e) => setKind(e.target.value as AgreementKind)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          >
            {KIND_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>State</span>
          <select
            aria-label="State"
            value={state}
            onChange={(e) => setState(e.target.value as AgreementState)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          >
            {ALL_STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Owner email</span>
          <input
            aria-label="Owner email"
            type="email"
            value={ownerEmail}
            onChange={(e) => setOwnerEmail(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Next action</span>
          <input
            aria-label="Next action"
            type="text"
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Due date</span>
          <input
            aria-label="Due date"
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        {error ? (
          <div
            role="alert"
            style={{
              background: "#fef2f2",
              color: "#991b1b",
              border: "1px solid #fecaca",
              padding: 8,
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {error}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

// --- Edit drawer -----------------------------------------------------------

function EditAgreementDrawer({
  open,
  onClose,
  agreement,
  onUpdated,
}: {
  open: boolean;
  onClose: () => void;
  agreement: AgreementRow | null;
  onUpdated: (row: AgreementRow) => void;
}) {
  const [state, setState] = useState<AgreementState>("drafting");
  const [nextAction, setNextAction] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [expiry, setExpiry] = useState("");
  const [noticeDays, setNoticeDays] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!agreement) return;
    setState(agreement.state);
    setNextAction(agreement.next_action ?? "");
    setDueDate(agreement.due_date ?? "");
    setEffectiveFrom(agreement.effective_from ?? "");
    setExpiry(agreement.expiry ?? "");
    setNoticeDays(agreement.notice_days?.toString() ?? "");
    setError(null);
    setUploadStatus(null);
  }, [agreement]);

  async function save() {
    if (!agreement) return;
    setSaving(true);
    setError(null);
    try {
      const patch: PatchAgreementBody = {};
      if (state !== agreement.state) patch.state = state;
      if ((nextAction || null) !== agreement.next_action)
        patch.next_action = nextAction || null;
      if ((dueDate || null) !== agreement.due_date)
        patch.due_date = dueDate || null;
      if ((effectiveFrom || null) !== agreement.effective_from)
        patch.effective_from = effectiveFrom || null;
      if ((expiry || null) !== agreement.expiry) patch.expiry = expiry || null;
      const parsedNotice = noticeDays === "" ? null : Number(noticeDays);
      if (parsedNotice !== agreement.notice_days) patch.notice_days = parsedNotice;

      if (Object.keys(patch).length === 0) {
        onClose();
        return;
      }
      const updated = await patchAgreement(agreement.id, patch);
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const onEvidenceFile = useCallback(
    async (file: File) => {
      if (!agreement) return;
      setUploading(true);
      setUploadStatus(null);
      setError(null);
      try {
        const ct =
          file.type === CONTENT_TYPES.pdf || file.type === CONTENT_TYPES.docx
            ? file.type
            : file.name.toLowerCase().endsWith(".pdf")
              ? CONTENT_TYPES.pdf
              : CONTENT_TYPES.docx;
        const signed = await getUploadUrl(agreement.id, {
          filename: file.name,
          content_type: ct,
        });
        // Direct browser PUT — bytes never touch the API.
        const putRes = await fetch(signed.url, {
          method: "PUT",
          headers: signed.required_headers ?? undefined,
          body: file,
        });
        if (!putRes.ok) {
          throw new Error(`Upload failed (${putRes.status})`);
        }
        // Confirm the upload by patching the row with the returned key.
        const updated = await patchAgreement(agreement.id, {
          evidence_s3_key: signed.s3_key,
        });
        onUpdated(updated);
        setUploadStatus("Uploaded.");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      } finally {
        setUploading(false);
      }
    },
    [agreement, onUpdated],
  );

  async function downloadEvidence() {
    if (!agreement) return;
    try {
      const { url } = await getDownloadUrl(agreement.id);
      window.open(url, "_blank");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to fetch download URL");
    }
  }

  if (!agreement) return null;

  return (
    <Drawer
      open={open}
      title={`Edit ${agreement.kind}`}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{
              background: "white",
              color: "#374151",
              border: "1px solid #e5e7eb",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            Close
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>State</span>
          <select
            aria-label="State"
            value={state}
            onChange={(e) => setState(e.target.value as AgreementState)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          >
            {ALL_STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Next action</span>
          <input
            aria-label="Next action"
            type="text"
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Due date</span>
          <input
            aria-label="Due date"
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Effective from</span>
          <input
            aria-label="Effective from"
            type="date"
            value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Expiry</span>
          <input
            aria-label="Expiry"
            type="date"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Notice days</span>
          <input
            aria-label="Notice days"
            type="number"
            min={0}
            value={noticeDays}
            onChange={(e) => setNoticeDays(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Evidence</div>
          <FileDropzone
            accept={[CONTENT_TYPES.pdf, CONTENT_TYPES.docx]}
            disabled={uploading}
            onFile={onEvidenceFile}
            label={uploading ? "Uploading…" : "Drop PDF or DOCX, or click"}
          />
          {agreement.evidence_s3_key ? (
            <div style={{ marginTop: 8, fontSize: 13 }}>
              <button
                type="button"
                onClick={downloadEvidence}
                style={{
                  background: "none",
                  border: "none",
                  color: "#2563eb",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 13,
                }}
              >
                Download current evidence
              </button>
            </div>
          ) : null}
          {uploadStatus ? (
            <div style={{ marginTop: 8, fontSize: 13, color: "#065f46" }}>
              {uploadStatus}
            </div>
          ) : null}
        </div>
        {error ? (
          <div
            role="alert"
            style={{
              background: "#fef2f2",
              color: "#991b1b",
              border: "1px solid #fecaca",
              padding: 8,
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {error}
          </div>
        ) : null}
      </div>
    </Drawer>
  );
}

// --- Panel entry point -----------------------------------------------------

export interface AgreementsPanelProps {
  legalEntityId: UUID;
  /** When true, hide the "Add agreement" button (read-only viewer). */
  readOnly?: boolean;
}

export function AgreementsPanel({ legalEntityId, readOnly }: AgreementsPanelProps) {
  const [rows, setRows] = useState<AgreementRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<AgreementRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listAgreements({ legal_entity_id: legalEntityId });
      setRows(res.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [legalEntityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo<Column<AgreementRow>[]>(
    () => [
      { key: "kind", header: "Type", render: (r) => r.kind },
      {
        key: "state",
        header: "State",
        render: (r) => <StatusChip tone={stateTone(r.state)}>{r.state}</StatusChip>,
      },
      {
        key: "effective",
        header: "Effective",
        render: (r) => fmt(r.effective_from ?? null),
      },
      { key: "expiry", header: "Expiry", render: (r) => fmt(r.expiry) },
      { key: "next_action", header: "Next action", render: (r) => r.next_action ?? "—" },
      { key: "owner", header: "Owner", render: (r) => r.owner_email ?? "—" },
    ],
    [],
  );

  function onCreated(row: AgreementRow) {
    setRows((prev) => [row, ...prev]);
  }

  function onUpdated(row: AgreementRow) {
    setRows((prev) => prev.map((r) => (r.id === row.id ? row : r)));
    setEditing(row);
  }

  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 16, color: "#111827" }}>Agreements</h2>
        {readOnly ? null : (
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "6px 12px",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            Add agreement
          </button>
        )}
      </header>
      {loading ? (
        <div style={{ color: "#6b7280", fontSize: 14 }}>Loading agreements…</div>
      ) : error ? (
        <ErrorState error={error} retry={load} />
      ) : rows.length === 0 ? (
        <EmptyState title="No agreements yet" hint="Add an NDA or MSA to get started." />
      ) : (
        <Table
          ariaLabel="Agreements"
          columns={columns}
          rows={rows}
          onRowClick={(row) => setEditing(row)}
        />
      )}
      <AddAgreementModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        legalEntityId={legalEntityId}
        onCreated={onCreated}
      />
      <EditAgreementDrawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        agreement={editing}
        onUpdated={onUpdated}
      />
    </section>
  );
}
