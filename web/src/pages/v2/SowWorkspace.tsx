import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import type { CommercialEditorStatus } from "./sow-workspace/CommercialModelEditor";
import { loadWorkspace } from "./sow-workspace/dataLoader";
import {
  buildRail,
  buildReadiness,
  defaultTabFor,
  nextValidStep,
  type WorkspaceSnapshot,
} from "./sow-workspace/readiness";
import { formatTermRange } from "./sow-workspace/format";
import { SubmitApprovalDialog } from "./sow-workspace/SubmitApprovalDialog";
import { workspaceTitle } from "./sow-workspace/readiness";
import {
  assessSowDeletion,
  deleteSow,
  getMe,
  type DeletionAssessmentResponse,
  type MeResponse,
} from "../../api/client";
import { Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../ui-v2/primitives/dialog";
import type { ReactNode as _RN } from "react";
function DialogFooter({ children }: { children: _RN }) {
  return <div className="mt-4 flex justify-end gap-2">{children}</div>;
}

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
/** Mirrors the server's governance-scoped _DELETE_ROLES in
 * api/app/routers/deletion.py — keep the two lists in sync. */
export const SOW_DELETE_ROLES = [
  "SystemAdmin",
  "CEO",
  "SalesLeader",
  "Finance",
  "Legal",
] as const;

export function canDeleteSow(groups: readonly string[] | undefined): boolean {
  return !!groups?.some((g) => (SOW_DELETE_ROLES as readonly string[]).includes(g));
}

export function SowWorkspacePage() {
  const { id, tab } = useParams<{ id: string; tab?: string }>();
  const nav = useNavigate();
  const [snap, setSnap] = useState<WorkspaceSnapshot | null>(null);
  const [snapshotRoute, setSnapshotRoute] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [degraded, setDegraded] = useState<string[]>([]);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(Date.now());
  const [viewer, setViewer] = useState<MeResponse | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteAssessment, setDeleteAssessment] = useState<DeletionAssessmentResponse | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [commercialStatus, setCommercialStatus] = useState<CommercialEditorStatus | null>(null);
  const commercialPrimaryAction = useRef<(() => void) | null>(null);
  const requestNo = useRef(0);
  const currentRoute = useRef(id);
  currentRoute.current = id;
  useEffect(() => { getMe().then(setViewer).catch(() => setViewer(null)); }, []);
  // S20 W3 D6: fetch the deletion assessment so the Delete/Archive
  // button renders the right label from first render. Assessment is
  // cheap (a single count query) and idempotent.
  useEffect(() => {
    if (!snap?.sow?.sow_id) return;
    assessSowDeletion(snap.sow.sow_id).then(setDeleteAssessment).catch(() => setDeleteAssessment(null));
  }, [snap?.sow?.sow_id]);

  const openDelete = useCallback(async () => {
    if (!snap?.sow?.sow_id) return;
    setDeleteOpen(true);
    setDeleteError(null);
    try {
      const a = await assessSowDeletion(snap.sow.sow_id);
      setDeleteAssessment(a);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "Assessment failed";
      setDeleteError(
        raw.includes("insufficient role")
          ? "Deleting a SOW needs a governance role (Finance, Legal, Sales leadership, CEO or SystemAdmin). You are signed in without one."
          : raw,
      );
    }
  }, [snap]);

  const confirmDelete = useCallback(async () => {
    if (!snap?.sow?.sow_id) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await deleteSow(snap.sow.sow_id);
      setDeleteOpen(false);
      nav(`/deletions/${result.job_id}`);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setDeleting(false);
    }
  }, [snap, nav]);

  const refresh = useCallback(async () => {
    if (!id || currentRoute.current !== id) return;
    const number = ++requestNo.current;
    try {
      const res = await loadWorkspace(id);
      if (number !== requestNo.current || currentRoute.current !== id) return;
      setSnap(res.snap); setSnapshotRoute(id); setDegraded(res.degradedEndpoints); setError(null);
      if (!res.degradedEndpoints.includes("listApprovalPackages") && !res.degradedEndpoints.includes("getApprovalPackage")) setUpdatedAt(Date.now());
    } catch (err) {
      if (number === requestNo.current && currentRoute.current === id) setError(err instanceof Error ? err.message : "Workspace unavailable");
    } finally { if (number === requestNo.current && currentRoute.current === id) setLoading(false); }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void refresh();
    return () => {
      requestNo.current++;
    };
  }, [id, tab, refresh]);

  const activeTab: TabKey = useMemo(() => {
    if (tab && (TAB_ORDER as readonly string[]).includes(tab)) return tab as TabKey;
    if (!snap) return "overview";
    return defaultTabFor(snap) as TabKey;
  }, [tab, snap]);

  const registerCommercialAction = useCallback((run: (() => void) | null) => {
    commercialPrimaryAction.current = run;
  }, []);
  const commercialSaved = useCallback(() => {
    if (id) nav(`/sows/new?opportunityId=${id}`);
  }, [id, nav]);

  useEffect(() => {
    if (activeTab === "staffing") return;
    setCommercialStatus(null);
    commercialPrimaryAction.current = null;
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== "approvals") return;
    const interval = window.setInterval(() => { void refresh(); }, 20_000);
    return () => window.clearInterval(interval);
  }, [activeTab, refresh]);

  if (!id) {
    return <EmptyState title="Missing SOW id" description="Return to the SOW list." />;
  }

  if ((loading && !snap) || (snap && snapshotRoute !== id && !error)) {
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

  // S20 W3 L09/L11: a deal with no SowVersion is a valid tracking record
  // — it must not render the SOW workspace shell (which would imply a
  // SOW exists, and expose the Delete button). Show a bordered empty
  // state with "Upload SOW" (pre-bound to this opportunity) and a Back
  // link to the deal (or Pipeline if the deal page isn't ready yet).
  if (!snap.sow) {
    return (
      <div className="space-y-4">
        <RecordHeader
          eyebrow={snap.deal?.client_name ?? "Client"}
          title="No SOW draft for this deal yet"
          identity={
            <>
              {/* S21 item 4: no internal ID line on the no-SOW shell either. */}
              {snap.deal?.owner?.name && <span>Owner {snap.deal.owner.name}</span>}
              {snap.deal?.engagement_type && <span>Type {snap.deal.engagement_type.replaceAll("_", " ")}</span>}
            </>
          }
          primaryAction={
            <div className="flex gap-2">
              <Button
                type="button"
                onClick={() =>
                  nav(
                    `/sows/new?bindOppId=${id}${snap.deal?.client_id ? `&bindClientId=${snap.deal.client_id}` : ""}`,
                  )
                }
                aria-label="Upload SOW"
              >
                Upload SOW
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => nav(snap.deal ? `/deals/${id}` : "/pipeline")}
                aria-label="Back to deal"
              >
                Back
              </Button>
            </div>
          }
        />
        <section
          aria-label="No SOW yet"
          className="rounded-panel border border-divider bg-surface p-6"
        >
          <p className="text-body text-text">
            This deal has no uploaded SOW. Upload the draft to start the
            scope, GM and approvals path. The deal itself keeps its
            comments, actions and reporting whether or not a SOW exists.
          </p>
          <p className="text-secondary text-text-secondary mt-3">
            No SOW is created automatically. Only the file you upload
            here starts a workspace — Delete SOW does not appear until a
            draft actually exists.
          </p>
        </section>
      </div>
    );
  }

  const step = nextValidStep(snap, {
    activeTab,
    commercial: commercialStatus,
  });
  const canSubmit = !!viewer && (viewer.id === snap.deal?.owner_id || viewer.groups.includes("SystemAdmin"));
  const termStart = snap.sow?.extracted_fields?.term_start?.value;
  const termEnd = snap.sow?.extracted_fields?.term_end?.value;
  // S21 item 4: single display format with explicit year on both sides.
  const termDisplay = formatTermRange(
    typeof termStart === "string" ? termStart : null,
    typeof termEnd === "string" ? termEnd : null,
  );
  // S21 item 4 + S21-1c item 1: owner falls back to the SOW uploader
  // when the deal has no owner. Always a display name — never a raw
  // id or UUID prefix (T09 extension: no ids on user-facing fields).
  const ownerDisplay = snap.deal?.owner?.name
    ?? (snap.sow?.uploaded_by_name ? `Uploader · ${snap.sow.uploaded_by_name}` : null);
  const rail = buildRail(snap);
  const readiness = buildReadiness(snap);
  const items: RecordTabItem[] = TAB_ORDER.map((key) => ({
    value: key,
    label: TAB_LABELS[key],
    href: `/sows/${id}/${key}`,
    content: key === "approvals" ? <ApprovalsTab snap={snap} refresh={refresh} updatedAt={updatedAt} canSubmit={canSubmit} /> : renderTab(
      key,
      snap,
      viewer,
      refresh,
      setCommercialStatus,
      registerCommercialAction,
      commercialSaved,
    ),
  }));

  return (
    <div className="space-y-4 min-w-0">
      <div data-testid="workspace-header" className="lg:sticky top-header z-10 bg-canvas pb-3">
        <RecordHeader
          eyebrow={snap.deal?.client_name ?? "Client"}
          title={workspaceTitle(snap)}
          identity={
            <>
              {/* S21 item 4: internal `ID <uuid>` line removed; owner
                  falls back to the uploader (never "Unassigned"); term
                  renders in a single explicit-year format. The SOW/GM
                  version chips stay — they are the content, not the
                  identifier. */}
              {ownerDisplay && <span data-testid="header-owner">Owner {ownerDisplay}</span>}
              {snap.deal?.engagement_type && <span>Type {snap.deal.engagement_type.replaceAll("_", " ")}</span>}
              {snap.gmModel?.delivery_pattern && <span>Delivery {snap.gmModel.delivery_pattern}</span>}
              {termDisplay && <span data-testid="header-term">Term {termDisplay}</span>}
              <span data-testid="sow-version">
                SOW v {snap.sow?.version_no ?? "—"}
              </span>
              <span data-testid="gm-version">
                GM v {snap.gmModel?.version ?? "—"}
              </span>
            </>
          }
          status={
            <>
              {snap.sow?.agreements_signed ? (
                <StatusBadge tone="ok" label="NDA/MSA marked signed" />
              ) : (
                <StatusBadge tone="neutral" label="NDA/MSA note only" />
              )}
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
            <div className="flex gap-2">
              <Button
                type="button"
                className="whitespace-normal h-auto min-h-9 max-w-full text-left"
                disabled={step.disabled || (step.action === "submit" && !canSubmit)}
                onClick={() => {
                  if (step.action === "submit") setSubmitOpen(true);
                  else if (step.action === "commercial") commercialPrimaryAction.current?.();
                  else if (step.label === "Complete scope") nav(`/sows/new?opportunityId=${id}`);
                  else if (step.href) nav(`/sows/${id}/${step.href}`);
                }}
                aria-label={step.label}
                title={step.reason}
              >
                {step.label}
              </Button>
              {/* S21 item 3: a Back control is always present in the
                  workspace header. The gate strip + tab bar are
                  revisitable (both clickable backward until Submit);
                  this control gives the user a one-click exit back to
                  the originating deal — the screenshot 05 complaint
                  was that there was no way back from inside the
                  studio flow. */}
              <Button
                type="button"
                variant="secondary"
                onClick={() => nav(snap.deal ? `/deals/${id}` : "/pipeline")}
                aria-label="Back"
                title="Back to the deal"
                data-testid="workspace-back"
              >
                Back
              </Button>
              {/* S21 item 1: Delete at every state. One label, one
                  action — the confirm dialog names the cascade. Rule 11:
                  the control only renders for roles that can use it. */}
              {canDeleteSow(viewer?.groups) && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => void openDelete()}
                aria-label="Delete SOW"
                title="Delete this SOW. Cascades to approvals, versions, GM runs, documents, next actions, comments, renewals, and any project created from it."
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete SOW
              </Button>
              )}
            </div>
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

        {step.reason ? (
          <p className="mt-2 text-secondary text-text-secondary">
            {step.reason}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-3 min-w-0">
          <RecordTabs items={items} value={activeTab} />
        </div>
        <aside className="lg:col-span-1">
          <div className="sticky top-56">
            <section
              aria-label="Readiness"
              className="rounded-panel border border-divider bg-surface p-4"
            >
              <h2 className="text-section text-text mb-3">Readiness</h2>
              {/* S22 redesign: compact state first — the current blocker,
                  who owns it, and the next action. The full checklist
                  stays below; this is the only readiness panel in the
                  shell. */}
              {(() => {
                const blocker = readiness.find((item) => item.status === "warn");
                return (
                  <p className="text-body text-text mb-3" data-testid="readiness-blocker">
                    {blocker ? (
                      <>
                        Next: <strong>{blocker.label}</strong> — {blocker.statusLabel}
                        {blocker.owner ? <> · {blocker.owner}</> : null}
                        {blocker.hint ? (
                          <span className="block text-secondary text-text-secondary">
                            {blocker.hint}
                          </span>
                        ) : null}
                      </>
                    ) : (
                      "No blockers — all readiness checks are clear."
                    )}
                  </p>
                );
              })()}
              <ul className="space-y-2">
                {readiness.map((item) => (
                  <li
                    key={item.id}
                    className="text-body text-text"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2"><span>{item.label}</span><StatusBadge tone={item.status} label={item.statusLabel} /></div>
                    {(item.owner || item.due) && (
                      <p className="text-secondary text-text-secondary mt-1">
                        {item.owner ? <>Owner: {item.owner}</> : null}
                        {item.owner && item.due ? " · " : null}
                        {item.due ? <>Due: {item.due}</> : null}
                      </p>
                    )}
                    {item.hint && <p className="text-secondary text-text-secondary mt-1">{item.hint}</p>}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </aside>
      </div>
      <SubmitApprovalDialog id={id} open={submitOpen} onOpenChange={setSubmitOpen} onSubmitted={() => { void refresh(); nav(`/sows/${id}/approvals`); }} />
      <Dialog open={deleteOpen} onOpenChange={(o) => (o ? undefined : setDeleteOpen(false))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this SOW?</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-body">
            <p>
              {workspaceTitle(snap)} — client{" "}
              {snap.deal?.client_name ?? "Unassigned"}
            </p>
            <p className="text-secondary text-text-secondary">
              Permanently remove this SOW, its versions, approvals, staffing,
              GM runs, owned files and review tasks. Projects and financial
              actuals are retained with their source marked deleted. The
              client, deal, NDA/MSA files and other SOWs are retained.
              A deletion audit entry remains. This cannot be undone.
            </p>
            {deleteAssessment ? (
              <ul className="text-body">
                {Object.entries(deleteAssessment.counts).map(([k, v]) => (
                  <li key={k} data-testid={`delete-cascade-${k}`}>
                    {k.replaceAll("_", " ")}: {v}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-secondary text-text-secondary">Assessing state…</p>
            )}
            {deleteError ? <p role="alert" className="text-danger">{deleteError}</p> : null}
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button onClick={() => void confirmDelete()} disabled={deleting || !deleteAssessment || !!deleteError}>
              {deleting ? "Deleting…" : "Delete SOW"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function renderTab(
  key: TabKey,
  snap: WorkspaceSnapshot,
  viewer?: MeResponse | null,
  refresh?: () => Promise<void>,
  onCommercialStatusChange?: (status: CommercialEditorStatus | null) => void,
  onCommercialPrimaryAction?: (run: (() => void) | null) => void,
  onCommercialSaved?: () => void | Promise<void>,
) {
  switch (key) {
    case "overview":
      return <OverviewTab snap={snap} />;
    case "scope":
      return <ScopeTab snap={snap} />;
    case "staffing":
      return <StaffingGmTab
        snap={snap}
        onCommercialStatusChange={onCommercialStatusChange}
        onCommercialPrimaryAction={onCommercialPrimaryAction}
        onCommercialSaved={onCommercialSaved}
      />;
    case "approvals":
      return <ApprovalsTab snap={snap} />;
    case "documents":
      return <DocumentsTab snap={snap} />;
    case "signature":
      return <SignatureTab snap={snap} viewer={viewer} refresh={refresh} />;
    case "handoff":
      return <HandoffTab snap={snap} viewer={viewer} refresh={refresh} />;
    case "activity":
      return <ActivityTab snap={snap} />;
  }
}
