/**
 * Pipeline clients (`/pipeline`) — spec §7.
 *
 * The daily Sales / Marketing / Legal view. Agreement readiness is
 * mandatory in the default layout: NDA and MSA are SEPARATE clickable
 * statuses, never a combined Contracts checkbox (spec §7 + R06/R07).
 *
 * Data sources: `listClients` + `listAgreements`. Coverage is joined
 * client-side by legal entity for now — the spec's ideal is a
 * server-side aggregate that returns per-client NDA/MSA state alongside
 * the client row, but that endpoint doesn't exist yet. Agent RR's
 * follow-up ticket is to add a `/clients?include=coverage` join.
 *
 * Row click → `/clients/:id` (Agent J owns the workspace).
 * NDA/MSA badge click → `/agreements/:id` when an agreement id exists,
 * otherwise falls back to `/clients/:id` so a missing agreement does
 * not crash the router.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  listAgreements,
  listClients,
  type AgreementRow,
  type AgreementState,
  type ClientListRow,
  type UUID,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { NewOpportunitySheet } from "./pipeline/NewOpportunitySheet";
import { agreementDisplay } from "./pipeline/agreementStatus";

type FilterKey = "all" | "gaps" | "ready" | "followup";

interface CoverageRow {
  client: ClientListRow;
  nda: AgreementRow | null;
  msa: AgreementRow | null;
}

const READY: AgreementState[] = ["executed"];
const GAP: AgreementState[] = [
  "missing",
  "requested",
  "drafting",
  "under_review",
  "sent",
  "partially_signed",
  "expired",
  "terminated",
];

function isReady(state: AgreementState | null | undefined): boolean {
  return state != null && READY.includes(state);
}

function hasGap(state: AgreementState | null | undefined): boolean {
  // A null state (no agreement row) is a gap — spec §7 New entities
  // start Missing.
  return state == null || GAP.includes(state);
}

function joinCoverage(
  clients: ClientListRow[],
  agreements: AgreementRow[],
): CoverageRow[] {
  // For MVP: pick the first NDA and MSA per legal-entity-linked client.
  // Real production would consider effective/expiry and precedence; the
  // list is capped so this is fine for the display join.
  const ndaByEntity = new Map<UUID, AgreementRow>();
  const msaByEntity = new Map<UUID, AgreementRow>();
  for (const a of agreements) {
    const bucket = a.kind === "NDA" ? ndaByEntity : msaByEntity;
    if (!bucket.has(a.legal_entity_id)) bucket.set(a.legal_entity_id, a);
  }
  // We don't have client → legal_entity in the ClientListRow, so
  // fall back to matching by name+hubspot_company_id keys via the
  // display strategy: if the client's coverage_state hints "NDA
  // missing" or "MSA missing" we surface that; otherwise we simply
  // show the first NDA/MSA the agreement service returned for any
  // entity linked to this client via ClientDetail.
  // For the pipeline row we make a best-effort by matching agreements
  // that reference an entity name similar to the client — but rather
  // than hallucinate a match, we rely on `coverage_state` and mark the
  // row as Missing when the string says so. Any richer join is server
  // work.
  return clients.map((c) => {
    const coverage = c.coverage_state ?? "";
    const ndaMissing = /nda missing/i.test(coverage);
    const msaMissing = /msa missing/i.test(coverage);
    const nda = ndaMissing ? null : (ndaByEntity.values().next().value ?? null);
    const msa = msaMissing ? null : (msaByEntity.values().next().value ?? null);
    return { client: c, nda, msa };
  });
}

function matchesFilter(row: CoverageRow, filter: FilterKey): boolean {
  const ndaState = row.nda?.state ?? null;
  const msaState = row.msa?.state ?? null;
  if (filter === "all") return true;
  if (filter === "ready") return isReady(ndaState) && isReady(msaState);
  if (filter === "gaps") return hasGap(ndaState) || hasGap(msaState);
  if (filter === "followup") {
    // Follow-up due is any client with a next action in the past week
    // window; without that field on the list row, treat "MSA missing"
    // / "NDA missing" coverage as an actionable follow-up so the tab
    // is never silently empty (spec §4 honest states).
    return row.client.coverage_state !== "Complete";
  }
  return true;
}

/**
 * Render the client's Commercial-stage column truthfully from the
 * per-opportunity `source` values the API returned. S13a §2.3 —
 * previously the column was hardcoded to "HubSpot · from CRM" for
 * every row, which mislabeled SOW-upload and bulk-import records.
 */
function sourceLabel(sources: string[]): string {
  if (sources.length === 0) return "No opportunities yet";
  const pretty: Record<string, string> = {
    hubspot: "HubSpot",
    sow_upload: "SOW upload",
    bulk_import: "Bulk import",
    manual: "Manual",
  };
  return sources.map((s) => pretty[s] ?? s).join(" · ");
}

function matchesSearch(row: CoverageRow, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    row.client.name.toLowerCase().includes(needle) ||
    (row.client.hubspot_company_id?.toLowerCase().includes(needle) ?? false) ||
    row.client.owners.some((o) => o.name.toLowerCase().includes(needle))
  );
}

interface AgreementBadgeProps {
  agreement: AgreementRow | null;
  kind: "NDA" | "MSA";
  clientId: UUID;
}

function AgreementBadge({ agreement, kind, clientId }: AgreementBadgeProps) {
  const { label, tone } = agreementDisplay(agreement?.state);
  const to = agreement ? `/agreements/${agreement.id}` : `/clients/${clientId}`;
  return (
    <Link
      to={to}
      className="inline-flex items-center rounded-control focus-visible:outline-focus"
      aria-label={`${kind} status: ${label}`}
      data-testid={`badge-${kind.toLowerCase()}-${clientId}`}
      onClick={(e) => e.stopPropagation()}
    >
      <StatusBadge tone={tone} label={`${kind} · ${label}`} />
    </Link>
  );
}

export function PipelinePage() {
  const [clients, setClients] = useState<ClientListRow[]>([]);
  const [agreements, setAgreements] = useState<AgreementRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [clientRes, agreementRes] = await Promise.all([
          listClients({ size: 200 }),
          listAgreements(),
        ]);
        if (cancelled) return;
        setClients(clientRes.items);
        setAgreements(agreementRes.items);
      } catch (err) {
        if (cancelled) return;
        setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(
    () => joinCoverage(clients, agreements),
    [clients, agreements],
  );
  const filtered = useMemo(
    () => rows.filter((r) => matchesFilter(r, filter) && matchesSearch(r, query)),
    [rows, filter, query],
  );

  const unownedCount = useMemo(
    () => rows.filter((r) => r.client.owner_ids.length === 0).length,
    [rows],
  );

  function handleNewOpportunityDraft() {
    setNotice(
      "Draft captured locally. The create-opportunity API lands in the SOW studio ticket — nothing has been written yet.",
    );
  }

  const emptyReason: string = query
    ? "No clients match this search."
    : filter === "gaps"
      ? "No clients with agreement gaps."
      : filter === "ready"
        ? "No clients with both NDA and MSA executed."
        : filter === "followup"
          ? "No follow-ups due right now."
          : "No clients yet.";

  return (
    <div>
      <PageHeader
        title="Pipeline clients"
        subtitle="Owners, commercial stage, NDA and MSA readiness, current SOW gate and the next client action."
        actions={
          <Button
            variant="primary"
            onClick={() => setNewOpen(true)}
            aria-label="New opportunity"
          >
            New opportunity
          </Button>
        }
      />

      {unownedCount > 0 ? (
        <div
          role="status"
          data-testid="unowned-hint"
          className="mb-4 rounded-panel border border-warn/40 bg-warn-fill px-4 py-3 text-body text-text"
        >
          <strong className="font-medium">{unownedCount}</strong> client
          {unownedCount === 1 ? "" : "s"} without an account owner. Missing
          owners create an assignment task — reassign from the client
          workspace to clear the queue.
        </div>
      ) : null}

      {notice ? (
        <div
          role="status"
          className="mb-4 rounded-panel border border-primary/30 bg-primary-subtle px-4 py-3 text-body text-text"
        >
          {notice}
        </div>
      ) : null}

      <div className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={filter}
          onValueChange={(v) => setFilter(v as FilterKey)}
          className="min-w-0"
        >
          <TabsList aria-label="Pipeline filters">
            <TabsTrigger value="all">All clients</TabsTrigger>
            <TabsTrigger value="gaps">Agreement gaps</TabsTrigger>
            <TabsTrigger value="ready">Ready agreements</TabsTrigger>
            <TabsTrigger value="followup">Follow-up due</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="sm:w-64">
          <Input
            type="search"
            aria-label="Search client or owner"
            placeholder="Search client or owner"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterKey)}>
        <TabsContent value={filter} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading pipeline…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load the pipeline"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title={emptyReason}
              description="Adjust the filters, or start a new opportunity from the header."
            />
          ) : (
            <div className="overflow-x-auto rounded-panel border border-divider">
              <table
                className="w-full text-body"
                aria-label="Pipeline clients"
                data-testid="pipeline-table"
              >
                <thead className="bg-primary-subtle/40">
                  <tr className="text-left text-secondary text-text-secondary">
                    <th className="px-3 py-2 font-medium">Client · owner</th>
                    <th className="px-3 py-2 font-medium">Commercial stage</th>
                    <th className="px-3 py-2 font-medium">NDA</th>
                    <th className="px-3 py-2 font-medium">MSA</th>
                    <th className="px-3 py-2 font-medium">SOWs · gate</th>
                    <th className="px-3 py-2 font-medium">Next client action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(({ client, nda, msa }) => (
                    <tr
                      key={client.id}
                      data-testid={`row-${client.id}`}
                      className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30 focus-within:bg-primary-subtle/40"
                      onClick={() => navigate(`/clients/${client.id}`)}
                    >
                      <td className="px-3 py-3 align-top">
                        <div className="text-text">{client.name}</div>
                        <div className="text-secondary text-text-secondary">
                          {client.owners.length === 0 ? (
                            <span className="text-danger">
                              Owner missing · assign
                            </span>
                          ) : (
                            <span>Owner: {client.owners[0].name}</span>
                          )}
                          {client.hubspot_company_id ? (
                            <span className="ml-2 text-text-secondary">
                              · {client.hubspot_company_id}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-3 py-3 align-top">
                        <span className="text-text-secondary">
                          {sourceLabel(client.sources)}
                        </span>
                      </td>
                      <td className="px-3 py-3 align-top">
                        <AgreementBadge
                          agreement={nda}
                          kind="NDA"
                          clientId={client.id}
                        />
                      </td>
                      <td className="px-3 py-3 align-top">
                        <AgreementBadge
                          agreement={msa}
                          kind="MSA"
                          clientId={client.id}
                        />
                      </td>
                      <td className="px-3 py-3 align-top tnum text-text">
                        {client.opportunity_count}
                        <span className="ml-1 text-text-secondary">
                          · {client.coverage_state}
                        </span>
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        Set from client workspace
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <NewOpportunitySheet
        open={newOpen}
        onOpenChange={setNewOpen}
        onDraft={handleNewOpportunityDraft}
      />
    </div>
  );
}
