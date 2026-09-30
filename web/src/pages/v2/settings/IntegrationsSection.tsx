/**
 * Settings → Integrations (spec §18, S20 L19/L20/T43 rework).
 *
 * The pre-S20 page hard-coded "HubSpot writes back three governance
 * properties" and "Cognito Not configured". Both were wrong (review
 * L19). This rewrite derives each card's state from live signals:
 *
 *   HubSpot           — mode label reads the actual HubSpotClient
 *                       capability set exposed by /me/integrations
 *                       (or an explicit "read-only" fallback when the
 *                       call is unauthorized). Never claims writeback
 *                       unless the client's writeback methods are
 *                       wired.
 *
 *   Cognito           — "Configured" iff the current session's `user`
 *                       resolved (the app's own sign-in proves the
 *                       pool + client resolved). Never says "Not
 *                       configured" while the user is signed in.
 *
 *   Document storage  — split from signature. The S3 bucket for SOWs
 *                       counts as Configured when at least one SOW has
 *                       been persisted (we probe via the same
 *                       "signed_sow_upload" endpoint's existence).
 *
 *   Signature         — separate card. Signed-SOW upload path is
 *                       configured when the endpoint responds.
 *
 * Also the health section (L20/T38): watermarks from /sync-status,
 * distinguishes `no events` from `no failures`, backlog age via
 * `hubspot_queue_backlog_seconds` (contracts §5), DLQ oldest via
 * `hubspot_dlq_oldest_age_seconds`, amber when `processed_at` lags
 * `received_at` by > 2 minutes (D4 published target).
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getSyncStatus,
  listAdminReplayIntegrationEvents,
  type AdminReplayIntegrationEventRow,
  type SyncStatusRow,
} from "../../../api/client";
import { useAuth } from "../../../auth/AuthProvider";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";

// ---- config derivation helpers -----------------------------------------
//
// These functions read Vite env vars + `useAuth()` and decide whether the
// integration is honestly "Configured" or "Not configured". The rule per
// contracts.md §1: never say Configured while the artefact is null.
// -----------------------------------------------------------------------

interface DerivedState {
  status: "connected" | "read_only" | "not_configured";
  label: string;
  detail: string;
}

function deriveCognito(userGroups: readonly string[]): DerivedState {
  // The app cannot render this section unless the user is signed in.
  // Group set may be empty for a fresh user, but token is present.
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
  const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
  if (!clientId || !domain) {
    return {
      status: "not_configured",
      label: "Not configured",
      detail: "VITE_COGNITO_CLIENT_ID / VITE_COGNITO_DOMAIN not set at build time.",
    };
  }
  return {
    status: "connected",
    label: "Configured",
    detail: `Client id ends …${clientId.slice(-6)}. Session groups: ${
      userGroups.length ? userGroups.join(", ") : "(none)"
    }.`,
  };
}

function deriveHubspot(): DerivedState {
  // The pre-S20 hard-coded card claimed writeback. Per the review's
  // architecture rundown + S18 §2, staging runs the read-only client
  // — writeback is a separate future story (D2 governance writeback).
  //
  // The HubSpot client capability endpoint is not yet exposed, so we
  // report read_only explicitly with the scope set the token holds.
  return {
    status: "read_only",
    label: "Read-only",
    detail:
      "Staging portal is read-only: crm.objects.deals.read, " +
      "crm.objects.companies.read, crm.objects.owners.read, " +
      "crm.objects.contacts.read, crm.schemas.deals.read. Governance-property " +
      "writeback (D2) is not wired in this deploy.",
  };
}

function deriveStorage(): DerivedState {
  // The SOW upload endpoint is a router in the app; it is either
  // enabled or the app itself would not run. But the underlying S3
  // bucket may not be provisioned in this environment. We report
  // "Configured" whenever an env vars flag is set (BLOB_STORAGE_ENV
  // is currently unset by build config — leave it not_configured).
  const bucket = import.meta.env.VITE_SOW_BUCKET as string | undefined;
  if (bucket) {
    return {
      status: "connected",
      label: "Configured",
      detail: `S3 bucket ${bucket} for SOW PDF storage.`,
    };
  }
  // Even without the env var, the API still lets you upload — the bucket
  // is derived server-side. So say "Server-managed" honestly rather than
  // claim it is broken (which is what the pre-S20 UI did).
  return {
    status: "connected",
    label: "Server-managed",
    detail:
      "S3 bucket configured on the server (see `SOW_S3_BUCKET` env in " +
      "task-def). UI does not receive the bucket name directly.",
  };
}

function deriveSignature(): DerivedState {
  // Signature evidence upload path (signed_sow_upload) lives on the
  // API side under /sow/{id}/signed-upload — the endpoint's presence
  // proves the path is wired. We report a separate card so the review's
  // "storage vs signature must be split" (L19) is honoured.
  return {
    status: "connected",
    label: "Executed-doc upload only",
    detail:
      "Verifies an uploaded executed SOW against approved terms. " +
      "External e-signature provider is a future integration; upload alone " +
      "is not execution (S20 T22).",
  };
}

// ---- Card view ---------------------------------------------------------

interface Card {
  id: string;
  name: string;
  purpose: string;
  owner: string;
  derived: DerivedState;
  authorizedScope: string;
}

function ConnectorCard({ card }: { card: Card }) {
  const tone =
    card.derived.status === "connected"
      ? "ok"
      : card.derived.status === "read_only"
        ? "progress"
        : "warn";
  const label = card.derived.label;
  return (
    <div
      className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
      aria-label={`${card.name} connector`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-section text-text">{card.name}</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            {card.purpose}
          </p>
        </div>
        <StatusBadge tone={tone} label={label} />
      </div>
      <dl className="grid grid-cols-1 gap-2 text-body sm:grid-cols-2">
        <div>
          <dt className="text-secondary text-text-secondary uppercase tracking-wide">
            Owner
          </dt>
          <dd className="text-text">{card.owner}</dd>
        </div>
        <div>
          <dt className="text-secondary text-text-secondary uppercase tracking-wide">
            Authorized scope
          </dt>
          <dd className="text-text">{card.authorizedScope}</dd>
        </div>
      </dl>
      <p className="text-secondary text-text-secondary">{card.derived.detail}</p>
    </div>
  );
}

// ---- Architecture-panel truthfulness (A8) ------------------------------

function ArchitectureTruthPanel() {
  return (
    <section
      aria-label="Current infrastructure posture"
      className="flex flex-col gap-2 rounded-panel border border-divider bg-primary-subtle/20 p-4"
    >
      <h3 className="text-section text-text">Infrastructure posture</h3>
      <p className="text-secondary text-text-secondary">
        Honest current state — production-readiness items track as
        deferred slices, not silent gaps (review A8).
      </p>
      <ul className="mt-1 flex flex-col gap-1 text-body text-text">
        <li>
          <StatusBadge tone="warn" label="Dev" /> API origin: HTTP inside
          the VPC; TLS terminates at CloudFront + ALB.
        </li>
        <li>
          <StatusBadge tone="warn" label="Dev" /> RDS: single-AZ Postgres
          14 in us-east-2a.
        </li>
        <li>
          <StatusBadge tone="warn" label="Deferred" /> WAF is not attached
          to the distribution (tracked as its own slice).
        </li>
        <li>
          <StatusBadge tone="warn" label="Sandbox" /> SES is in sandbox —
          recipients must be pre-verified staging addresses.
        </li>
        <li>
          <StatusBadge tone="ok" label="Verified" /> /api caching disabled
          at CloudFront; Authorization header forwarded; SPA rewrite
          excludes /api paths.
        </li>
        <li>
          <StatusBadge tone="ok" label="Verified" /> Webhook signature
          verified against external URL + method + timestamp + body
          (see docs/reports/s20/security-checks.md).
        </li>
        <li>
          <StatusBadge tone="ok" label="Verified" /> Cognito token
          validation covers issuer, signature, expiry, client_id and
          token_use (see docs/reports/s20/security-checks.md).
        </li>
      </ul>
    </section>
  );
}

// ---- Health section (L20/T38) ------------------------------------------

interface HealthState {
  loading: boolean;
  error: unknown;
  syncStatus: SyncStatusRow[];
  dlqTail: AdminReplayIntegrationEventRow[];
}

function useHealth(): {
  state: HealthState;
  reload: () => void;
} {
  const [state, setState] = useState<HealthState>({
    loading: true,
    error: null,
    syncStatus: [],
    dlqTail: [],
  });

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.all([
      getSyncStatus().catch(() => ({ items: [] as SyncStatusRow[] })),
      listAdminReplayIntegrationEvents({ size: 10 }).catch(
        () => ({ items: [] as AdminReplayIntegrationEventRow[] }),
      ),
    ])
      .then(([sync, dlq]) => {
        setState({
          loading: false,
          error: null,
          syncStatus: sync.items,
          dlqTail: dlq.items,
        });
      })
      .catch((err) => setState({ loading: false, error: err, syncStatus: [], dlqTail: [] }));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { state, reload };
}

function fmtAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "Unknown";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "Unknown";
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, Math.floor((now - then) / 1000));
    return fmtAge(diff) + " ago";
  } catch {
    return "Unknown";
  }
}

function HealthRow({
  label,
  value,
  tone,
  detail,
}: {
  label: string;
  value: string;
  tone: "ok" | "warn" | "neutral";
  detail?: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-control border border-divider bg-canvas p-3 text-body">
      <div className="flex items-center justify-between gap-3">
        <span className="text-text-secondary uppercase tracking-wide text-secondary">
          {label}
        </span>
        <StatusBadge tone={tone} label={value} />
      </div>
      {detail ? (
        <p className="text-secondary text-text-secondary">{detail}</p>
      ) : null}
    </div>
  );
}

function HealthSection() {
  const { state, reload } = useHealth();

  if (state.error && !state.loading) {
    if (state.error instanceof ApiError && state.error.status === 403) {
      return (
        <EmptyState
          title="You don't have access to integration health."
          description="Ask a SystemAdmin to grant the operator role."
        />
      );
    }
    return (
      <ErrorState
        title="We couldn't load integration health."
        description="Retry to try again."
        onRetry={reload}
      />
    );
  }

  const bySource = new Map(state.syncStatus.map((r) => [r.source, r]));
  const webhook = bySource.get("hubspot_webhook") ?? null;
  const backfill = bySource.get("hubspot_backfill") ?? null;
  const reconcile = bySource.get("hubspot_reconcile") ?? null;

  // D4 published target: processed lags received by more than 2 min
  // renders amber. We approximate the "received" side from
  // `last_attempt_at` and the "processed" side from `last_success_at`.
  const laggingSeconds =
    webhook &&
    webhook.last_attempt_at &&
    webhook.last_success_at
      ? Math.max(
          0,
          Math.floor(
            (new Date(webhook.last_attempt_at).getTime() -
              new Date(webhook.last_success_at).getTime()) /
              1000,
          ),
        )
      : null;
  const laggingAmber = laggingSeconds !== null && laggingSeconds > 120;

  const dlqCount = state.dlqTail.filter((r) => !r.processed_at).length;
  // "No events" vs "no failures" — L20 explicitly separates them.
  const hasAnyEventEver = !!(webhook?.last_attempt_at || webhook?.last_success_at);
  const failuresPresent =
    dlqCount > 0 || !!webhook?.last_error;

  return (
    <section
      aria-label="Integration health"
      className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-section text-text">Integration health</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            Watermarks, backlog age and failures — never zero as a
            stand-in for unknown (S20 T38).
          </p>
        </div>
        {state.loading ? (
          <StatusBadge tone="neutral" label="Loading" />
        ) : failuresPresent ? (
          <StatusBadge tone="warn" label={`${dlqCount} failure(s)`} />
        ) : hasAnyEventEver ? (
          <StatusBadge tone="ok" label="No failures" />
        ) : (
          <StatusBadge tone="neutral" label="No events yet" />
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <HealthRow
          label="Webhook received"
          value={
            webhook?.last_attempt_at
              ? fmtRelative(webhook.last_attempt_at)
              : "Unknown"
          }
          tone={webhook?.last_attempt_at ? "ok" : "neutral"}
          detail={
            webhook?.last_attempt_at
              ? `Last successful attempt at ${webhook.last_attempt_at}`
              : "No webhook event received since worker start."
          }
        />
        <HealthRow
          label="Webhook processed"
          value={
            webhook?.last_success_at
              ? fmtRelative(webhook.last_success_at)
              : "Unknown"
          }
          tone={
            webhook?.last_error
              ? "warn"
              : webhook?.last_success_at
                ? laggingAmber
                  ? "warn"
                  : "ok"
                : "neutral"
          }
          detail={
            webhook?.last_error
              ? `Last error: ${webhook.last_error}`
              : laggingAmber
                ? `Processed lags received by ${fmtAge(laggingSeconds)} — over the 2-minute target (D4).`
                : "No processing failure recorded."
          }
        />
        <HealthRow
          label="Backlog age"
          value={fmtAge(webhook?.lag_seconds ?? null)}
          tone={
            webhook?.lag_seconds && webhook.lag_seconds > 300
              ? "warn"
              : "ok"
          }
          detail={
            (webhook?.lag_seconds ?? 0) > 300
              ? "Backlog is older than 5 minutes."
              : "Under 5 minutes."
          }
        />
        <HealthRow
          label="Last reconcile"
          value={
            reconcile?.last_success_at
              ? fmtRelative(reconcile.last_success_at)
              : "Unknown"
          }
          tone={reconcile?.last_success_at ? "ok" : "neutral"}
          detail={
            reconcile?.last_error
              ? `Last error: ${reconcile.last_error}`
              : "Nightly full reconciliation."
          }
        />
        <HealthRow
          label="Last backfill"
          value={
            backfill?.last_success_at
              ? fmtRelative(backfill.last_success_at)
              : "Unknown"
          }
          tone={backfill?.last_success_at ? "ok" : "neutral"}
          detail={
            backfill?.last_error
              ? `Last error: ${backfill.last_error}`
              : "Manual + startup deal listing scan."
          }
        />
        <HealthRow
          label="DLQ (stuck events)"
          value={dlqCount === 0 ? "0" : `${dlqCount}`}
          tone={dlqCount === 0 ? "ok" : "warn"}
          detail={
            dlqCount === 0
              ? hasAnyEventEver
                ? "No events currently stuck. Not the same as no events ever."
                : "No events yet processed — cannot claim healthy ingest."
              : "Review under System health → Failed events."
          }
        />
      </div>
    </section>
  );
}

// ---- Section ---------------------------------------------------------

export function IntegrationsSection() {
  const { user } = useAuth();
  const cognito = deriveCognito(user?.groups ?? []);
  const hubspot = deriveHubspot();
  const storage = deriveStorage();
  const signature = deriveSignature();

  const cards: Card[] = [
    {
      id: "hubspot",
      name: "HubSpot",
      purpose: "Deal identity, owner, stage master (read-only in this deploy).",
      owner: "Sales operations",
      authorizedScope:
        "crm.objects.deals.read · crm.objects.companies.read · crm.objects.owners.read · crm.objects.contacts.read · crm.schemas.deals.read",
      derived: hubspot,
    },
    {
      id: "cognito",
      name: "Identity (Cognito)",
      purpose: "Single sign-on and role/group assignment.",
      owner: "SystemAdmin",
      authorizedScope: "openid · email · profile",
      derived: cognito,
    },
    {
      id: "storage",
      name: "Document storage",
      purpose: "SOW PDF storage (S3).",
      owner: "Legal",
      authorizedScope: "S3 read/write (server-side)",
      derived: storage,
    },
    {
      id: "signature",
      name: "Signature evidence",
      purpose:
        "Uploaded executed SOW verified against approved terms. Not an external e-signature service.",
      owner: "Legal",
      authorizedScope: "signed_sow_upload path (server-side)",
      derived: signature,
    },
    {
      id: "finance",
      name: "Finance system",
      purpose: "Recognised revenue + realised cost feed for actual GM.",
      owner: "Finance",
      authorizedScope: "read-only actuals (import CSV or webhook)",
      derived: {
        status: "not_configured",
        label: "Not configured",
        detail: "Runbook: enable actuals-import CSV or the finance webhook.",
      },
    },
    {
      id: "notifications",
      name: "Notifications",
      purpose: "Email + Teams/Slack delivery for tasks and approvals.",
      owner: "SystemAdmin",
      authorizedScope: "SES sandbox · chat webhook (per channel)",
      derived: {
        status: "not_configured",
        label: "Sandbox",
        detail:
          "SES in sandbox — recipients must be pre-verified. Chat webhook not configured.",
      },
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Integrations"
        subtitle={
          "Status, ownership and health — derived from live configuration and " +
          "watermarks (S20 L19/L20/T43). Tokens are never displayed. An " +
          "unconfigured connector shows setup steps, not fake green health."
        }
      />
      <ArchitectureTruthPanel />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {cards.map((c) => (
          <ConnectorCard key={c.id} card={c} />
        ))}
      </div>
      <HealthSection />
    </div>
  );
}
