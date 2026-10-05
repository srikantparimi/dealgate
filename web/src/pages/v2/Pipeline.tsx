/**
 * S20 · W2 · Pipeline (L02-L08).
 *
 * Two views (Clients default, Opportunities). Every list column reads the
 * cache — no HubSpot call in a request path.
 *
 * Contract obligations landed here:
 * - **L02** — Stage chips filter IN PLACE by toggling `stage=<id>` on
 *   the URL. Chips render zero-count stages too (D9). "Clear filters"
 *   shows when any chip is active.
 * - **L03** — 25/50/100 pagination. `meta.total` from the API is
 *   computed over the full authorized filter set BEFORE pagination
 *   (A5, T35). Prev/next controls; changing filters resets to page 1;
 *   Back restores filters + page + scroll (URL state).
 * - **L04** — Deal identity column shows the actual deal name (from
 *   `opportunity.name` once W1 lands the migration; fallback to
 *   `stage_label` in the meantime). BU column + pipeline context tag.
 * - **L05** — Client rows show account owner (D2) as a separate
 *   concept from deal owner. Matching-vs-total open deals rendered.
 * - **L06** — Stage chips reconcile with matching-deal totals; zero
 *   stages rendered; unknown-stage bucket visible.
 * - **L07** — Closed Lost rows carry a plain "Closed Lost" pill; no
 *   numeric stage/UUID owner as label.
 * - **L08** — no engineering copy ("mirror", "cache", "page-load
 *   path" out); "Last synced", "Data delayed" in.
 *
 * URL is the source of truth (contracts §4). `useSearchParams` is the
 * canonical read/write path. localStorage is a landing fallback only
 * when the URL is empty.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Download, ExternalLink, X } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  downloadPipelineCsv,
  getPipelineFacets,
  getPipelineSummary,
  getSyncStatus,
  getUserPreference,
  listPipelineClients,
  listPipelineOpportunities,
  listSavedViews,
  listTrackingGroups,
  putUserPreference,
  type PipelineClientRow,
  type PipelineFacets,
  type PipelineFilters,
  type PipelineOpportunityRow,
  type PipelineListPage,
  type PipelineStageCount,
  type PipelineSummary,
  type SavedView,
  type SyncStatusRow,
  type TrackingGroup,
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

const PREF_KEY_VIEW = "s19.pipeline.view";
// S20 W6 Session 4b item 6 · last applied saved-view, per-user per-tab.
const PREF_KEY_LAST_VIEW = "s20.pipeline.lastSavedView";
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

const OPEN_CLOSED_LABELS: Record<string, string> = {
  open: "Open",
  closed_won: "Closed Won",
  closed_lost: "Closed Lost",
  any: "Any",
};

const DATE_PRESET_LABELS: Record<string, string> = {
  last7: "Last 7 days",
  last30: "Last 30 days",
  last90: "Last 90 days",
  next7: "Next 7 days",
  next30: "Next 30 days",
  next90: "Next 90 days",
  this_month: "This month",
  this_quarter: "This quarter",
  custom: "Custom",
};

const DATE_FIELD_LABELS: Record<string, string> = {
  created: "Created",
  close: "Close date",
  last_activity: "Last activity",
  last_contacted: "Last contacted",
  action_due: "Action due",
};

const MISSING_LABELS: Record<string, string> = {
  owner: "Missing: owner",
  stage: "Missing: stage",
  close_date: "Missing: close date",
  amount: "Missing: amount",
  business_unit: "Missing: BU",
  next_action: "Missing: next action",
};

type ViewMode = "clients" | "opportunities";

const PAGE_SIZES = [25, 50, 100] as const;
type PageSize = (typeof PAGE_SIZES)[number];

function isPageSize(n: number): n is PageSize {
  return (PAGE_SIZES as readonly number[]).includes(n);
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
  if (!iso) return "no recorded activity";
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
  if (rows.length === 0) return { label: "no recorded sync", lag: null, error: null };
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

// ---------------------------------------------------------------------------
// URL-state hooks: filters, page, page_size, sort, view live on the URL.
// Explicit URL beats localStorage (contracts §4). We keep a scroll restore
// cache keyed by the exact URL so Back returns to the same spot.
// ---------------------------------------------------------------------------

function savedViewFilters(view: SavedView): Partial<PipelineFilters> {
  const filters = { ...view.filter_json } as Partial<PipelineFilters>;
  const sort = view.sort_json;
  if (sort && typeof sort === "object" && "column" in sort && typeof sort.column === "string") {
    filters.sort = `${"descending" in sort && sort.descending === true ? "-" : ""}${sort.column}`;
  }
  return filters;
}

function readFiltersFromURL(sp: URLSearchParams): PipelineFilters & {
  page: number;
  page_size: PageSize;
  show_clients_without_matches?: boolean;
} {
  const size = Number(sp.get("page_size") || "25");
  const page_size: PageSize = isPageSize(size) ? size : 25;
  const page = Math.max(1, Number(sp.get("page") || "1"));
  return {
    search: sp.get("search") || undefined,
    pipeline: sp.get("pipeline") || undefined,
    stage: sp.getAll("stage"),
    owner: sp.getAll("owner"),
    account_owner: sp.getAll("account_owner"),
    business_unit: sp.getAll("business_unit"),
    client: sp.getAll("client"),
    readiness: sp.getAll("readiness"),
    attention: sp.getAll("attention"),
    missing: sp.getAll("missing"),
    date_field: (sp.get("date_field") as PipelineFilters["date_field"]) || undefined,
    date_from: sp.get("date_from") || undefined,
    date_to: sp.get("date_to") || undefined,
    date_preset: (sp.get("date_preset") as PipelineFilters["date_preset"]) || undefined,
    open_closed: (sp.get("open_closed") as PipelineFilters["open_closed"]) || undefined,
    include_closed: sp.get("include_closed") === "true" || undefined,
    group: sp.getAll("group"),
    watching: sp.get("watching") === "true" || undefined,
    show_clients_without_matches: sp.get("show_clients_without_matches") === "true" || undefined,
    page,
    page_size,
    sort: sp.get("sort") || undefined,
  };
}

function writeFiltersToURL(
  filters: PipelineFilters & { page: number; page_size: PageSize; show_clients_without_matches?: boolean },
  view: ViewMode,
): URLSearchParams {
  const p = new URLSearchParams();
  if (view !== "clients") p.set("view", view);
  if (filters.search) p.set("search", filters.search);
  if (filters.pipeline) p.set("pipeline", filters.pipeline);
  filters.stage?.forEach((s) => p.append("stage", s));
  filters.owner?.forEach((o) => p.append("owner", o));
  filters.account_owner?.forEach((o) => p.append("account_owner", o));
  filters.business_unit?.forEach((b) => p.append("business_unit", b));
  filters.client?.forEach((c) => p.append("client", c));
  filters.readiness?.forEach((r) => p.append("readiness", r));
  filters.attention?.forEach((a) => p.append("attention", a));
  filters.missing?.forEach((m) => p.append("missing", m));
  if (filters.date_field) p.set("date_field", filters.date_field);
  if (filters.date_from) p.set("date_from", filters.date_from);
  if (filters.date_to) p.set("date_to", filters.date_to);
  if (filters.date_preset) p.set("date_preset", filters.date_preset);
  if (filters.open_closed) p.set("open_closed", filters.open_closed);
  if (filters.include_closed) p.set("include_closed", "true");
  filters.group?.forEach((g) => p.append("group", g));
  if (filters.watching) p.set("watching", "true");
  if (filters.show_clients_without_matches) p.set("show_clients_without_matches", "true");
  if (filters.page && filters.page > 1) p.set("page", String(filters.page));
  if (filters.page_size !== 25) p.set("page_size", String(filters.page_size));
  if (filters.sort) p.set("sort", filters.sort);
  return p;
}

function countActiveFilters(f: PipelineFilters): number {
  let n = 0;
  if (f.search) n++;
  if (f.pipeline) n++;
  if (f.stage?.length) n++;
  if (f.owner?.length) n++;
  if (f.account_owner?.length) n++;
  if (f.business_unit?.length) n++;
  if (f.readiness?.length) n++;
  if (f.attention?.length) n++;
  if (f.missing?.length) n++;
  if (f.open_closed) n++;
  if (f.date_field && (f.date_from || f.date_to || f.date_preset)) n++;
  if (f.group?.length) n++;
  if (f.watching) n++;
  return n;
}

// ---------------------------------------------------------------------------

export function PipelinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setViewInternal] = useState<ViewMode>(() => {
    const q = searchParams.get("view");
    if (q === "opportunities" || q === "clients") return q;
    const stored = window.localStorage.getItem(PREF_KEY_VIEW);
    return stored === "opportunities" ? "opportunities" : "clients";
  });

  const filters = useMemo(() => readFiltersFromURL(searchParams), [searchParams]);
  const latestURL = useRef(searchParams.toString());
  latestURL.current = searchParams.toString();
  const requestVersion = useRef(0);
  const activeFilterCount = useMemo(() => countActiveFilters(filters), [filters]);

  const [clientsPage, setClientsPage] = useState<PipelineListPage<PipelineClientRow> | null>(null);
  const [oppsPage, setOppsPage] = useState<PipelineListPage<PipelineOpportunityRow> | null>(null);
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [sync, setSync] = useState<SyncStatusRow[]>([]);
  const [facets, setFacets] = useState<PipelineFacets>({ owners: [], business_units: [] });
  const [groups, setGroups] = useState<TrackingGroup[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [watchCount, setWatchCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const navigate = useNavigate();

  const exportCsv = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await downloadPipelineCsv(filters);
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "pipeline.csv";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch (cause) {
      setExportError(cause instanceof Error ? cause.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  // Saved-view navigation is independent of the active query.
  useEffect(() => {
    const initialURL = searchParams.toString();
    listTrackingGroups({ member_kind: "opportunity" })
      .then((r) => setGroups(r.items))
      .catch(() => setGroups([]));
    listSavedViews()
      .then(async (r) => {
        setSavedViews(r.items);
        // S4 Item 6 moved to user_preference backing (S5 item 0a):
        // read per-user via the server; fall back to localStorage so
        // a browser that already stored a view keeps working on first
        // login after the migration.
        const hasExplicitFilter =
          searchParams.toString().replace(/^view=\w+&?/, "") !== "";
        const pref =
          (await getUserPreference<{ view_id: string }>(
            PREF_KEY_LAST_VIEW,
          )) ?? null;
        const lastKey =
          pref?.view_id ?? window.localStorage.getItem(PREF_KEY_LAST_VIEW);
        if (!hasExplicitFilter && lastKey && latestURL.current === initialURL) {
          const v = r.items.find((it) => it.id === lastKey);
          if (v) {
            const sp = new URLSearchParams();
            for (const [k, val] of Object.entries(savedViewFilters(v))) {
              if (Array.isArray(val)) val.forEach((x) => sp.append(k, String(x)));
              else if (val != null && val !== false) sp.set(k, String(val));
            }
            setSearchParams(sp, { replace: true });
          }
        }
      })
      .catch(() => setSavedViews([]));
  }, []);

  // Local UI-only echo of search + open_closed so typing doesn't rebuild
  // the URL on every keystroke. Committed to URL on blur / Enter.
  const [searchDraft, setSearchDraft] = useState<string>(filters.search ?? "");
  useEffect(() => {
    setSearchDraft(filters.search ?? "");
  }, [filters.search]);

  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    setWatchCount(null);
    try {
      const opportunities = listPipelineOpportunities(filters);
      // Reuse the selected population when Watching is already active.
      const watched = filters.watching ? opportunities : listPipelineOpportunities({
        ...filters, watching: true, page: 1, page_size: 25,
      });
      const [clientRes, oppRes, summaryRes, syncRes, facetsRes, watchedRes] = await Promise.all([
        listPipelineClients(filters),
        opportunities,
        getPipelineSummary(filters),
        getSyncStatus().catch(() => ({ items: [] as SyncStatusRow[] })),
        getPipelineFacets(filters),
        watched,
      ]);
      if (version !== requestVersion.current) return;
      setClientsPage(clientRes);
      setOppsPage(oppRes);
      setSummary(summaryRes);
      setSync(syncRes.items);
      setFacets(facetsRes);
      setWatchCount(watchedRes.total);
    } catch (err) {
      if (version === requestVersion.current) setError(err);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
    return () => { requestVersion.current++; };
  }, [load]);

  useEffect(() => {
    setViewInternal(searchParams.get("view") === "opportunities" ? "opportunities" : "clients");
  }, [searchParams]);

  // Persist view choice so a fresh landing without any URL state remembers
  // it, but never override an explicit `?view=…` URL (contracts §4).
  const setView = useCallback(
    (next: ViewMode) => {
      setViewInternal(next);
      window.localStorage.setItem(PREF_KEY_VIEW, next);
      const p = new URLSearchParams(searchParams);
      p.set("view", next);
      setSearchParams(p);
    },
    [searchParams, setSearchParams],
  );

  const commitFilters = useCallback(
    (
      updater: (
        prev: PipelineFilters & { page: number; page_size: PageSize },
      ) => PipelineFilters & { page: number; page_size: PageSize },
      { resetPage = true }: { resetPage?: boolean } = {},
    ) => {
      const next = updater(filters);
      if (resetPage) next.page = 1;
      const params = writeFiltersToURL(next, view);
      setSearchParams(params);
    },
    [filters, view, setSearchParams],
  );

  const oppRows: PipelineOpportunityRow[] = oppsPage?.items ?? [];
  const clientRows: PipelineClientRow[] = clientsPage?.items ?? [];
  const totalOpps = oppsPage?.total ?? 0;
  const totalClients = clientsPage?.total ?? 0;
  // Stage chips come from the meta payload — computed over the FULL
  // authorized filter set (A5). Never derived from `rows` (that would
  // silently make chips a page-scoped view).
  const stageCounts: PipelineStageCount[] =
    oppsPage?.meta?.stage_counts ?? clientsPage?.meta?.stage_counts ?? [];
  const unknownBucket =
    oppsPage?.meta?.unknown_bucket ?? clientsPage?.meta?.unknown_bucket ?? 0;
  const freshness = oppsPage?.meta?.freshness ?? clientsPage?.meta?.freshness;
  const businessTz = oppsPage?.meta?.business_timezone ?? "America/Los_Angeles";

  const syncSummary = useMemo(() => summariseSync(sync), [sync]);
  const showAmberBanner =
    (syncSummary.lag ?? 0) > 30 * 60 ||
    syncSummary.error !== null ||
    freshness?.state === "Stale" ||
    freshness?.state === "Failed";

  function toggleStage(stageId: string | null) {
    if (!stageId) return;
    commitFilters((prev) => {
      const s = new Set(prev.stage || []);
      if (s.has(stageId)) s.delete(stageId);
      else s.add(stageId);
      return { ...prev, stage: Array.from(s) };
    });
  }

  function clearFilters() {
    commitFilters(() => ({
      page: 1,
      page_size: filters.page_size,
    }));
  }

  function commitSearch() {
    commitFilters((prev) => ({
      ...prev,
      search: searchDraft.trim() || undefined,
    }));
  }

  function setPage(next: number) {
    commitFilters((prev) => ({ ...prev, page: next }), { resetPage: false });
  }

  function setPageSize(size: PageSize) {
    commitFilters((prev) => ({ ...prev, page_size: size }));
  }

  function setOpenClosed(v: PipelineFilters["open_closed"]) {
    commitFilters((prev) => ({ ...prev, open_closed: v }));
  }

  const chipLabels: Record<string, string> = {
    search: "Search", pipeline: "Pipeline", stage: "Stage", owner: "Owner",
    account_owner: "Account owner", business_unit: "BU", readiness: "SOW",
    attention: "Attention", missing: "Missing", open_closed: "Status",
    date_field: "Date field", date_from: "From", date_to: "To", date_preset: "Date",
    group: "Group", watching: "Watching", include_closed: "Include closed",
  };
  const activeChips = Array.from(searchParams.entries()).filter(([key]) => key in chipLabels);
  function chipValue(key: string, value: string) {
    if (key === "owner") return facets.owners.find(o => o.id === value)?.name ?? "Unavailable owner";
    if (key === "stage") return stageCounts.find(s => s.stage_id === value)?.stage_label ?? "Unavailable stage";
    if (key === "group") return groups.find(g => g.id === value)?.name ?? "Unavailable group";
    if (key === "open_closed") return OPEN_CLOSED_LABELS[value] ?? value;
    if (key === "readiness") return SOW_STATE_LABELS[value] ?? value;
    if (key === "attention") return ATTENTION_LABELS[value] ?? value;
    if (key === "date_field") return DATE_FIELD_LABELS[value] ?? value;
    if (key === "date_preset") return DATE_PRESET_LABELS[value] ?? value;
    return value;
  }

  return (
    <div>
      <PageHeader
        title="Pipeline"
        subtitle="Clients and opportunities"
        actions={
          <>
          <Button variant="secondary" size="icon" title="Export filtered CSV"
            aria-label="Export filtered CSV" disabled={exporting || loading}
            onClick={exportCsv}>
            <Download className="h-4 w-4" aria-hidden />
          </Button>
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
          </>
        }
      />
      {exportError && <p role="alert" className="mb-4 text-danger">{exportError}</p>}

      <div
        className="mb-4 flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface px-4 py-3 text-body"
        data-testid="sync-banner"
      >
        <span className="text-text-secondary">Last synced</span>
        <span className="font-medium">{syncSummary.label}</span>
        {showAmberBanner ? (
          <span
            className="ml-2 inline-flex items-center gap-1 rounded-full bg-warn-fill px-2 py-0.5 text-secondary text-warn"
            role="status"
          >
            <AlertTriangle className="h-3 w-3" aria-hidden />
            {syncSummary.error
              ? "Sync error"
              : freshness?.state === "Failed"
                ? "Data unavailable"
                : "Data delayed"}
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

      <FilterBar
        filters={filters}
        activeCount={activeFilterCount}
        searchDraft={searchDraft}
        setSearchDraft={setSearchDraft}
        commitSearch={commitSearch}
        clear={clearFilters}
        setOpenClosed={setOpenClosed}
        commitFilters={commitFilters}
        businessTz={businessTz}
        facets={facets}
        groups={groups}
        savedViews={savedViews}
        watchCount={watchCount}
      />

      {view === "clients" && <label className="mb-3 flex items-center gap-2 text-secondary">
        <input type="checkbox" checked={filters.show_clients_without_matches === true}
          onChange={event => commitFilters(previous => ({ ...previous, show_clients_without_matches: event.target.checked || undefined }))} />
        Show clients with no match
      </label>}

      {activeChips.length > 0 && <div className="mb-4 flex flex-wrap gap-2" aria-label="Active filters">
        {activeChips.map(([key, value]) => {
          const label = `${chipLabels[key]}: ${chipValue(key, value)}`;
          return <button type="button" key={`${key}:${value}`} aria-label={`Remove ${label}`}
            className="inline-flex items-center gap-2 border border-divider px-2 py-1 text-secondary"
            onClick={() => {
              const next = new URLSearchParams(searchParams);
              const remaining = next.getAll(key).filter(item => item !== value);
              next.delete(key);
              remaining.forEach(item => next.append(key, item));
              next.delete("page");
              setSearchParams(next);
            }}>{label}<X className="h-3 w-3" aria-hidden /></button>;
        })}
      </div>}

      {stageCounts.length ? (
        <div
          className="mb-4 flex flex-wrap gap-2"
          data-testid="stage-strip"
          aria-label="Stage strip"
        >
          {stageCounts.map((sc) => {
            const active = filters.stage?.includes(sc.stage_id || "") ?? false;
            const tone = sc.is_closed_lost
              ? "border-danger text-danger"
              : sc.is_closed_won
                ? "border-success text-success"
                : "border-divider text-text-secondary";
            // S3b Rev-2 · chip value: sum across currencies rendered as
            // "$X · €Y" so leaders see both count + value at a glance.
            const valueLines = sc.open_value_by_currency
              ? formatCurrencyMap(sc.open_value_by_currency)
              : [];
            return (
              <button
                key={`${sc.pipeline_id}:${sc.stage_id}`}
                type="button"
                onClick={() => toggleStage(sc.stage_id)}
                className={`flex flex-col items-start rounded-panel border px-3 py-1 text-secondary transition-colors ${
                  active ? "bg-primary-subtle text-primary" : `bg-surface ${tone}`
                }`}
                data-testid={`stage-chip-${sc.stage_id}`}
              >
                <span>
                  <span className="font-medium">
                    {sc.stage_label || "Unknown stage"}
                  </span>
                  <span
                    className="ml-2 text-text-secondary"
                    data-testid={`stage-chip-count-${sc.stage_id}`}
                  >
                    {sc.count}
                  </span>
                </span>
                {valueLines.length > 0 ? (
                  <span
                    className="text-[10px] text-text-secondary tnum"
                    data-testid={`stage-chip-value-${sc.stage_id}`}
                  >
                    {valueLines.map((v) => v.formatted).join(" · ")}
                  </span>
                ) : null}
              </button>
            );
          })}
          {unknownBucket > 0 ? (
            <span
              className="rounded-panel border border-divider bg-surface px-3 py-1 text-secondary text-text-secondary"
              data-testid="stage-chip-unknown"
            >
              Unknown stage · {unknownBucket}
            </span>
          ) : null}
        </div>
      ) : null}

      {/* S20 W6 Session 4b item 5 · "why is this here" — explain the
        * active scope (group / view / watching) in prose so a user can
        * see why these specific rows are in view. */}
      {(filters.group?.length || filters.watching) ? (
        <div
          className="mb-3 rounded-panel border border-primary/40 bg-primary-subtle/40 px-3 py-2 text-body text-text"
          data-testid="scope-explainer"
        >
          <span className="font-medium">Why these rows: </span>
          {filters.group?.length
            ? (() => {
                const g = groups.find((x) => x.id === filters.group![0]);
                if (!g) return "scoped to a group.";
                if (g.filter_json) {
                  const preds = Object.entries(g.filter_json)
                    .filter(([, v]) => v != null && v !== false)
                    .map(([k, v]) => `${k} = ${JSON.stringify(v)}`);
                  return (
                    <>
                      rule-based group <b>{g.name}</b> matches rows where{" "}
                      {preds.join(" AND ")}.
                    </>
                  );
                }
                return (
                  <>
                    manual group <b>{g.name}</b> (members added by hand).
                  </>
                );
              })()
            : "scoped to deals + clients you've starred (Watching)."}
        </div>
      ) : null}

      <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
        <TabsList aria-label="Pipeline view">
          <TabsTrigger value="clients">
            Clients ({totalClients.toLocaleString("en-US")} matching)
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
          ) : clientRows.length === 0 ? (
            <EmptyState
              title="No clients match this view"
              description="Adjust filters or clear search."
            />
          ) : (
            <ClientsTable
              rows={clientRows}
              onRow={(id) => navigate(`/clients/${id}`)}
            />
          )}
          <Paginator
            page={filters.page}
            pageSize={filters.page_size}
            total={totalClients}
            setPage={setPage}
            setPageSize={setPageSize}
          />
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
          ) : oppRows.length === 0 ? (
            <EmptyState
              title="No opportunities match this view"
              description="Adjust filters or clear search."
            />
          ) : (
            <OpportunitiesTable
              rows={oppRows}
              onRow={(id) => navigate(`/deals/${id}`)}
            />
          )}
          <Paginator
            page={filters.page}
            pageSize={filters.page_size}
            total={totalOpps}
            setPage={setPage}
            setPageSize={setPageSize}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FilterBar — full filter surface per contracts §4.
// ---------------------------------------------------------------------------

function FilterBar({
  filters,
  activeCount,
  searchDraft,
  setSearchDraft,
  commitSearch,
  clear,
  setOpenClosed,
  commitFilters,
  businessTz,
  facets,
  groups,
  savedViews,
  watchCount,
}: {
  filters: PipelineFilters & { page: number; page_size: PageSize };
  activeCount: number;
  searchDraft: string;
  setSearchDraft: (v: string) => void;
  commitSearch: () => void;
  clear: () => void;
  setOpenClosed: (v: PipelineFilters["open_closed"]) => void;
  facets: PipelineFacets;
  groups: TrackingGroup[];
  savedViews: SavedView[];
  watchCount: number | null;
  commitFilters: (
    updater: (
      prev: PipelineFilters & { page: number; page_size: PageSize },
    ) => PipelineFilters & { page: number; page_size: PageSize },
  ) => void;
  businessTz: string;
}) {
  return (
    <div
      className="mb-4 flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface p-3"
      data-testid="filter-bar"
    >
      <Input
        type="search"
        placeholder="Search deal or client"
        value={searchDraft}
        onChange={(e) => setSearchDraft(e.target.value)}
        onBlur={commitSearch}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitSearch();
        }}
        className="sm:w-64"
        aria-label="Search deal or client"
      />

      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Status
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.open_closed ?? "open"}
          onChange={(e) =>
            setOpenClosed(
              (e.target.value || undefined) as PipelineFilters["open_closed"],
            )
          }
          data-testid="filter-open-closed"
        >
          {(["open", "closed_won", "closed_lost", "any"] as const).map((v) => (
            <option key={v} value={v}>
              {OPEN_CLOSED_LABELS[v]}
            </option>
          ))}
        </select>
      </label>

      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Date
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.date_field ?? ""}
          onChange={(e) => {
            const v = e.target.value as PipelineFilters["date_field"] | "";
            commitFilters((prev) => ({
              ...prev,
              date_field: v || undefined,
              // clear preset/bounds if the field is turned off
              date_preset: v ? prev.date_preset : undefined,
              date_from: v ? prev.date_from : undefined,
              date_to: v ? prev.date_to : undefined,
            }));
          }}
          data-testid="filter-date-field"
        >
          <option value="">— any date field —</option>
          {Object.entries(DATE_FIELD_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        {filters.date_field ? (
          <select
            className="rounded border border-divider bg-surface px-2 py-1 text-body"
            value={filters.date_preset ?? ""}
            onChange={(e) => {
              const v = (e.target.value || undefined) as PipelineFilters["date_preset"];
              commitFilters((prev) => ({ ...prev, date_preset: v }));
            }}
            data-testid="filter-date-preset"
          >
            <option value="">— range —</option>
            {Object.entries(DATE_PRESET_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        ) : null}
        <span className="text-secondary text-text-secondary">({businessTz})</span>
      </label>

      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        SOW
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.readiness?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              readiness: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-sow-state"
        >
          <option value="">— any state —</option>
          {Object.entries(SOW_STATE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>

      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Attention
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.attention?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              attention: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-attention"
        >
          <option value="">— any —</option>
          {Object.entries(ATTENTION_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>

      {/* S3b Rev-2 · Owner select. Options come from `/pipeline/facets`
        * (distinct users owning ≥1 HubSpot deal). Multi-value URL state
        * (`owner=A&owner=B`). Empty option = clear the filter. */}
      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Owner
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.owner?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              owner: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-owner"
          disabled={facets.owners.length === 0}
        >
          <option value="">— any owner —</option>
          {facets.owners.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      </label>

      {/* BU options follow the same active population as rows and totals. */}
      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        BU
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.business_unit?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              business_unit: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-business-unit"
          disabled={facets.business_units.length === 0}
        >
          <option value="">
            {facets.business_units.length === 0
              ? "— no matching BU —"
              : "— any BU —"}
          </option>
          {facets.business_units.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </label>

      {/* S20 W6 · Group select. Manual + rule-based tracking groups
        * (opportunity-scope) come from `/tracking-groups`. */}
      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Group
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.group?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              group: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-group"
          disabled={groups.length === 0}
        >
          <option value="">
            {groups.length === 0 ? "— no groups yet —" : "— any group —"}
          </option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
              {g.filter_json ? " (rule)" : ""}
            </option>
          ))}
        </select>
      </label>

      {/* S20 W6 · Saved view picker. Sets filter_json onto URL. */}
      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        View
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value=""
          onChange={(e) => {
            const viewId = e.target.value;
            if (!viewId) return;
            const view = savedViews.find((v) => v.id === viewId);
            if (!view) return;
            commitFilters((prev) => ({
              ...savedViewFilters(view),
              page: 1,
              page_size: prev.page_size,
            }));
            // S5 item 0a · persist per-user via server; keep localStorage
            // as fire-and-forget mirror for offline/first-load.
            window.localStorage.setItem(PREF_KEY_LAST_VIEW, view.id);
            putUserPreference(PREF_KEY_LAST_VIEW, {
              view_id: view.id,
            }).catch(() => {});
          }}
          data-testid="filter-saved-view"
          disabled={savedViews.length === 0}
        >
          <option value="">
            {savedViews.length === 0 ? "— no saved views —" : "— apply a view —"}
          </option>
          {savedViews.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.is_builtin ? " (built-in)" : ""}
            </option>
          ))}
        </select>
      </label>

      {/* S20 W6 · Watching toggle. Scopes list to the caller's stars. */}
      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        <input
          type="checkbox"
          checked={filters.watching === true}
          onChange={(e) => {
            const on = e.target.checked;
            commitFilters((prev) => ({
              ...prev,
              watching: on ? true : undefined,
            }));
          }}
          data-testid="filter-watching"
        />
        Watching ({watchCount ?? "..."})
      </label>

      <label className="inline-flex items-center gap-2 text-body text-text-secondary">
        Missing
        <select
          className="rounded border border-divider bg-surface px-2 py-1 text-body"
          value={filters.missing?.[0] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            commitFilters((prev) => ({
              ...prev,
              missing: v ? [v] : undefined,
            }));
          }}
          data-testid="filter-missing"
        >
          <option value="">— nothing missing —</option>
          {Object.entries(MISSING_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>

      {activeCount > 0 ? (
        <button
          type="button"
          onClick={clear}
          className="inline-flex items-center gap-1 rounded-panel border border-divider bg-surface px-3 py-1 text-secondary text-danger"
          data-testid="clear-filters"
        >
          <X className="h-3 w-3" aria-hidden />
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagination controls (L03). 25/50/100 + prev/next + global total on the
// count. Filter changes reset to page 1 — happens in `commitFilters`.
// ---------------------------------------------------------------------------

function Paginator({
  page,
  pageSize,
  total,
  setPage,
  setPageSize,
}: {
  page: number;
  pageSize: PageSize;
  total: number;
  setPage: (n: number) => void;
  setPageSize: (n: PageSize) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div
      className="mt-3 flex flex-wrap items-center justify-between gap-3 border-divider border-t pt-3 text-secondary text-text-secondary"
      data-testid="paginator"
    >
      <div>
        Showing {start.toLocaleString("en-US")}–{end.toLocaleString("en-US")} of{" "}
        {total.toLocaleString("en-US")}
      </div>
      <div className="flex items-center gap-2">
        <label className="inline-flex items-center gap-1">
          Rows per page
          <select
            className="rounded border border-divider bg-surface px-2 py-1 text-body"
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value) as PageSize)}
            data-testid="page-size"
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="rounded border border-divider bg-surface px-2 py-1 disabled:opacity-40"
          onClick={() => setPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          data-testid="page-prev"
        >
          ← Prev
        </button>
        <span aria-live="polite">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="rounded border border-divider bg-surface px-2 py-1 disabled:opacity-40"
          onClick={() => setPage(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          data-testid="page-next"
        >
          Next →
        </button>
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

// ---------------------------------------------------------------------------
// ClientsTable — D2 (account owner separate from deal owner) + matching-vs-total.
// ---------------------------------------------------------------------------

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
            <th className="px-3 py-2 font-medium">Account owner</th>
            <th className="px-3 py-2 font-medium">Matching / total open</th>
            <th className="px-3 py-2 font-medium">Open value</th>
            <th className="px-3 py-2 font-medium">Agreements</th>
            <th className="px-3 py-2 font-medium">SOW</th>
            <th className="px-3 py-2 font-medium">Attention</th>
            <th className="px-3 py-2 font-medium">Last activity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const matching = row.matching_deal_count ?? row.open_opp_count;
            const total = row.total_open_deal_count ?? matching;
            const accountLabel =
              row.account_owner_name ||
              row.account_owner_email ||
              (row.account_owner_id ? "Owner details unavailable" : "Not set");
            return (
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
                  {accountLabel}
                </td>
                <td className="px-3 py-3 align-top tnum text-text">
                  {total > matching ? `${matching} / ${total}` : String(matching)}
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
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OpportunitiesTable — L04 deal name, BU column, pipeline context, L07 Closed Lost pill.
// ---------------------------------------------------------------------------

function OpportunitiesTable({
  rows,
  onRow,
}: {
  rows: PipelineOpportunityRow[];
  onRow: (id: string) => void;
}) {
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
            <th className="px-3 py-2 font-medium">BU</th>
            <th className="px-3 py-2 font-medium">Amount</th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Close</th>
            <th className="px-3 py-2 font-medium">SOW</th>
            <th className="px-3 py-2 font-medium">Attention</th>
            <th className="px-3 py-2 font-medium">Latest comment</th>
            <th className="px-3 py-2 font-medium">Last activity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            // L04: prefer the real deal name (`row.name` mirrors HubSpot
            // dealname once W1 lands the column). Fall back to stage_label
            // then to the HubSpot id — but NEVER render a numeric stage
            // as the display name.
            const displayName =
              row.name && row.name.trim().length > 0
                ? row.name
                : row.hubspot_deal_id
                  ? `Deal ${row.hubspot_deal_id}`
                  : "Unnamed deal";
            const ownerLabel =
              row.owner_name ||
              row.owner_email ||
              (row.owner_id || row.source_owner_id
                ? "Owner details unavailable"
                : "Unassigned");
            return (
              <tr
                key={row.opportunity_id}
                data-testid={`opp-row-${row.opportunity_id}`}
                className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                onClick={() => onRow(row.opportunity_id)}
              >
                <td className="sticky left-0 z-10 bg-surface px-3 py-3 align-top">
                  <div className="flex items-center gap-2">
                    <span className="text-text">{displayName}</span>
                    {row.source_origin === "local_test_fixture" ? (
                      <span className="text-xs text-text-secondary">Local test fixture</span>
                    ) : null}
                    {row.is_closed_lost ? (
                      <Badge tone="danger" data-testid="closed-lost-pill">
                        Closed Lost
                      </Badge>
                    ) : null}
                    {row.is_closed_won ? (
                      <Badge tone="success" data-testid="closed-won-pill">
                        Closed Won
                      </Badge>
                    ) : null}
                  </div>
                  <div className="text-secondary text-text-secondary">
                    {row.hubspot_deal_id ? `HS #${row.hubspot_deal_id}` : ""}
                    {row.hubspot_pipeline_id ? (
                      <span>
                        {row.hubspot_deal_id ? " · " : ""}
                        pipeline {row.hubspot_pipeline_id}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {row.client_name || "—"}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {row.stage_label || "Unknown"}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {row.business_unit || "—"}
                </td>
                <td className="px-3 py-3 align-top tnum text-text">
                  {formatMoney(row.amount, row.currency)}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {ownerLabel}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {formatDate(row.close_date)}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {SOW_STATE_LABELS[row.sow_approval_state] ??
                    row.sow_approval_state}
                </td>
                <td className="px-3 py-3 align-top">
                  <AttentionBadges flags={row.attention_flags} />
                </td>
                <td
                  className="max-w-xs px-3 py-3 align-top text-text-secondary"
                  data-testid={`opp-latest-comment-${row.opportunity_id}`}
                >
                  {row.latest_comment_body ? (
                    <>
                      {row.latest_comment_pinned ? (
                        <span
                          className="mr-1 rounded bg-warn-fill/30 px-1 text-secondary text-warn"
                          data-testid={`opp-pinned-${row.opportunity_id}`}
                        >
                          📌
                        </span>
                      ) : null}
                      <span className="line-clamp-2">
                        {row.latest_comment_body}
                      </span>
                      <div className="text-secondary">
                        {row.latest_comment_author ?? "Someone"} ·{" "}
                        {formatAgo(row.latest_comment_at ?? null)}
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {formatAgo(row.hubspot_last_activity_at)}
                </td>
              </tr>
            );
          })}
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
