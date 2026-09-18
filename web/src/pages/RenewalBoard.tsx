/**
 * RenewalBoard — column-view of renewal rows the scheduler + owner drive
 * (Sprint 5, story s5-renewals-scheduler).
 *
 * Read is any governance role; write is the account owner of the deal
 * (or SystemAdmin). Both gates live on the API — this page renders what
 * the server hands back and posts PATCHes on the edit drawer.
 *
 * No business math in the browser (blueprint §2). ``days_until_end``
 * comes from the API.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getRenewal,
  listRenewals,
  patchRenewal,
  type RenewalRow,
  type RenewalStatus,
} from "../api/client";
import { Drawer } from "../ui/Drawer";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";

const AT_RISK_DAYS = 30;

interface Column {
  key: string;
  label: string;
  tone: "ok" | "warn" | "block" | "neutral";
  match: (row: RenewalRow) => boolean;
}

const COLUMNS: Column[] = [
  {
    key: "open",
    label: "Open",
    tone: "warn",
    match: (r) => r.status === "open" && r.days_until_end > AT_RISK_DAYS,
  },
  {
    key: "at_risk",
    label: "At risk",
    tone: "block",
    match: (r) => r.status === "open" && r.days_until_end <= AT_RISK_DAYS,
  },
  {
    key: "closed",
    label: "Closed",
    tone: "ok",
    match: (r) => r.status === "closed" || r.status === "extended",
  },
  {
    key: "churn",
    label: "Churn",
    tone: "neutral",
    match: (r) => r.status === "churn",
  },
];

const STATUS_TONE: Record<RenewalStatus, "ok" | "warn" | "block" | "neutral"> = {
  open: "warn",
  closed: "ok",
  extended: "ok",
  churn: "block",
};

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  return ts.slice(0, 19).replace("T", " ") + "Z";
}

export function RenewalBoardPage() {
  const [items, setItems] = useState<RenewalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<RenewalRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch each status so churn/closed rows still render (server filters).
      const statuses: RenewalStatus[] = ["open", "closed", "extended", "churn"];
      const responses = await Promise.all(
        statuses.map((s) => listRenewals({ status: s, size: 200 })),
      );
      const merged: RenewalRow[] = [];
      responses.forEach((r) => merged.push(...r.items));
      setItems(merged);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(() => {
    const bucket: Record<string, RenewalRow[]> = {};
    COLUMNS.forEach((c) => (bucket[c.key] = []));
    for (const row of items) {
      const col = COLUMNS.find((c) => c.match(row));
      if (col) bucket[col.key].push(row);
    }
    return bucket;
  }, [items]);

  const openDrawer = useCallback(async (row: RenewalRow) => {
    setSaveError(null);
    setSelected(row);
    try {
      // Re-fetch for the latest server-truth (someone else may have PATCHed).
      const fresh = await getRenewal(row.id);
      setSelected(fresh);
    } catch (e) {
      // Non-fatal — the stale row is still editable; save is authoritative.
      setSaveError(e);
    }
  }, []);

  const closeDrawer = useCallback(() => {
    setSelected(null);
    setSaveError(null);
  }, []);

  const submitEdit = useCallback(
    async (payload: {
      outcome_summary: string | null;
      status?: "closed" | "extended";
      replacement_sow_version_id?: string | null;
    }) => {
      if (!selected) return;
      setSaving(true);
      setSaveError(null);
      try {
        await patchRenewal(selected.id, payload);
        await load();
        setSelected(null);
      } catch (e) {
        setSaveError(e);
      } finally {
        setSaving(false);
      }
    },
    [selected, load],
  );

  return (
    <div>
      <PageHeader
        title="Renewals"
        subtitle="Track renewal, churn and at-risk SOWs across the book."
      />
      {error ? <ErrorState error={error} retry={load} /> : null}
      {loading ? (
        <div style={{ color: "#6b7280" }}>Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No renewals yet"
          hint="The scheduler will open one at term_end – 60 days."
        />
      ) : (
        <div
          data-testid="renewal-columns"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: 16,
          }}
        >
          {COLUMNS.map((col) => (
            <section
              key={col.key}
              data-testid={`col-${col.key}`}
              aria-label={col.label}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 8,
                background: "#f9fafb",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <header
                style={{
                  padding: "8px 12px",
                  borderBottom: "1px solid #e5e7eb",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <StatusChip tone={col.tone}>{col.label}</StatusChip>
                <span
                  style={{ color: "#6b7280", fontSize: 12 }}
                  data-testid={`count-${col.key}`}
                >
                  {grouped[col.key].length}
                </span>
              </header>
              <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                {grouped[col.key].length === 0 ? (
                  <div style={{ color: "#9ca3af", fontSize: 13, padding: 8 }}>—</div>
                ) : (
                  grouped[col.key].map((row) => (
                    <button
                      type="button"
                      key={row.id}
                      onClick={() => openDrawer(row)}
                      data-testid={`row-${row.id}`}
                      style={{
                        textAlign: "left",
                        background: "white",
                        border: "1px solid #e5e7eb",
                        borderRadius: 6,
                        padding: 10,
                        cursor: "pointer",
                        display: "flex",
                        flexDirection: "column",
                        gap: 4,
                        fontSize: 13,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "#111827" }}>
                        {row.hubspot_deal_id ?? row.opportunity_id.slice(0, 8)}
                      </div>
                      <div style={{ color: "#374151" }}>
                        term ends <strong>{row.term_end}</strong>
                        <span style={{ marginLeft: 8, color: "#6b7280" }}>
                          ({row.days_until_end}d)
                        </span>
                      </div>
                      <div style={{ color: "#6b7280", fontSize: 12 }}>
                        trigger {row.trigger_date} · owner{" "}
                        {row.owner_id ? row.owner_id.slice(0, 8) : "—"}
                      </div>
                      <div style={{ color: "#9ca3af", fontSize: 12 }}>
                        last update {formatTs(row.updated_at)}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      )}

      <RenewalEditDrawer
        renewal={selected}
        onClose={closeDrawer}
        onSubmit={submitEdit}
        saving={saving}
        error={saveError}
      />
    </div>
  );
}

interface EditDrawerProps {
  renewal: RenewalRow | null;
  onClose: () => void;
  onSubmit: (payload: {
    outcome_summary: string | null;
    status?: "closed" | "extended";
    replacement_sow_version_id?: string | null;
  }) => Promise<void>;
  saving: boolean;
  error: unknown;
}

function RenewalEditDrawer({
  renewal,
  onClose,
  onSubmit,
  saving,
  error,
}: EditDrawerProps) {
  const [outcome, setOutcome] = useState("");
  const [status, setStatus] = useState<"" | "closed" | "extended">("");
  const [replacement, setReplacement] = useState("");

  useEffect(() => {
    setOutcome(renewal?.outcome_summary ?? "");
    setStatus("");
    setReplacement(renewal?.replacement_sow_version_id ?? "");
  }, [renewal]);

  const handleSave = async () => {
    if (!renewal) return;
    const payload: {
      outcome_summary: string | null;
      status?: "closed" | "extended";
      replacement_sow_version_id?: string | null;
    } = { outcome_summary: outcome || null };
    if (status !== "") payload.status = status;
    if (replacement) payload.replacement_sow_version_id = replacement;
    await onSubmit(payload);
  };

  const errorMessage =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : error
          ? String(error)
          : null;

  return (
    <Drawer
      open={Boolean(renewal)}
      onClose={onClose}
      title={`Edit renewal · ${renewal?.hubspot_deal_id ?? ""}`}
      ariaLabel="Edit renewal"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{
              background: "white",
              border: "1px solid #d1d5db",
              padding: "6px 12px",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            data-testid="save-renewal"
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "6px 12px",
              borderRadius: 6,
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      {renewal ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <dl style={{ margin: 0, fontSize: 13 }}>
            <dt style={{ fontWeight: 600, color: "#6b7280" }}>Term end</dt>
            <dd style={{ margin: 0, marginBottom: 8 }}>{renewal.term_end}</dd>
            <dt style={{ fontWeight: 600, color: "#6b7280" }}>Trigger date</dt>
            <dd style={{ margin: 0, marginBottom: 8 }}>{renewal.trigger_date}</dd>
            <dt style={{ fontWeight: 600, color: "#6b7280" }}>Days until end</dt>
            <dd style={{ margin: 0, marginBottom: 8 }}>{renewal.days_until_end}</dd>
            <dt style={{ fontWeight: 600, color: "#6b7280" }}>Current status</dt>
            <dd style={{ margin: 0, marginBottom: 8 }}>
              <StatusChip tone={STATUS_TONE[renewal.status]}>
                {renewal.status}
              </StatusChip>
            </dd>
          </dl>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
              Outcome summary
            </span>
            <textarea
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              data-testid="outcome-summary"
              rows={5}
              style={{
                border: "1px solid #d1d5db",
                borderRadius: 6,
                padding: 8,
                fontSize: 14,
              }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
              Move status to
            </span>
            <select
              value={status}
              onChange={(e) =>
                setStatus(e.target.value as "" | "closed" | "extended")
              }
              data-testid="status-select"
              style={{
                border: "1px solid #d1d5db",
                borderRadius: 6,
                padding: 8,
                fontSize: 14,
              }}
            >
              <option value="">Keep current</option>
              <option value="closed">Closed</option>
              <option value="extended">Extended (renewal signed)</option>
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
              Replacement SOW version id
            </span>
            <input
              value={replacement}
              onChange={(e) => setReplacement(e.target.value)}
              placeholder="UUID of the signed renewal SOW"
              data-testid="replacement-input"
              style={{
                border: "1px solid #d1d5db",
                borderRadius: 6,
                padding: 8,
                fontSize: 14,
              }}
            />
          </label>
          {errorMessage ? (
            <div
              role="alert"
              style={{ color: "#991b1b", fontSize: 13 }}
              data-testid="save-error"
            >
              {errorMessage}
            </div>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
