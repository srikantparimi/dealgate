/**
 * Legacy import reconciliation (S6, Finance/CEO/SystemAdmin).
 *
 * Shows matched SOWs, unmatched SOWs, orphaned resource lines and the
 * per-project GM computed by the API. Finance approves the batch to
 * freeze it — the confirmation modal reminds the caller that legacy
 * SOWs stay "approval not evidenced" (blueprint §13 rollout).
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  ApiError,
  approveLegacyBatch,
  getLegacyReconciliation,
  type LegacyReconciliationResponse,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { Modal } from "../ui/Modal";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

const FINANCE_APPROVAL_ROLES = new Set(["Finance", "CEO", "SystemAdmin"]);

type MatchedRow = LegacyReconciliationResponse["matched"][number] & { id: string };
type UnmatchedRow = LegacyReconciliationResponse["unmatched_sows"][number] & {
  id: string;
};
type OrphanRow =
  LegacyReconciliationResponse["orphaned_resource_lines"][number] & { id: string };
type GmRow = LegacyReconciliationResponse["project_gm"][number] & { id: string };

export function LegacyReconciliationPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canApprove = (user?.groups ?? []).some((g) =>
    FINANCE_APPROVAL_ROLES.has(g),
  );

  const [report, setReport] = useState<LegacyReconciliationResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!batchId) return;
    setLoading(true);
    setError(null);
    getLegacyReconciliation(batchId)
      .then(setReport)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [batchId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const h = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(h);
  }, [toast]);

  if (!batchId) return <ErrorState error="Missing batch id" />;
  if (error) return <ErrorState error={error} retry={load} />;
  if (!report) {
    return loading ? (
      <EmptyState title="Loading" hint="Fetching the reconciliation report." />
    ) : (
      <EmptyState title="No data" />
    );
  }

  const matched: MatchedRow[] = report.matched.map((r) => ({
    ...r,
    id: r.sow_id,
  }));
  const unmatched: UnmatchedRow[] = report.unmatched_sows.map((r) => ({
    ...r,
    id: r.sow_id,
  }));
  const orphans: OrphanRow[] = report.orphaned_resource_lines.map((r) => ({
    ...r,
    id: r.gm_model_id,
  }));
  const gmRows: GmRow[] = report.project_gm.map((r, i) => ({
    ...r,
    id: `${r.sow_ref}-${i}`,
  }));

  const matchedColumns: Column<MatchedRow>[] = [
    { key: "sow_ref", header: "SOW ref", render: (r) => r.sow_ref },
    {
      key: "file",
      header: "File",
      render: (r) => (
        <span style={{ color: "#6b7280", fontSize: 12 }}>{r.filename ?? "—"}</span>
      ),
    },
    { key: "lines", header: "Lines", render: (r) => r.line_count },
    {
      key: "gm_us",
      header: "GM (US)",
      render: (r) => formatGm(r.gm_us),
    },
    {
      key: "gm_india",
      header: "GM (India)",
      render: (r) => formatGm(r.gm_india),
    },
    {
      key: "floor",
      header: "Floor",
      render: (r) =>
        r.below_floor ? (
          <StatusChip tone="block">
            Below floor{r.failing.length ? `: ${r.failing.join(", ")}` : ""}
          </StatusChip>
        ) : (
          <StatusChip tone="ok">Pass</StatusChip>
        ),
    },
  ];

  const unmatchedColumns: Column<UnmatchedRow>[] = [
    { key: "sow_ref", header: "SOW ref", render: (r) => r.sow_ref || "—" },
    { key: "file", header: "File", render: (r) => r.filename ?? "—" },
    {
      key: "status",
      header: "Status",
      render: () => <StatusChip tone="warn">No matching rows</StatusChip>,
    },
  ];

  const orphanColumns: Column<OrphanRow>[] = [
    {
      key: "gm_model_id",
      header: "GM model",
      render: (r) => (
        <code style={{ fontSize: 12 }}>{r.gm_model_id.slice(0, 8)}…</code>
      ),
    },
    { key: "engagement_type", header: "Engagement", render: (r) => r.engagement_type },
    { key: "lines", header: "Lines", render: (r) => r.line_count },
  ];

  const gmColumns: Column<GmRow>[] = [
    { key: "sow_ref", header: "SOW ref", render: (r) => r.sow_ref },
    {
      key: "revenue_us",
      header: "Revenue (US)",
      render: (r) => formatMoney(r.revenue_us),
    },
    {
      key: "cost_us",
      header: "Cost (US)",
      render: (r) => formatMoney(r.cost_us),
    },
    { key: "gm_us", header: "GM (US)", render: (r) => formatGm(r.gm_us) },
    {
      key: "revenue_india",
      header: "Revenue (India)",
      render: (r) => formatMoney(r.revenue_india),
    },
    {
      key: "cost_india",
      header: "Cost (India)",
      render: (r) => formatMoney(r.cost_india),
    },
    { key: "gm_india", header: "GM (India)", render: (r) => formatGm(r.gm_india) },
    {
      key: "flag",
      header: "Floor",
      render: (r) =>
        r.below_floor ? (
          <StatusChip tone="block">Below floor</StatusChip>
        ) : (
          <StatusChip tone="ok">OK</StatusChip>
        ),
    },
  ];

  async function approve() {
    if (!batchId) return;
    setApproving(true);
    try {
      const res = await approveLegacyBatch(batchId);
      setReport(res);
      setConfirmOpen(false);
      setToast("Batch approved — tasks filed for unmatched SOWs.");
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : String(err));
    } finally {
      setApproving(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Legacy reconciliation"
        subtitle={
          <span>
            Batch <code>{batchId.slice(0, 8)}…</code> — status{" "}
            <StatusChip tone={report.status === "approved" ? "ok" : "warn"}>
              {report.status}
            </StatusChip>
          </span>
        }
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={() => navigate("/legacy/import")}
              style={secondaryBtn}
            >
              Back to import
            </button>
            {canApprove && report.status !== "approved" ? (
              <button
                type="button"
                aria-label="Approve reconciliation"
                onClick={() => setConfirmOpen(true)}
                style={primaryBtn}
              >
                Approve reconciliation
              </button>
            ) : null}
          </div>
        }
      />

      <Section title="Per-project GM">
        {gmRows.length === 0 ? (
          <EmptyState title="No imported resources yet" />
        ) : (
          <Table ariaLabel="Per-project GM" rows={gmRows} columns={gmColumns} />
        )}
      </Section>

      <Section title={`Matched (${matched.length})`}>
        {matched.length === 0 ? (
          <EmptyState title="No matches" hint="Excel rows haven't lined up with any uploaded SOW." />
        ) : (
          <Table ariaLabel="Matched SOWs" rows={matched} columns={matchedColumns} />
        )}
      </Section>

      <Section title={`Unmatched SOWs (${unmatched.length})`}>
        {unmatched.length === 0 ? (
          <EmptyState title="Every SOW has resource lines" />
        ) : (
          <Table
            ariaLabel="Unmatched SOWs"
            rows={unmatched}
            columns={unmatchedColumns}
          />
        )}
      </Section>

      <Section title={`Orphaned resource lines (${orphans.length})`}>
        {orphans.length === 0 ? (
          <EmptyState title="No orphaned lines" />
        ) : (
          <Table ariaLabel="Orphaned lines" rows={orphans} columns={orphanColumns} />
        )}
      </Section>

      <Modal
        open={confirmOpen}
        title="Approve legacy import batch?"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <button type="button" onClick={() => setConfirmOpen(false)} style={secondaryBtn}>
              Cancel
            </button>
            <button
              type="button"
              onClick={approve}
              disabled={approving}
              style={primaryBtn}
            >
              {approving ? "Approving…" : "Yes, approve"}
            </button>
          </>
        }
      >
        <p style={{ margin: 0, fontSize: 14, color: "#111827" }}>
          Approving this batch freezes the import. Blueprint §13 rollout: every
          uploaded SOW stays tagged <strong>legacy — approval not evidenced</strong>.
          Approving here <em>does not</em> create approval records for these
          projects.
        </p>
        {report.unmatched_sows.length > 0 ? (
          <p style={{ marginTop: 12, fontSize: 13, color: "#7f1d1d" }}>
            Tasks will be filed against the account owner for{" "}
            <strong>{report.unmatched_sows.length}</strong> unmatched SOW
            {report.unmatched_sows.length === 1 ? "" : "s"}.
          </p>
        ) : null}
      </Modal>

      {toast ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            background: "#111827",
            color: "white",
            padding: "8px 12px",
            borderRadius: 6,
            fontSize: 14,
          }}
        >
          {toast}
        </div>
      ) : null}
    </div>
  );
}

// --- helpers -------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section style={{ marginTop: 24 }}>
      <h2 style={{ margin: "0 0 8px", fontSize: 16, color: "#111827" }}>{title}</h2>
      {children}
    </section>
  );
}

function formatMoney(v: string | null): string {
  if (v === null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatGm(v: string | null): string {
  if (v === null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${(n * 100).toFixed(2)}%`;
}

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
