/**
 * S19 slice 1 rebuild of `/pipeline`.
 *
 * Two views (Clients default, Opportunities) driven by
 * `list_clients` / `list_opportunities` / `summary` in the shared
 * hubspot_pipeline service. Every column comes from the local mirror;
 * no HubSpot call in a request path.
 *
 * Slice 1 scope: read-only. Filters land as URL search params; the
 * next-action edit panel + tracking-group filter arrive in slice 2.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  getPipelineSummary,
  getSyncStatus,
  listPipelineClients,
  listPipelineOpportunities,
  type PipelineClientRow,
  type PipelineFilters,
  type PipelineOpportunityRow,
  type PipelineSummary,
  type SyncStatusRow,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { Badge } from "../../ui-v2/primitives/badge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";

const PREF_KEY = "s19.pipeline.view";
const HUBSPOT_NEW_DEAL_URL =
  "https://app.hubspot.com/contacts/48656168/deal/new";

const ATTENTION_LABELS: Record<string, string> = {
  overdue_action: "Overdue action",
  stalled: "Stalled 14d+",
  no_owner: "No owner",
  pending_approval: "Pending approval",
  closed_won_not_released: "Closed-won · no release",
};

const SOW_STATE_LABELS: Record<string, string> = {
  none: "No SOW",
  draft: "Draft",
  in_review_delivery_hr: "In review · delivery/hr",
  in_review_finance_legal: "In review · finance/legal",
  changes_requested: "Changes requested",
  ceo_exception: "CEO exception",
  approved: "Approved",
  awaiting_signature: "Awaiting signature",
  signed: "Signed",
};

type ViewMode = "clients" | "opportunities";

function initialView(): ViewMode {
  const stored = window.localStorage.getItem(PREF_KEY);
  return stored === "opportunities" ? "opportunities" : "clients";
}

function formatMoney(amount: string | null, currency: string | null): string {
  if (amount === null) return "—";
  if (amount === "0" || amount === "0.00") return "0";
  const cur = currency || "USD";
  const num = Number(amount);
  if (Number.isNaN(num)) return amount;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 0,
    }).format(num);
  } catch {
    return `${cur} ${num.toLocaleString("en-US")}`;
  }
}

function formatCurrencyMap(
  map: Record<string, string>,
): { currency: string; formatted: string }[] {
  return Object.entries(map).map(([currency, amount]) => ({
    currency,
    formatted: formatMoney(amount, currency),
  }));
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().slice(0, 10);
}

function formatAgo(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function summariseSync(rows: SyncStatusRow[]): {
  label: string;
  lag: number | null;
  error: string | null;
} {
  if (rows.length === 0) return { label: "never", lag: null, error: null };
  const backfill = rows.find((r) => r.source === "hubspot_backfill");
  const webhook = rows.find((r) => r.source === "hubspot_webhook");
  const primary = webhook?.last_success_at ? webhook : backfill;
  const lag =
    rows
      .map((r) => r.lag_seconds ?? Number.MAX_SAFE_INTEGER)
      .reduce((a, b) => Math.min(a, b), Number.MAX_SAFE_INTEGER) ??
    Number.MAX_SAFE_INTEGER;
  const error = rows.map((r) => r.last_error).find((e) => e) ?? null;
  return {
    label: formatAgo(primary?.last_success_at ?? null),
    lag: lag === Number.MAX_SAFE_INTEGER ? null : lag,
    error,
  };
}

export function PipelinePage() {
  const [view, setView] = useState<ViewMode>(() => initialView());
  const [search, setSearch] = useState("");
  const [includeClosed, setIncludeClosed] = useState(false);
  const [selectedStages, setSelectedStages] = useState<string[]>([]);
  const [clients, setClients] = useState<PipelineClientRow[]>([]);
  const [opps, setOpps] = useState<PipelineOpportunityRow[]>([]);
  const [totalClients, setTotalClients] = useState(0);
  const [totalOpps, setTotalOpps] = useState(0);
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [sync, setSync] = useState<SyncStatusRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const navigate = useNavigate();

  const filters = useMemo<PipelineFilters>(
    () => ({
      search: search.trim() || undefined,
      stage: selectedStages.length ? selectedStages : undefined,
      include_closed: includeClosed || undefined,
      page: 1,
      page_size: 50,
    }),
    [search, selectedStages, includeClosed],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [clientRes, oppRes, summaryRes, syncRes] = await Promise.all([
        listPipelineClients(filters),
        listPipelineOpportunities(filters),
        getPipelineSummary(filters),
        getSyncStatus().catch(() => ({ items: [] as SyncStatusRow[] })),
      ]);
      setClients(clientRes.items);
      setTotalClients(clientRes.total);
      setOpps(oppRes.items);
      setTotalOpps(oppRes.total);
      setSummary(summaryRes);
      setSync(syncRes.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    window.localStorage.setItem(PREF_KEY, view);
  }, [view]);

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const opp of opps) {
      const label = opp.stage_label || "Unknown";
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [opps]);

  const syncSummary = useMemo(() => summariseSync(sync), [sync]);
  const showAmberBanner =
    (syncSummary.lag ?? 0) > 30 * 60 || syncSummary.error !== null;

  function toggleStage(stage: string) {
    setSelectedStages((prev) =>
      prev.includes(stage) ? prev.filter((s) => s !== stage) : [...prev, stage],
    );
  }

  return (
    <div>
      <PageHeader
        title="Pipeline"
        subtitle="Clients and opportunities, live from the HubSpot mirror. Every column reads the cache — no HubSpot call in the page load path."
        actions={
          <a
            href={HUBSPOT_NEW_DEAL_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2"
            data-testid="create-in-hubspot"
          >
            <Button variant="primary" asChild={false}>
              Create in HubSpot
              <ExternalLink className="ml-1 h-4 w-4" aria-hidden />
            </Button>
          </a>
        }
      />

      <div
        className="mb-4 flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface px-4 py-3 text-body"
        data-testid="sync-banner"
      >
        <span className="text-text-secondary">Synced</span>
        <span className="font-medium">{syncSummary.label}</span>
        {showAmberBanner ? (
          <span
            className="ml-2 inline-flex items-center gap-1 rounded-full bg-warn-fill px-2 py-0.5 text-secondary text-warn"
            role="status"
          >
            <AlertTriangle className="h-3 w-3" aria-hidden />
            {syncSummary.error ? "Sync error" : "Sync delayed"}
          </span>
        ) : null}
      </div>

      {summary ? (
        <div
          className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"
          data-testid="summary-bar"
        >
          <SummaryCell label="Open deals" value={summary.open_count.toString()} />
          {formatCurrencyMap(summary.open_value_by_currency).map((row) => (
            <SummaryCell
              key={row.currency}
              label={`Open value · ${row.currency}`}
              value={row.formatted}
            />
          ))}
          <SummaryCell
            label="Closing this month"
            value={summary.closing_this_month.toString()}
          />
          <SummaryCell
            label="Overdue actions"
            value={summary.overdue_actions.toString()}
          />
          <SummaryCell
            label="Pending approvals"
            value={summary.pending_approvals.toString()}
          />
          <SummaryCell
            label="Agreement gaps"
            value={summary.agreement_gaps.toString()}
          />
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          type="search"
          placeholder="Search deal or client"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="sm:w-64"
          aria-label="Search deal or client"
        />
        <label className="inline-flex items-center gap-2 text-body text-text-secondary">
          <input
            type="checkbox"
            checked={includeClosed}
            onChange={(e) => setIncludeClosed(e.target.checked)}
            aria-label="Include closed"
          />
          Include closed
        </label>
      </div>

      {stageCounts.length ? (
        <div
          className="mb-4 flex flex-wrap gap-2"
          data-testid="stage-strip"
          aria-label="Stage strip"
        >
          {stageCounts.map(([stage, count]) => (
            <button
              key={stage}
              type="button"
              onClick={() => toggleStage(stage)}
              className={`rounded-panel border border-divider px-3 py-1 text-secondary transition-colors ${
                selectedStages.includes(stage)
                  ? "bg-primary-subtle text-primary"
                  : "bg-surface text-text-secondary hover:bg-primary-subtle/50"
              }`}
            >
              <span className="font-medium">{stage}</span>
              <span className="ml-2 text-text-secondary">{count}</span>
            </button>
          ))}
        </div>
      ) : null}

      <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
        <TabsList aria-label="Pipeline view">
          <TabsTrigger value="clients">
            Clients ({totalClients.toLocaleString("en-US")})
          </TabsTrigger>
          <TabsTrigger value="opportunities">
            Opportunities ({totalOpps.toLocaleString("en-US")})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="clients">
          {loading ? (
            <PanelStatus>Loading pipeline…</PanelStatus>
          ) : error ? (
            <ErrorState
              title="We couldn't load the pipeline"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
            />
          ) : clients.length === 0 ? (
            <EmptyState
              title="No clients match this view"
              description="Adjust filters or clear search."
            />
          ) : (
            <ClientsTable
              rows={clients}
              onRow={(id) => navigate(`/clients/${id}`)}
            />
          )}
        </TabsContent>

        <TabsContent value="opportunities">
          {loading ? (
            <PanelStatus>Loading pipeline…</PanelStatus>
          ) : error ? (
            <ErrorState
              title="We couldn't load the pipeline"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
            />
          ) : opps.length === 0 ? (
            <EmptyState
              title="No opportunities match this view"
              description="Adjust filters, include closed, or clear search."
            />
          ) : (
            <OpportunitiesTable rows={opps} />
          )}
        </TabsContent>
      </Tabs>

      <div className="mt-3 text-secondary text-text-secondary">
        {view === "clients"
          ? `${totalClients.toLocaleString("en-US")} matching clients`
          : `${totalOpps.toLocaleString("en-US")} matching opportunities`}
      </div>
    </div>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-panel border border-divider bg-surface px-4 py-3">
      <div className="text-secondary text-text-secondary">{label}</div>
      <div className="mt-1 text-heading-3 text-text">{value}</div>
    </div>
  );
}

function PanelStatus({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="status"
      className="rounded-panel border border-divider p-6 text-body text-text-secondary"
    >
      {children}
    </div>
  );
}

function ClientsTable({
  rows,
  onRow,
}: {
  rows: PipelineClientRow[];
  onRow: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-panel border border-divider">
      <table
        className="w-full text-body"
        aria-label="Pipeline clients"
        data-testid="clients-table"
      >
        <thead className="bg-primary-subtle/40">
          <tr className="text-left text-secondary text-text-secondary">
            <th className="sticky left-0 z-10 bg-primary-subtle/60 px-3 py-2 font-medium">
              Client
            </th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Open</th>
            <th className="px-3 py-2 font-medium">Open value</th>
            <th className="px-3 py-2 font-medium">Agreements</th>
            <th className="px-3 py-2 font-medium">SOW</th>
            <th className="px-3 py-2 font-medium">Attention</th>
            <th className="px-3 py-2 font-medium">Last activity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.client_id}
              data-testid={`client-row-${row.client_id}`}
              className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
              onClick={() => onRow(row.client_id)}
            >
              <td className="sticky left-0 z-10 bg-surface px-3 py-3 align-top">
                <div className="text-text">{row.client_name}</div>
                {row.hubspot_company_id ? (
                  <div className="text-secondary text-text-secondary">
                    HS #{row.hubspot_company_id}
                  </div>
                ) : null}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {row.owner_name || row.owner_email || "Unassigned"}
              </td>
              <td className="px-3 py-3 align-top tnum text-text">
                {row.open_opp_count}
              </td>
              <td className="px-3 py-3 align-top text-text">
                {Object.keys(row.open_value_by_currency).length === 0
                  ? "—"
                  : formatCurrencyMap(row.open_value_by_currency).map((v) => (
                      <div key={v.currency} className="tnum">
                        {v.formatted}
                      </div>
                    ))}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                <span className={row.has_nda ? "text-success" : "text-danger"}>
                  NDA {row.has_nda ? "✓" : "–"}
                </span>
                <span className="ml-2">·</span>
                <span
                  className={`ml-2 ${row.has_msa ? "text-success" : "text-danger"}`}
                >
                  MSA {row.has_msa ? "✓" : "–"}
                </span>
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {SOW_STATE_LABELS[row.worst_sow_approval_state] ??
                  row.worst_sow_approval_state}
              </td>
              <td className="px-3 py-3 align-top">
                <AttentionBadges flags={row.attention_flags} />
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {formatAgo(row.latest_activity_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpportunitiesTable({ rows }: { rows: PipelineOpportunityRow[] }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-divider">
      <table
        className="w-full text-body"
        aria-label="Pipeline opportunities"
        data-testid="opportunities-table"
      >
        <thead className="bg-primary-subtle/40">
          <tr className="text-left text-secondary text-text-secondary">
            <th className="sticky left-0 z-10 bg-primary-subtle/60 px-3 py-2 font-medium">
              Deal
            </th>
            <th className="px-3 py-2 font-medium">Client</th>
            <th className="px-3 py-2 font-medium">Stage</th>
            <th className="px-3 py-2 font-medium">Amount</th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Close</th>
            <th className="px-3 py-2 font-medium">SOW</th>
            <th className="px-3 py-2 font-medium">Attention</th>
            <th className="px-3 py-2 font-medium">Last activity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.opportunity_id}
              data-testid={`opp-row-${row.opportunity_id}`}
              className="border-t border-divider hover:bg-primary-subtle/30"
            >
              <td className="sticky left-0 z-10 bg-surface px-3 py-3 align-top">
                <div className="text-text">
                  {row.name || `Deal ${row.hubspot_deal_id}`}
                </div>
                {row.hubspot_deal_id ? (
                  <div className="text-secondary text-text-secondary">
                    HS #{row.hubspot_deal_id}
                  </div>
                ) : null}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {row.client_name || "—"}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {row.stage_label || "—"}
              </td>
              <td className="px-3 py-3 align-top tnum text-text">
                {formatMoney(row.amount, row.currency)}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {row.owner_name || row.owner_email || "Unassigned"}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {formatDate(row.close_date)}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {SOW_STATE_LABELS[row.sow_approval_state] ?? row.sow_approval_state}
              </td>
              <td className="px-3 py-3 align-top">
                <AttentionBadges flags={row.attention_flags} />
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {formatAgo(row.hubspot_last_activity_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AttentionBadges({ flags }: { flags: string[] }) {
  if (!flags.length) return <span className="text-text-secondary">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {flags.map((flag) => (
        <Badge key={flag} tone="warning" data-testid={`flag-${flag}`}>
          {ATTENTION_LABELS[flag] ?? flag}
        </Badge>
      ))}
    </div>
  );
}
