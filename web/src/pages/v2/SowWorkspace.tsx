import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { RecordHeader } from "../../ui-v2/RecordHeader";
import { RecordTabs, type RecordTabItem } from "../../ui-v2/RecordTabs";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { ActivityTab } from "./sow-workspace/ActivityTab";
import { ApprovalsTab } from "./sow-workspace/ApprovalsTab";
import { DocumentsTab } from "./sow-workspace/DocumentsTab";
import { HandoffTab } from "./sow-workspace/HandoffTab";
import { OverviewTab } from "./sow-workspace/OverviewTab";
import { ProgressRail } from "./sow-workspace/ProgressRail";
import { ScopeTab } from "./sow-workspace/ScopeTab";
import { SignatureTab } from "./sow-workspace/SignatureTab";
import { StaffingGmTab } from "./sow-workspace/StaffingGmTab";
import { loadWorkspace } from "./sow-workspace/dataLoader";
import {
  buildRail,
  buildReadiness,
  defaultTabFor,
  nextValidStep,
  type WorkspaceSnapshot,
} from "./sow-workspace/readiness";
import { formatDate, shortId } from "./sow-workspace/format";

const TAB_ORDER = [
  "overview",
  "scope",
  "staffing",
  "approvals",
  "documents",
  "signature",
  "handoff",
  "activity",
] as const;

type TabKey = (typeof TAB_ORDER)[number];

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview",
  scope: "Scope",
  staffing: "Staffing & GM",
  approvals: "Approvals",
  documents: "Documents",
  signature: "Signature",
  handoff: "Handoff",
  activity: "Activity",
};

/**
 * SOW workspace (spec §8) — one durable route per SOW, eight tabs that
 * mirror the spec's information architecture, and an always-visible
 * readiness panel so the "primary action" is never mysteriously disabled.
 */
export function SowWorkspacePage() {
  const { id, tab } = useParams<{ id: string; tab?: string }>();
  const nav = useNavigate();
  const [snap, setSnap] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [degraded, setDegraded] = useState<string[]>([]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    loadWorkspace(id)
      .then((res) => {
        if (cancelled) return;
        setSnap(res.snap);
        setDegraded(res.degradedEndpoints);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const activeTab: TabKey = useMemo(() => {
    if (tab && (TAB_ORDER as readonly string[]).includes(tab)) return tab as TabKey;
    if (!snap) return "overview";
    return defaultTabFor(snap) as TabKey;
  }, [tab, snap]);

  if (!id) {
    return <EmptyState title="Missing SOW id" description="Return to the SOW list." />;
  }

  if (loading && !snap) {
    return (
      <div className="p-6">
        <p className="text-body text-text-secondary">Loading workspace…</p>
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load this SOW"
        description={error}
        onRetry={() => nav(0)}
      />
    );
  }

  if (!snap) {
    return (
      <EmptyState
        title="No workspace data"
        description="The record has no data yet."
      />
    );
  }

  const step = nextValidStep(snap);
  const rail = buildRail(snap);
  const readiness = buildReadiness(snap);
  const items: RecordTabItem[] = TAB_ORDER.map((key) => ({
    value: key,
    label: TAB_LABELS[key],
    href: `/sows/${id}/${key}`,
    content: renderTab(key, snap),
  }));

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 bg-background pb-3">
        <RecordHeader
          eyebrow={snap.deal?.client_name ?? "Client"}
          title={
            snap.sow
              ? `SOW · ${shortId(snap.sow.id)}`
              : `Opportunity · ${shortId(snap.deal?.hubspot_deal_id)}`
          }
          identity={
            <>
              <span>ID {shortId(id)}</span>
              <span>Owner {snap.deal?.owner_id ?? "Unassigned"}</span>
              <span>Type {snap.deal?.engagement_type ?? "—"}</span>
              <span>
                Delivery {snap.gmModel?.delivery_pattern ?? "—"}
              </span>
              <span>
                Term {formatDate(snap.sow?.uploaded_at ?? null) ?? "—"}
              </span>
              <span data-testid="sow-version">
                SOW v {snap.sow ? shortId(snap.sow.id) : "—"}
              </span>
              <span data-testid="gm-version">
                GM v {snap.gmModel ? shortId(snap.gmModel.id) : "—"}
              </span>
            </>
          }
          status={
            <>
              <StatusBadge
                tone={
                  snap.agreements.some(
                    (a) => a.kind === "NDA" && a.state === "executed",
                  )
                    ? "ok"
                    : "warn"
                }
                label="NDA"
              />
              <StatusBadge
                tone={
                  snap.agreements.some(
                    (a) => a.kind === "MSA" && a.state === "executed",
                  )
                    ? "ok"
                    : "warn"
                }
                label="MSA"
              />
              <StatusBadge
                tone={snap.sow?.confirmed_at ? "ok" : "warn"}
                label={snap.sow?.confirmed_at ? "Scope confirmed" : "Scope draft"}
              />
              <StatusBadge
                tone={
                  snap.gmModel?.computed?.complete ? "ok" : "warn"
                }
                label={
                  snap.gmModel?.computed?.complete
                    ? "Financials complete"
                    : "Financials incomplete"
                }
              />
              <StatusBadge
                tone={
                  snap.approvalPackage?.status === "released"
                    ? "ok"
                    : snap.approvalPackage
                      ? "warn"
                      : "neutral"
                }
                label={
                  snap.approvalPackage
                    ? snap.approvalPackage.status.replace(/_/g, " ")
                    : "Not submitted"
                }
              />
            </>
          }
          primaryAction={
            <Button
              type="button"
              disabled={step.disabled}
              onClick={() => step.href && nav(`/sows/${id}/${step.href}`)}
              aria-label={step.label}
              title={step.reason}
            >
              {step.label}
            </Button>
          }
        />

        <div className="mt-3">
          <ProgressRail rail={rail} />
        </div>

        {degraded.length > 0 ? (
          <p className="mt-2 text-secondary text-warning">
            Degraded: {degraded.join(", ")} — some panels show best-effort
            data.
          </p>
        ) : null}

        {step.disabled && step.reason ? (
          <p className="mt-2 text-secondary text-text-secondary">
            Primary action held: {step.reason}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3">
          <RecordTabs items={items} value={activeTab} />
        </div>
        <aside className="lg:col-span-1 hidden lg:block">
          <div className="sticky top-56">
            <section
              aria-label="Readiness"
              className="rounded-panel border border-divider bg-surface p-4"
            >
              <h2 className="text-section text-text mb-3">Readiness</h2>
              <ul className="space-y-2">
                {readiness.slice(0, 6).map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-2 text-body text-text"
                  >
                    <span>{item.label}</span>
                    <StatusBadge tone={item.status} label={item.statusLabel} />
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}

function renderTab(key: TabKey, snap: WorkspaceSnapshot) {
  switch (key) {
    case "overview":
      return <OverviewTab snap={snap} />;
    case "scope":
      return <ScopeTab snap={snap} />;
    case "staffing":
      return <StaffingGmTab snap={snap} />;
    case "approvals":
      return <ApprovalsTab snap={snap} />;
    case "documents":
      return <DocumentsTab snap={snap} />;
    case "signature":
      return <SignatureTab snap={snap} />;
    case "handoff":
      return <HandoffTab snap={snap} />;
    case "activity":
      return <ActivityTab snap={snap} />;
  }
}
