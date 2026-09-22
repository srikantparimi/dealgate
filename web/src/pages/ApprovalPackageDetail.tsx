/**
 * ApprovalPackageDetail — the frozen snapshot for one approval package.
 *
 * The page never computes numbers; every value comes from the API. It
 * renders the pinned SOW + GM model summary, the current state and
 * released/voided stamps, and one row per recorded approval. The floor
 * pass/fail chips come from the ``floors`` block on the detail response.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getApprovalPackage,
  type ApprovalPackage,
  type ApprovalPackageStatus,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { FinanceGmPanel } from "./v2/sow-workspace/staffing/FinanceGmPanel";
import { DirectCostsEditor } from "./v2/sow-workspace/staffing/DirectCostsEditor";

const STATUS_TONE: Record<ApprovalPackageStatus, "ok" | "warn" | "block" | "neutral"> = {
  pending_delivery_hr: "warn",
  pending_finance_legal: "warn",
  pending_ceo_exception: "block",
  ready_to_sign: "ok",
  released: "ok",
  voided: "neutral",
  rejected: "block",
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
      }}
    >
      <h2 style={{ marginTop: 0, marginBottom: 12, fontSize: 16, color: "#111827" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8, display: "flex", gap: 12 }}>
      <div style={{ minWidth: 160, fontSize: 12, color: "#6b7280" }}>{label}</div>
      <div style={{ flex: 1, fontSize: 14, color: "#111827" }}>{children}</div>
    </div>
  );
}

export function ApprovalPackageDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [pkg, setPkg] = useState<ApprovalPackage | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const p = await getApprovalPackage(id);
      setPkg(p);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !pkg) return <ErrorState error={error} retry={load} />;
  if (!pkg) return <EmptyState title="Loading" hint="Fetching the package." />;

  const floors = pkg.floors ?? {
    us_pass: true,
    india_pass: true,
    requires_ceo: false,
    failing: [],
  };
  const approvalRows = pkg.approvals.map((a) => ({ ...a }));
  const cols: Column<typeof approvalRows[number]>[] = [
    { key: "function", header: "Function", render: (a) => a.function },
    { key: "decision", header: "Decision", render: (a) => a.decision },
    { key: "approver", header: "Approver", render: (a) => a.approver_id.slice(0, 8) + "…" },
    { key: "reason", header: "Reason", render: (a) => a.reason ?? "—" },
    { key: "at", header: "When", render: (a) => a.decided_at ?? "—" },
  ];

  return (
    <div>
      <PageHeader
        title={`Package ${pkg.id.slice(0, 8)}…`}
        subtitle={
          <span>
            <StatusChip tone={STATUS_TONE[pkg.status]}>{pkg.status}</StatusChip>{" "}
            <StatusChip tone={floors.requires_ceo ? "block" : "ok"}>
              {floors.requires_ceo ? "Below floor" : "Floors pass"}
            </StatusChip>
          </span>
        }
      />

      <Panel title="Frozen snapshot">
        <Field label="Opportunity">
          <Link to={`/deals/${pkg.opportunity_id}`}>{pkg.opportunity_id}</Link>
        </Field>
        <Field label="SOW version">{pkg.sow_version_id}</Field>
        <Field label="GM model">{pkg.gm_model_id}</Field>
        <Field label="Package hash">
          <code style={{ fontSize: 12 }}>{pkg.package_hash}</code>
        </Field>
        <Field label="Submitted">
          {pkg.submitted_at ?? "—"} by {pkg.submitted_by.slice(0, 8)}…
        </Field>
        {pkg.released_at ? <Field label="Released">{pkg.released_at}</Field> : null}
        {pkg.voided_at ? (
          <Field label="Voided">
            {pkg.voided_at} — {pkg.voided_reason ?? ""}
          </Field>
        ) : null}
      </Panel>

      <div className="mb-6 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        {pkg.cost_lines !== undefined ? <DirectCostsEditor rows={pkg.cost_lines} /> : <div />}
        <FinanceGmPanel result={floors} state="review snapshot" />
      </div>

      <Panel title="Decisions">
        {approvalRows.length === 0 ? (
          <EmptyState title="No decisions yet" />
        ) : (
          <Table ariaLabel="Approvals" columns={cols} rows={approvalRows} />
        )}
      </Panel>
    </div>
  );
}
