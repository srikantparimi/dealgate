import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type {
  ClientDetail,
  ClientLegalEntity,
  ClientOpportunity,
  ClientRecentActivity,
} from "../api/client";
import { getClient } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { getIdTokenClaims } from "../auth/cognito";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { DeletionConfirmationDialog } from "../ui-v2/DeletionConfirmationDialog";
import { Button } from "../ui-v2/primitives/button";
import { AgreementsPanel } from "./AgreementsPanel";
import { coverageTone } from "./ClientList";

// S5 E10: "SOWs & GM" tab visibility mirrors the governance read set that
// the ``/dashboards/client/{id}`` API enforces. The API is the source of
// truth; hiding the tab is a UX hint, not a security boundary.
const SOW_GM_TAB_ROLES = new Set([
  "Finance",
  "CEO",
  "Delivery",
  "SystemAdmin",
]);

// S13a-FE: role gate for the "Delete client" button. Mirrors
// `api/app/routers/deletion.py::_DELETE_ROLES`. Server enforces this
// on every write — hiding the button is UX only.
const DELETE_ROLES: readonly string[] = [
  "SystemAdmin",
  "CEO",
  "SalesLeader",
  "Finance",
  "Legal",
];

function userCanDelete(claimGroups: string[] | null): boolean {
  const groups = claimGroups ?? [];
  return groups.some((g) => DELETE_ROLES.includes(g));
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

function useOptionalAuth() {
  // Existing ClientDetail tests render the page without wrapping it in
  // AuthProvider. Wrap the hook so that unwrapped renders still work and
  // simply hide the "SOWs & GM" tab.
  try {
    return useAuth();
  } catch {
    return null;
  }
}

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const auth = useOptionalAuth();
  const groups = auth?.user?.groups ?? [];
  const canSeeSowGm = groups.some((g) => SOW_GM_TAB_ROLES.has(g));
  const navigate = useNavigate();
  // Fall back to id-token claims so the button gates work on the legacy
  // page even when it's rendered outside AuthProvider (e.g. the existing
  // ClientDetail vitest suite).
  const canDelete = useMemo(() => {
    if (auth?.user?.groups?.length) return userCanDelete(auth.user.groups);
    const claims = getIdTokenClaims();
    const raw = claims?.["cognito:groups"];
    return userCanDelete(Array.isArray(raw) ? (raw as string[]) : null);
  }, [auth?.user?.groups]);
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    setError(null);
    getClient(id)
      .then((c) => setClient(c))
      .catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !client) return <ErrorState error={error} retry={load} />;
  if (!client) return <EmptyState title="Loading" hint="Fetching the client." />;

  const entityCols: Column<ClientLegalEntity>[] = [
    { key: "name", header: "Legal entity", render: (e) => e.name },
    { key: "country", header: "Country", render: (e) => e.country ?? "—" },
  ];

  const opportunityCols: Column<ClientOpportunity>[] = [
    {
      key: "deal",
      header: "Deal",
      render: (o) => (
        <Link to={`/deals/${o.id}`} style={{ color: "#1d4ed8" }}>
          {o.hubspot_deal_id}
        </Link>
      ),
    },
    { key: "stage", header: "Stage", render: (o) => o.sales_stage ?? "—" },
    { key: "engagement", header: "Engagement", render: (o) => o.engagement_type ?? "—" },
    { key: "gov", header: "Governance", render: (o) => o.governance_status },
    {
      key: "next",
      header: "Next action",
      render: (o) => (
        <span>
          <div>{o.next_client_action ?? "—"}</div>
          <div style={{ color: "#6b7280", fontSize: 12 }}>{o.next_client_date ?? ""}</div>
        </span>
      ),
    },
  ];

  const activityCols: Column<ClientRecentActivity>[] = [
    { key: "ts", header: "When", render: (a) => a.ts },
    { key: "entity", header: "Entity", render: (a) => a.entity },
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
        title={client.name}
        subtitle={
          <span>
            <StatusChip tone={coverageTone(client.coverage_state)}>
              {client.coverage_state}
            </StatusChip>{" "}
            {client.hubspot_company_id ? (
              <span style={{ color: "#6b7280" }}>
                HubSpot: {client.hubspot_company_id}
              </span>
            ) : null}
            {canSeeSowGm ? (
              <>
                {" · "}
                <Link
                  to={`/clients/${client.id}/sows`}
                  style={{ color: "#1d4ed8" }}
                >
                  SOWs &amp; GM
                </Link>
              </>
            ) : null}
          </span>
        }
        right={
          canDelete ? (
            <Button
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
              data-testid="client-detail-delete-btn"
            >
              Delete client
            </Button>
          ) : null
        }
      />

      {canDelete ? (
        <DeletionConfirmationDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          kind="client"
          id={client.id}
          name={client.name}
          onConfirmed={() => {
            setDeleteOpen(false);
            navigate("/pipeline");
          }}
        />
      ) : null}

      <Panel title="Client + entities">
        <div style={{ marginBottom: 12, color: "#6b7280", fontSize: 14 }}>
          Timezone: {client.timezone ?? "—"}
        </div>
        {client.legal_entities.length === 0 ? (
          <EmptyState
            title="No legal entities"
            hint="A default entity is created on intake; add more via Legal."
          />
        ) : (
          <Table
            ariaLabel="Legal entities"
            columns={entityCols}
            rows={client.legal_entities}
          />
        )}
      </Panel>

      {client.legal_entities.map((entity) => (
        <Panel key={entity.id} title={`Agreements — ${entity.name}`}>
          <AgreementsPanel legalEntityId={entity.id} />
        </Panel>
      ))}

      <Panel title="Opportunities">
        {client.opportunities.length === 0 ? (
          <EmptyState title="No opportunities linked yet" />
        ) : (
          <Table
            ariaLabel="Opportunities"
            columns={opportunityCols}
            rows={client.opportunities}
          />
        )}
      </Panel>

      <Panel title="Recent activity">
        {client.recent_activity.length === 0 ? (
          <EmptyState title="No recent activity" />
        ) : (
          <Table
            ariaLabel="Recent activity"
            columns={activityCols}
            rows={client.recent_activity}
          />
        )}
      </Panel>
    </div>
  );
}
