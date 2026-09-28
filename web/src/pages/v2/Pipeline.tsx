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

import { MoreVertical } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  listClients,
  type ClientListRow,
} from "../../api/client";
import { getIdTokenClaims } from "../../auth/cognito";
import { DeletionConfirmationDialog } from "../../ui-v2/DeletionConfirmationDialog";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { Button } from "../../ui-v2/primitives/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../ui-v2/primitives/dropdown-menu";
import { Input } from "../../ui-v2/primitives/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { NewOpportunitySheet } from "./pipeline/NewOpportunitySheet";

/**
 * Roles allowed to hard-delete or archive records. Mirrors the server-side
 * `require_role` set on `api/app/routers/deletion.py`. Hiding the row-menu
 * is UX only — the server enforces the same list on every write.
 */
const DELETE_ROLES: readonly string[] = [
  "SystemAdmin",
  "CEO",
  "SalesLeader",
  "Finance",
  "Legal",
];

function currentGroups(): string[] {
  const claims = getIdTokenClaims();
  const raw = claims?.["cognito:groups"];
  return Array.isArray(raw) ? (raw as string[]) : [];
}

function userCanDelete(): boolean {
  const groups = currentGroups();
  return groups.some((g) => DELETE_ROLES.includes(g));
}

// S17: NDA/MSA is a doc store — no gap/ready/follow-up filters. The
// Pipeline just shows every client with an ownership + search filter.
type FilterKey = "all";

interface ClientRow {
  client: ClientListRow;
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

function matchesSearch(row: ClientRow, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    row.client.name.toLowerCase().includes(needle) ||
    (row.client.hubspot_company_id?.toLowerCase().includes(needle) ?? false) ||
    row.client.owners.some((o) => o.name.toLowerCase().includes(needle))
  );
}

export function PipelinePage() {
  const [clients, setClients] = useState<ClientListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ClientListRow | null>(null);
  const canDelete = useMemo(() => userCanDelete(), []);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const clientRes = await listClients({ size: 200 });
      setClients(clientRes.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await load();
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const rows = useMemo<ClientRow[]>(
    () => clients.map((c) => ({ client: c })),
    [clients],
  );
  const filtered = useMemo(
    () => rows.filter((r) => matchesSearch(r, query)),
    [rows, query],
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

  const emptyReason: string = query ? "No clients match this search." : "No clients yet.";

  return (
    <div>
      <PageHeader
        title="Pipeline clients"
        subtitle="Owners, commercial stage and the next client action. NDA/MSA lives on the Agreements page."
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
                    <th className="px-3 py-2 font-medium">SOWs</th>
                    <th className="px-3 py-2 font-medium">Next client action</th>
                    {canDelete ? (
                      <th className="px-3 py-2 font-medium">
                        <span className="sr-only">Row actions</span>
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(({ client }) => (
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
                      <td className="px-3 py-3 align-top tnum text-text">
                        {client.opportunity_count}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        Set from client workspace
                      </td>
                      {canDelete ? (
                        <td
                          className="px-3 py-3 align-top text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={`Actions for ${client.name}`}
                                data-testid={`row-menu-${client.id}`}
                              >
                                <MoreVertical
                                  className="h-4 w-4"
                                  aria-hidden
                                />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onSelect={() => setDeleteTarget(client)}
                                data-testid={`row-delete-${client.id}`}
                                className="text-danger"
                              >
                                Delete…
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      ) : null}
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

      {deleteTarget ? (
        <DeletionConfirmationDialog
          open={deleteTarget !== null}
          onOpenChange={(o) => {
            if (!o) setDeleteTarget(null);
          }}
          kind="client"
          id={deleteTarget.id}
          name={deleteTarget.name}
          onConfirmed={() => {
            setDeleteTarget(null);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}
