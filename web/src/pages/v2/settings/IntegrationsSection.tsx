/**
 * Settings → Integrations (spec §18).
 *
 * Cards for HubSpot, identity, storage, finance, notifications. The one
 * connector with real health telemetry today is HubSpot (via the
 * integration-events DLQ). Everything else is "Not configured — see
 * setup steps" per spec §18: "an unconfigured connector shows setup
 * steps, not fake green health."
 *
 * Tokens are never displayed here. Even the HubSpot connector shows the
 * queue tail, not the API key.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  listAdminReplayIntegrationEvents,
  type AdminReplayIntegrationEventRow,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";

interface ConnectorDef {
  id: string;
  name: string;
  purpose: string;
  owner: string;
  scopes: string;
  status: "connected" | "not_configured";
  detail: string;
}

const CONNECTORS: ConnectorDef[] = [
  {
    id: "hubspot",
    name: "HubSpot",
    purpose: "Deal identity, owner and stage master. Writes back three governance properties.",
    owner: "Sales operations",
    scopes: "crm.objects.deals.read · crm.objects.companies.read · crm.objects.contacts.read · writeback",
    status: "connected",
    detail: "The DLQ tail on this card is the honest signal — see below.",
  },
  {
    id: "identity",
    name: "Identity (Cognito)",
    purpose: "Single sign-on and role/group assignment.",
    owner: "SystemAdmin",
    scopes: "openid · email · profile",
    status: "not_configured",
    detail: "Runbook: register app client, configure hosted UI, wire callback URL.",
  },
  {
    id: "storage",
    name: "Document storage & signature",
    purpose: "SOW PDF storage; signature evidence for executed agreements.",
    owner: "Legal",
    scopes: "S3 bucket · signature webhook",
    status: "not_configured",
    detail: "Runbook: provision bucket, exchange signature-provider webhook secret.",
  },
  {
    id: "finance",
    name: "Finance system",
    purpose: "Recognised revenue + realised cost feed for actual GM.",
    owner: "Finance",
    scopes: "read-only actuals",
    status: "not_configured",
    detail: "Runbook: enable actuals-import CSV or the finance webhook.",
  },
  {
    id: "notifications",
    name: "Notifications",
    purpose: "Email + Teams/Slack delivery for tasks and approvals.",
    owner: "SystemAdmin",
    scopes: "SES · chat webhook",
    status: "not_configured",
    detail: "Runbook: verify SES domain, register chat webhook per channel.",
  },
];

export function IntegrationsSection() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Integrations"
        subtitle={
          "Status, ownership and errors. Tokens are never displayed here. " +
          "An unconfigured connector shows setup steps — not fake green health."
        }
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {CONNECTORS.map((c) => (
          <ConnectorCard key={c.id} connector={c} />
        ))}
      </div>
      <HubspotHealthCard />
    </div>
  );
}

function ConnectorCard({ connector }: { connector: ConnectorDef }) {
  return (
    <div
      className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
      aria-label={`${connector.name} connector`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-section text-text">{connector.name}</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            {connector.purpose}
          </p>
        </div>
        {connector.status === "connected" ? (
          <StatusBadge tone="ok" label="Connected" />
        ) : (
          <StatusBadge tone="warn" label="Not configured" />
        )}
      </div>
      <dl className="grid grid-cols-1 gap-2 text-body sm:grid-cols-2">
        <div>
          <dt className="text-secondary text-text-secondary uppercase tracking-wide">
            Owner
          </dt>
          <dd className="text-text">{connector.owner}</dd>
        </div>
        <div>
          <dt className="text-secondary text-text-secondary uppercase tracking-wide">
            Authorized scope
          </dt>
          <dd className="text-text">{connector.scopes}</dd>
        </div>
      </dl>
      <p className="text-secondary text-text-secondary">{connector.detail}</p>
    </div>
  );
}

function HubspotHealthCard() {
  const [rows, setRows] = useState<AdminReplayIntegrationEventRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listAdminReplayIntegrationEvents({ size: 10 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section
      aria-label="HubSpot integration events tail"
      className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-section text-text">HubSpot recent events</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            Tail of the integration-event queue. Empty is healthy.
          </p>
        </div>
        {loading ? (
          <StatusBadge tone="neutral" label="Loading" />
        ) : rows.length === 0 ? (
          <StatusBadge tone="ok" label="No stuck events" />
        ) : (
          <StatusBadge tone="warn" label={`${rows.length} stuck`} />
        )}
      </div>
      {error ? (
        error instanceof ApiError && error.status === 403 ? (
          <EmptyState
            title="You don't have access to this section."
            description="Ask a SystemAdmin to grant the operator role."
          />
        ) : (
          <ErrorState
            title="We couldn't reach the integration-event tail."
            description="Retry to try again."
            onRetry={load}
          />
        )
      ) : rows.length === 0 ? (
        <EmptyState
          title="No stuck integration events"
          description="Every webhook has been processed."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((r) => (
            <li
              key={r.id}
              className="flex items-center justify-between gap-3 rounded-control border border-divider bg-canvas px-3 py-2 text-body"
            >
              <span className="font-mono text-text">{r.source_event_id}</span>
              <span className="text-text-secondary">
                {r.processed_at ? "Processed" : "Pending"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
