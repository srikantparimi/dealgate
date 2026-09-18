import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type {
  DealDetail,
  DealPatch,
  EngagementType,
  SowVersion,
} from "../api/client";
import {
  getCurrentSowVersion,
  getDeal,
  patchDeal,
  submitApprovalPackage,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { DeliveryModelBuilder } from "./DeliveryModelBuilder";
import { SignedSOWReview } from "./SignedSOWReview";
import { SOWConfirm } from "./SOWConfirm";
import { SOWUpload } from "./SOWUpload";

const DELIVERY_ROLES = new Set([
  "Delivery",
  "Presales",
  "Finance",
  "HR",
  "SystemAdmin",
  "CEO",
  "Legal",
]);
const DELIVERY_WRITE_ROLES = new Set(["Delivery", "SystemAdmin"]);

const KNOWN_ENGAGEMENT_TYPES: readonly EngagementType[] = [
  "staff_aug",
  "single_resource",
  "fixed_price",
  "assessment",
  "tm",
  "managed_service",
];

function toEngagementType(value: string | null | undefined): EngagementType | null {
  if (!value) return null;
  return KNOWN_ENGAGEMENT_TYPES.includes(value as EngagementType)
    ? (value as EngagementType)
    : null;
}

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

/** `useAuth` throws when the provider is absent (as in test harnesses that
 * mount the page directly). Wrap it so a missing provider degrades to a
 * read-only view instead of crashing the entire panel. */
function useOptionalAuth(): { user: ReturnType<typeof useAuth>["user"] | null } {
  try {
    const { user } = useAuth();
    return { user };
  } catch {
    return { user: null };
  }
}

export function DealDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useOptionalAuth();
  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [sowVersion, setSowVersion] = useState<SowVersion | null>(null);

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
    // Independent load so a SOW fetch failure never blocks the deal panel.
    getCurrentSowVersion(id)
      .then(setSowVersion)
      .catch(() => setSowVersion(null));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // The API is the real gate — this is a UX hint so the dropzone / confirm
  // buttons render for users who can plausibly perform them. Anyone with
  // Sales/SalesLeader/SystemAdmin sees the write UI; the API still rejects
  // a mutation from a non-owner with 403.
  const groups = user?.groups ?? [];
  const canEditSow =
    groups.includes("SystemAdmin") ||
    groups.includes("Sales") ||
    groups.includes("SalesLeader");

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
        <Field label="Client">
          {deal.client_id ? (
            <Link to={`/clients/${deal.client_id}`} style={{ color: "#1d4ed8" }}>
              {deal.client_name ?? deal.client_id}
            </Link>
          ) : (
            "—"
          )}
        </Field>
      </Panel>

      <Panel title="Tasks">
        {deal.tasks.length === 0 ? (
          <EmptyState title="No tasks" hint="Tasks assigned to this deal will show here." />
        ) : (
          <Table ariaLabel="Deal tasks" columns={taskCols} rows={deal.tasks} />
        )}
      </Panel>

      <Panel title="SOW">
        {sowVersion ? (
          <SOWConfirm
            version={sowVersion}
            onVersionChanged={setSowVersion}
            canEdit={canEditSow}
          />
        ) : canEditSow && id ? (
          <SOWUpload opportunityId={id} onUploaded={setSowVersion} />
        ) : (
          <EmptyState
            title="No SOW uploaded yet"
            hint="The account owner will upload the signed SOW here."
          />
        )}
      </Panel>

      <DeliveryModelPanel
        opportunityId={id ?? null}
        userGroups={groups}
        sowVersion={sowVersion}
      />

      <ApprovalPanel
        opportunityId={id ?? null}
        userGroups={groups}
        ownerId={deal.owner_id}
        currentUserId={user?.sub ?? null}
        latestPackage={deal.latest_package ?? null}
        onSubmitted={load}
      />

      {deal.latest_package?.status === "ready_to_sign" ? (
        <Panel title="Signed SOW">
          <SignedSOWReview
            packageId={deal.latest_package.id}
            canWrite={
              groups.includes("SystemAdmin") ||
              (deal.owner_id !== null && user?.sub === deal.owner_id)
            }
          />
        </Panel>
      ) : null}

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

/** Inline Delivery Model panel — hidden for roles that must not see cost
 * bands (Sales/Marketing). Once the SOW has been confirmed the Builder
 * mounts inline; otherwise we render a hint plus a "Start anyway" button
 * so Delivery can still model an early plan.
 */
function DeliveryModelPanel({
  opportunityId,
  userGroups,
  sowVersion,
}: {
  opportunityId: string | null;
  userGroups: string[];
  sowVersion: SowVersion | null;
}) {
  const [open, setOpen] = useState(false);
  const canRead = userGroups.some((g) => DELIVERY_ROLES.has(g));
  const canWrite = userGroups.some((g) => DELIVERY_WRITE_ROLES.has(g));
  if (!opportunityId || !canRead) return null;

  const sowConfirmed = Boolean(sowVersion?.confirmed_at);
  const suggested = toEngagementType(
    sowVersion?.engagement_type_confirmed ?? sowVersion?.engagement_type_suggested ?? null,
  );

  return (
    <Panel title="Delivery model">
      {!open ? (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            {sowConfirmed ? (
              <span data-testid="dm-hint-confirmed">
                SOW confirmed — open the Builder to plan resources.
              </span>
            ) : (
              <span data-testid="dm-hint-no-sow">
                SOW not confirmed yet; the Builder will pre-select the confirmed
                engagement type once it lands.
              </span>
            )}
          </div>
          {canWrite ? (
            <button
              type="button"
              onClick={() => setOpen(true)}
              data-testid="dm-open-btn"
              style={{
                padding: "6px 12px",
                background: "#111827",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              Open builder
            </button>
          ) : (
            <span style={{ fontSize: 12, color: "#6b7280" }}>Read-only role</span>
          )}
        </div>
      ) : (
        <DeliveryModelBuilder
          opportunityId={opportunityId}
          suggestedEngagement={suggested}
          sowVersionId={sowVersion?.id ?? null}
        />
      )}
    </Panel>
  );
}

const APPROVAL_STATUS_TONE: Record<
  string,
  "ok" | "warn" | "block" | "neutral"
> = {
  pending_delivery_hr: "warn",
  pending_finance_legal: "warn",
  pending_ceo_exception: "block",
  ready_to_sign: "ok",
  voided: "neutral",
  rejected: "block",
};

/** Approval package panel — shows the current package (if any) with a
 * link to its detail, and lets the account owner (or SystemAdmin) submit
 * a fresh package once no active one exists. Every guard is UX-only; the
 * server rejects unauthorised POSTs with 403 either way. */
function ApprovalPanel({
  opportunityId,
  userGroups,
  ownerId,
  currentUserId,
  latestPackage,
  onSubmitted,
}: {
  opportunityId: string | null;
  userGroups: readonly string[];
  ownerId: string | null;
  currentUserId: string | null;
  latestPackage:
    | {
        id: string;
        status:
          | "pending_delivery_hr"
          | "pending_finance_legal"
          | "pending_ceo_exception"
          | "ready_to_sign"
          | "voided"
          | "rejected";
        submitted_at: string | null;
      }
    | null;
  onSubmitted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (!opportunityId) return null;

  const isOwner = ownerId !== null && currentUserId !== null && ownerId === currentUserId;
  const isAdmin = userGroups.includes("SystemAdmin");
  const canSubmit = isOwner || isAdmin;
  const activeStatuses = new Set([
    "pending_delivery_hr",
    "pending_finance_legal",
    "pending_ceo_exception",
    "ready_to_sign",
  ]);
  const activePackage =
    latestPackage && activeStatuses.has(latestPackage.status) ? latestPackage : null;

  async function submit() {
    if (!opportunityId) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitApprovalPackage(opportunityId);
      onSubmitted();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Panel title="Approval package">
      {activePackage ? (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <StatusChip tone={APPROVAL_STATUS_TONE[activePackage.status] ?? "neutral"}>
            {activePackage.status}
          </StatusChip>
          <Link to={`/approvals/${activePackage.id}`} style={{ color: "#1d4ed8" }}>
            View package
          </Link>
          <span style={{ color: "#6b7280", fontSize: 13 }}>
            submitted {activePackage.submitted_at?.slice(0, 19) ?? "—"}Z
          </span>
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ color: "#6b7280", fontSize: 13 }}>
            {latestPackage
              ? `Previous package ${latestPackage.status}. Submit a fresh one when ready.`
              : "No approval package submitted yet."}
          </span>
          {canSubmit ? (
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              data-testid="submit-approval-btn"
              style={{
                padding: "6px 12px",
                background: "#111827",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: submitting ? "wait" : "pointer",
                fontSize: 13,
              }}
            >
              {submitting ? "Submitting…" : "Submit for approval"}
            </button>
          ) : (
            <span style={{ fontSize: 12, color: "#6b7280" }}>
              Only the account owner may submit.
            </span>
          )}
        </div>
      )}
      {error ? (
        <p style={{ color: "#991b1b", marginTop: 8, fontSize: 13 }}>
          {String((error as { message?: string })?.message ?? error)}
        </p>
      ) : null}
    </Panel>
  );
}
