import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type { DealDetail, DealPatch } from "../api/client";
import { getDeal, patchDeal } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

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

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div>{children}</div>
    </div>
  );
}

function Toast({ message }: { message: string }) {
  return (
    <div
      role="status"
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        background: "#065f46",
        color: "white",
        padding: "8px 16px",
        borderRadius: 6,
        fontSize: 14,
      }}
    >
      {message}
    </div>
  );
}

export function DealDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [ownerId, setOwnerId] = useState<string>("");
  const [engagement, setEngagement] = useState<string>("");
  const [nextAction, setNextAction] = useState<string>("");

  const load = useCallback(() => {
    if (!id) return;
    setError(null);
    getDeal(id)
      .then((d) => {
        setDeal(d);
        setOwnerId(d.owner_id ?? "");
        setEngagement(d.engagement_type ?? "");
        setNextAction(d.next_client_action ?? "");
      })
      .catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!id || !deal) return;
    setSaving(true);
    try {
      const patch: DealPatch = {};
      const newOwner = ownerId.trim() === "" ? null : ownerId.trim();
      if (newOwner !== (deal.owner_id ?? null)) patch.owner_id = newOwner;
      const newEng = engagement.trim() === "" ? null : engagement.trim();
      if (newEng !== (deal.engagement_type ?? null)) patch.engagement_type = newEng;
      const newNext = nextAction.trim() === "" ? null : nextAction.trim();
      if (newNext !== (deal.next_client_action ?? null))
        patch.next_client_action = newNext;
      const updated = await patchDeal(id, patch);
      setDeal(updated);
      setToast("Saved");
      window.setTimeout(() => setToast(null), 1500);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  if (error && !deal) return <ErrorState error={error} retry={load} />;
  if (!deal) return <EmptyState title="Loading" hint="Fetching the deal." />;

  const taskCols: Column<DealDetail["tasks"][number]>[] = [
    { key: "subject", header: "Subject", render: (t) => t.subject },
    { key: "status", header: "Status", render: (t) => t.status },
    { key: "due", header: "Due", render: (t) => t.due_date ?? "—" },
  ];

  const auditCols: Column<DealDetail["audit"][number]>[] = [
    { key: "ts", header: "When", render: (a) => a.ts },
    { key: "action", header: "Action", render: (a) => a.action },
    {
      key: "after",
      header: "Change",
      render: (a) => (a.after ? JSON.stringify(a.after) : "—"),
    },
  ];

  return (
    <div>
      <PageHeader
        title={`Deal ${deal.hubspot_deal_id}`}
        subtitle={
          <span>
            <StatusChip tone="warn">{deal.governance_status}</StatusChip>{" "}
            <StatusChip tone="neutral">{deal.coverage_state}</StatusChip>
          </span>
        }
        right={
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
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        }
      />
      {error ? <ErrorState error={error} retry={load} /> : null}
      <Panel title="Intake">
        <Field label="Owner ID">
          <input
            aria-label="Owner ID"
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value)}
            style={{ width: "100%", padding: 6 }}
          />
        </Field>
        <Field label="Engagement type">
          <input
            aria-label="Engagement type"
            value={engagement}
            onChange={(e) => setEngagement(e.target.value)}
            style={{ width: "100%", padding: 6 }}
          />
        </Field>
        <Field label="Next client action">
          <input
            aria-label="Next client action"
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
            style={{ width: "100%", padding: 6 }}
          />
        </Field>
        <Field label="Next client date">{deal.next_client_date ?? "—"}</Field>
      </Panel>

      <Panel title="Coverage">
        <Field label="Coverage state">
          <StatusChip tone={deal.coverage_state === "Complete" ? "ok" : "warn"}>
            {deal.coverage_state}
          </StatusChip>
        </Field>
      </Panel>

      <Panel title="Tasks">
        {deal.tasks.length === 0 ? (
          <EmptyState title="No tasks" hint="Tasks assigned to this deal will show here." />
        ) : (
          <Table ariaLabel="Deal tasks" columns={taskCols} rows={deal.tasks} />
        )}
      </Panel>

      <Panel title="Recent audit">
        {deal.audit.length === 0 ? (
          <EmptyState title="No audit events yet" />
        ) : (
          <Table ariaLabel="Audit events" columns={auditCols} rows={deal.audit} />
        )}
      </Panel>
      {toast ? <Toast message={toast} /> : null}
    </div>
  );
}
