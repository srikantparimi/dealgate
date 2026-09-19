/**
 * Delivery & actuals (`/projects`) — spec §15.
 *
 * Three portfolio tabs — Portfolio / Actuals / Staffing — plus a
 * pre-wired detail page at `/projects/:id/:tab?` via inline nested
 * routes. The detail route is intentionally NOT registered in App.tsx
 * (this Wave brief locks App.tsx). When App.tsx switches the outer
 * pattern to `/projects/*`, this file transparently starts serving the
 * detail pane.
 *
 * Role gates (client-side UX; server independently enforces per
 * CLAUDE.md rule 5):
 *   - Import actuals              → Finance / SystemAdmin
 *   - Update forecast (detail)    → Delivery / SystemAdmin
 *
 * All money and margin strings arrive pre-formatted from the server
 * loader helpers in `projects/format.ts`; the components never do the
 * math (blueprint §2).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import {
  ApiError,
  getDeals,
  listActualBatches,
  type ActualBatch,
  type DealRow,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { SourceFreshness } from "../../ui-v2/SourceFreshness";
import { Button } from "../../ui-v2/primitives/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { PortfolioTable, type PortfolioRow } from "./projects/PortfolioTable";
import { ActualsTab } from "./projects/ActualsTab";
import { StaffingTab, type StaffingRow } from "./projects/StaffingTab";
import { ProjectDetailPage } from "./projects/ProjectDetail";

const FINANCE_ROLES = new Set(["Finance", "SystemAdmin"]);

type TabKey = "portfolio" | "actuals" | "staffing";

const TABS: { key: TabKey; label: string }[] = [
  { key: "portfolio", label: "Portfolio" },
  { key: "actuals", label: "Actuals" },
  { key: "staffing", label: "Staffing" },
];

function todayMonth(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}-${m}`;
}

/**
 * Turn a deal row into a portfolio row. The server does NOT yet return
 * an approved / forecast final GM per deal, so those columns render as
 * "Not validated" via `MarginCell` — that is the honest "no verified
 * source" state (spec §4). We do not fabricate margins on the client.
 */
function toPortfolioRow(d: DealRow): PortfolioRow {
  return {
    id: d.id,
    clientProject:
      d.client_name ?? d.hubspot_deal_id ?? `Deal ${d.id.slice(0, 8)}`,
    sowEndDate: null,
    deliveryOwner: d.owner_id ? d.owner_id.slice(0, 8) : null,
    signedValue: null,
    approvedFinalGm: null,
    forecastFinalGm: null,
    risk:
      d.governance_status === "released"
        ? { label: "Active", tone: "ok" }
        : d.governance_status === "rejected"
          ? { label: "Blocked", tone: "danger" }
          : { label: d.governance_status.replace(/_/g, " "), tone: "warn" },
    nextReview: d.next_client_date,
  };
}

function PortfolioIndex() {
  const nav = useNavigate();
  const { user } = useAuth();
  const canUpload = (user?.groups ?? []).some((g) => FINANCE_ROLES.has(g));

  const [tab, setTab] = useState<TabKey>("portfolio");
  const [deals, setDeals] = useState<DealRow[]>([]);
  const [batches, setBatches] = useState<ActualBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [period, setPeriod] = useState<string>(todayMonth());
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dealsRes, batchesRes] = await Promise.all([
        getDeals({ size: 100 }),
        canUpload
          ? listActualBatches({ size: 20 }).catch((err) => {
              // Non-403 rethrows; 403 degrades quietly.
              if (err instanceof ApiError && err.status === 403) return null;
              throw err;
            })
          : Promise.resolve(null),
      ]);
      setDeals(dealsRes.items);
      setBatches(batchesRes?.items ?? []);
      setFetchedAt(new Date());
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [canUpload]);

  useEffect(() => {
    void load();
  }, [load]);

  const portfolioRows = useMemo(() => deals.map(toPortfolioRow), [deals]);
  const staffingRows = useMemo<StaffingRow[]>(
    () => [], // Server does not yet return resource lines in the deals list.
    [],
  );

  const actions = (
    <div className="flex items-center gap-2">
      {canUpload ? (
        <Button type="button" data-testid="import-actuals">
          Import actuals
        </Button>
      ) : null}
      <Button variant="secondary" type="button" data-testid="export-portfolio">
        Export
      </Button>
    </div>
  );

  const counts: Record<TabKey, number> = {
    portfolio: portfolioRows.length,
    actuals: batches.length,
    staffing: staffingRows.length,
  };

  return (
    <div>
      <PageHeader
        title="Delivery & actuals"
        subtitle="Portfolio, reconciliation, forecast and staffing. Signed value is not the same as recognized revenue."
        actions={actions}
      />

      <div className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
          <TabsList aria-label="Delivery tabs">
            {TABS.map((t) => (
              <TabsTrigger key={t.key} value={t.key}>
                {t.label} ({counts[t.key]})
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {fetchedAt ? (
          <SourceFreshness
            source="DealGate governance"
            asOf={fetchedAt.toLocaleString()}
            basis="Server-computed. Missing values render as Unavailable."
          />
        ) : null}
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsContent value={tab} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading portfolio…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load the portfolio"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
              onRetry={() => void load()}
            />
          ) : tab === "portfolio" ? (
            portfolioRows.length === 0 ? (
              <EmptyState
                title="No portfolio rows yet."
                description="Signed SOWs surface here once the release evidence lands."
              />
            ) : (
              <PortfolioTable
                rows={portfolioRows}
                onRowClick={(r) => nav(`/projects/${r.id}`)}
              />
            )
          ) : tab === "actuals" ? (
            <ActualsTab
              periodMonth={period}
              onPeriodChange={setPeriod}
              batches={batches}
              canUpload={canUpload}
              reconciliation={null}
            />
          ) : (
            <StaffingTab rows={staffingRows} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Public entry point. Nests the detail route in-line — the wave brief
 * forbids editing App.tsx, so we ship the sub-routes here for the day
 * App.tsx switches to `/projects/*`.
 */
export function ProjectsActualsPage() {
  return (
    <Routes>
      <Route index element={<PortfolioIndex />} />
      <Route path=":id" element={<ProjectDetailPage />} />
      <Route path=":id/:tab" element={<ProjectDetailPage />} />
    </Routes>
  );
}
