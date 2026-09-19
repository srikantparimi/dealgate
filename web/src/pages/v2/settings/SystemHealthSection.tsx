/**
 * Settings → System health (spec §18).
 *
 * Tabs: Overview / Failed events / Notification delivery / Reconciliation.
 *
 * The API today exposes three DLQ listings + replay endpoints:
 *   listAdminReplayHubspotWriteback / replayAdminHubspotWriteback
 *   listAdminReplayNotifications    / replayAdminNotification
 *   listAdminReplayIntegrationEvents/ replayAdminIntegrationEvent
 *
 * Every "Review and retry" opens a preflight card that surfaces the
 * business effect, previous attempts and duplicate protection before
 * the operator confirms — spec §18 is explicit that we never blindly
 * replay a signed-contract distribution or duplicate an approval.
 *
 * Raw payloads are not shown here (spec §18 restricts + redacts them).
 * Every replay writes an audit_event server-side (CLAUDE.md rule 5).
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  listAdminReplayHubspotWriteback,
  listAdminReplayIntegrationEvents,
  listAdminReplayNotifications,
  replayAdminHubspotWriteback,
  replayAdminIntegrationEvent,
  replayAdminNotification,
  type AdminReplayHubspotRow,
  type AdminReplayIntegrationEventRow,
  type AdminReplayNotificationRow,
  type UUID,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../ui-v2/primitives/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../ui-v2/primitives/tabs";

type TabId = "overview" | "failed-events" | "notifications" | "reconciliation";

interface PreflightData {
  scope: "hubspot" | "notification" | "integration";
  id: UUID;
  title: string;
  effect: string;
  attempts: number | null;
  lastError: string | null;
  duplicateProtection: string;
}

export function SystemHealthSection() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const activeTab = (params.get("tab") as TabId) || "overview";

  const [preflight, setPreflight] = useState<PreflightData | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  async function confirmReplay() {
    if (!preflight) return;
    setBusy(true);
    setToast(null);
    try {
      if (preflight.scope === "hubspot") {
        await replayAdminHubspotWriteback(preflight.id);
      } else if (preflight.scope === "notification") {
        await replayAdminNotification(preflight.id);
      } else {
        await replayAdminIntegrationEvent(preflight.id);
      }
      setToast(`Replay submitted for ${preflight.id.slice(0, 8)}…`);
      setPreflight(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="System health"
        subtitle={
          "Queues, retries and reconciliation. Every replay opens a preflight — " +
          "we never blindly replay a signed contract distribution or duplicate " +
          "an approval. Raw payloads are restricted and redacted."
        }
      />

      {toast ? (
        <div
          role="status"
          className="rounded-panel border border-divider bg-primary-subtle/20 px-3 py-2 text-body text-text"
        >
          {toast}
        </div>
      ) : null}

      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          const next = new URLSearchParams(location.search);
          next.set("tab", v);
          navigate({ search: next.toString() }, { replace: true });
        }}
      >
        <TabsList aria-label="System health tabs">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="failed-events">Failed events</TabsTrigger>
          <TabsTrigger value="notifications">Notification delivery</TabsTrigger>
          <TabsTrigger value="reconciliation">Reconciliation</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewPanel key={`o-${reloadKey}`} />
        </TabsContent>

        <TabsContent value="failed-events">
          <FailedEventsPanel
            key={`fe-${reloadKey}`}
            onPreflight={(row) =>
              setPreflight({
                scope: row.hubspot_deal_id ? "hubspot" : "integration",
                id: row.id,
                title: row.hubspot_deal_id
                  ? `HubSpot writeback for deal ${row.hubspot_deal_id}`
                  : `Integration event ${row.source_event_id ?? row.id}`,
                effect: row.hubspot_deal_id
                  ? "Re-attempts three-property writeback to HubSpot."
                  : "Re-processes the upstream integration event.",
                attempts: row.attempts ?? null,
                lastError: row.last_error ?? null,
                duplicateProtection:
                  "Server dedupes on event id + target state hash before writing.",
              })
            }
          />
        </TabsContent>

        <TabsContent value="notifications">
          <NotificationsPanel
            key={`no-${reloadKey}`}
            onPreflight={(row) =>
              setPreflight({
                scope: "notification",
                id: row.id,
                title: `Notification: ${row.subject}`,
                effect: `Resends "${row.subject}" via ${row.channel} for ${row.category}.`,
                attempts: row.attempts ?? null,
                lastError: row.last_error ?? null,
                duplicateProtection:
                  "Recipient sees at most one delivery per idempotency key.",
              })
            }
          />
        </TabsContent>

        <TabsContent value="reconciliation">
          <ReconciliationPanel />
        </TabsContent>
      </Tabs>

      <PreflightDialog
        preflight={preflight}
        busy={busy}
        onCancel={() => setPreflight(null)}
        onConfirm={() => void confirmReplay()}
      />
    </div>
  );
}

// -----------------------------------------------------------------------------

function OverviewPanel() {
  const [hubspot, setHubspot] = useState<AdminReplayHubspotRow[]>([]);
  const [notif, setNotif] = useState<AdminReplayNotificationRow[]>([]);
  const [events, setEvents] = useState<AdminReplayIntegrationEventRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      listAdminReplayHubspotWriteback({ size: 5 }).catch(() => ({ items: [] as AdminReplayHubspotRow[] })),
      listAdminReplayNotifications({ size: 5 }).catch(() => ({ items: [] as AdminReplayNotificationRow[] })),
      listAdminReplayIntegrationEvents({ size: 5 }).catch(() => ({ items: [] as AdminReplayIntegrationEventRow[] })),
    ])
      .then(([hs, no, ev]) => {
        setHubspot(hs.items);
        setNotif(no.items);
        setEvents(ev.items);
      })
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return (
        <EmptyState
          title="You don't have access to this section."
          description="System health requires the SystemAdmin operator role."
        />
      );
    }
    return (
      <ErrorState
        title="We couldn't load system health."
        description="Retry to try again."
        onRetry={load}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <OverviewTile
        label="HubSpot writebacks"
        count={hubspot.length}
        loading={loading}
      />
      <OverviewTile
        label="Notification failures"
        count={notif.length}
        loading={loading}
      />
      <OverviewTile
        label="Stuck integration events"
        count={events.length}
        loading={loading}
      />
    </div>
  );
}

function OverviewTile({
  label,
  count,
  loading,
}: {
  label: string;
  count: number;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-panel border border-divider bg-surface p-4">
      <span className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </span>
      <span className="text-metric text-text tnum">
        {loading ? "—" : count}
      </span>
      <StatusBadge
        tone={loading ? "neutral" : count === 0 ? "ok" : "warn"}
        label={loading ? "Loading" : count === 0 ? "Healthy" : "Needs attention"}
      />
    </div>
  );
}

// -----------------------------------------------------------------------------

function FailedEventsPanel({
  onPreflight,
}: {
  onPreflight: (row: AdminReplayHubspotRow & Partial<AdminReplayIntegrationEventRow>) => void;
}) {
  const [hubspot, setHubspot] = useState<AdminReplayHubspotRow[]>([]);
  const [events, setEvents] = useState<AdminReplayIntegrationEventRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      listAdminReplayHubspotWriteback({ size: 25 }),
      listAdminReplayIntegrationEvents({ size: 25 }),
    ])
      .then(([hs, ev]) => {
        setHubspot(hs.items);
        setEvents(ev.items);
      })
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return (
        <EmptyState
          title="You don't have access to this section."
          description="Failed-event triage requires the SystemAdmin operator role."
        />
      );
    }
    return (
      <ErrorState
        title="We couldn't load failed events."
        description="Retry to try again."
        onRetry={load}
      />
    );
  }
  if (loading) {
    return <EmptyState title="Loading" description="Fetching failed events." />;
  }
  if (hubspot.length === 0 && events.length === 0) {
    return (
      <EmptyState
        title="No failed events"
        description="Every recent integration event has been processed."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {hubspot.length > 0 ? (
        <section aria-label="HubSpot writeback failures">
          <h3 className="mb-2 text-section text-text">HubSpot writeback</h3>
          <ul className="flex flex-col gap-2">
            {hubspot.map((r) => (
              <FailureRow
                key={r.id}
                title={`Deal ${r.hubspot_deal_id}`}
                subtitle={`${r.attempts} attempt(s)`}
                error={r.last_error}
                onReview={() =>
                  onPreflight({
                    ...r,
                    // TS: allow Partial<AdminReplayIntegrationEventRow> merge.
                  })
                }
              />
            ))}
          </ul>
        </section>
      ) : null}

      {events.length > 0 ? (
        <section aria-label="Integration event queue">
          <h3 className="mb-2 text-section text-text">Integration events</h3>
          <ul className="flex flex-col gap-2">
            {events.map((r) => (
              <FailureRow
                key={r.id}
                title={`Event ${r.source_event_id}`}
                subtitle={r.received_at}
                error={r.processed_at ? null : "Awaiting processing"}
                onReview={() =>
                  onPreflight({
                    id: r.id,
                    opportunity_id: "" as UUID,
                    hubspot_deal_id: "",
                    target_state: {},
                    status: "",
                    attempts: 0,
                    next_attempt_at: null,
                    last_error: r.processed_at ? null : "Awaiting processing",
                    created_at: r.received_at,
                    sent_at: r.processed_at,
                    source_event_id: r.source_event_id,
                  } as AdminReplayHubspotRow & Partial<AdminReplayIntegrationEventRow>)
                }
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function FailureRow({
  title,
  subtitle,
  error,
  onReview,
}: {
  title: string;
  subtitle: string;
  error: string | null;
  onReview: () => void;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-panel border border-divider bg-surface p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-1">
        <span className="text-body font-medium text-text">{title}</span>
        <span className="text-secondary text-text-secondary">{subtitle}</span>
        {error ? (
          <span className="text-secondary text-danger">{error}</span>
        ) : null}
      </div>
      <Button variant="secondary" size="sm" onClick={onReview}>
        Review and retry
      </Button>
    </li>
  );
}

// -----------------------------------------------------------------------------

function NotificationsPanel({
  onPreflight,
}: {
  onPreflight: (row: AdminReplayNotificationRow) => void;
}) {
  const [rows, setRows] = useState<AdminReplayNotificationRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listAdminReplayNotifications({ size: 25 })
      .then((res) => setRows(res.items))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return (
        <EmptyState
          title="You don't have access to this section."
          description="Notification triage requires the SystemAdmin operator role."
        />
      );
    }
    return (
      <ErrorState
        title="We couldn't load notification delivery."
        description="Retry to try again."
        onRetry={load}
      />
    );
  }
  if (loading) {
    return <EmptyState title="Loading" description="Fetching failed notifications." />;
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No failed notifications"
        description="Every recent notification has been delivered."
      />
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => (
        <FailureRow
          key={r.id}
          title={r.subject}
          subtitle={`${r.channel} · ${r.category} · ${r.attempts} attempt(s)`}
          error={r.last_error}
          onReview={() => onPreflight(r)}
        />
      ))}
    </ul>
  );
}

// -----------------------------------------------------------------------------

function ReconciliationPanel() {
  // The reconciliation surface today lives on the legacy import → reconciliation
  // deep link; a dedicated endpoint is not yet exposed. Say so honestly.
  return (
    <EmptyState
      title="Reconciliation viewer not available yet"
      description={
        "Per-batch reconciliation lives on the legacy import wizard until we " +
        "lift it here. Signed handoff and actuals import each have their own " +
        "reconciliation view accessible from those pages."
      }
    />
  );
}

// -----------------------------------------------------------------------------

function PreflightDialog({
  preflight,
  busy,
  onCancel,
  onConfirm,
}: {
  preflight: PreflightData | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={preflight !== null}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Review and retry</DialogTitle>
          <DialogDescription>
            Confirm the effect before the replay runs. This action is audited.
          </DialogDescription>
        </DialogHeader>
        {preflight ? (
          <div className="flex flex-col gap-3 text-body text-text">
            <div>
              <p className="text-secondary text-text-secondary uppercase tracking-wide">
                Target
              </p>
              <p>{preflight.title}</p>
            </div>
            <div>
              <p className="text-secondary text-text-secondary uppercase tracking-wide">
                Business effect
              </p>
              <p>{preflight.effect}</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-secondary text-text-secondary uppercase tracking-wide">
                  Previous attempts
                </p>
                <p className="tnum">{preflight.attempts ?? "0"}</p>
              </div>
              <div>
                <p className="text-secondary text-text-secondary uppercase tracking-wide">
                  Duplicate protection
                </p>
                <p>{preflight.duplicateProtection}</p>
              </div>
            </div>
            {preflight.lastError ? (
              <div>
                <p className="text-secondary text-text-secondary uppercase tracking-wide">
                  Last error
                </p>
                <p className="text-danger">{preflight.lastError}</p>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <DialogClose asChild>
            <Button variant="secondary" disabled={busy}>
              Cancel
            </Button>
          </DialogClose>
          <Button onClick={onConfirm} disabled={busy}>
            {busy ? "Retrying…" : "Confirm retry"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
