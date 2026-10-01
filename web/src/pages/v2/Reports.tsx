/**
 * Reports (`/reports`) — spec §17.
 *
 * Five report tabs — Portfolio / Margin / Revenue / Renewals /
 * Approval turnaround — sit under one page. A single global filter
 * row (period, business unit, geography, client, account owner,
 * engagement, currency) is shared across reports; each tab extends it
 * with its own local controls. Every tab labels display basis, as-of
 * time and included/excluded counts so a screenshot is self-describing.
 *
 * Where an API does not yet materialize a report we degrade to
 * "No verified source" (spec §4 state copy, blueprint §2 non-negotiable
 * "honest numbers"). Charts are inline SVG bars — no decorative pie
 * charts, and no browser math.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getApprovalsAging,
  getApprovalTurnaround,
  getCeoDashboard,
  getDeals,
  getFinanceDashboard,
  getPortfolioBasis,
  getReportsByBu,
  getReportsByOwner,
  getReportsByStage,
  getSowGmReport,
  listPipelineOpportunities,
  listRenewals,
  reportsPipelineCsvUrl,
  type ApprovalsAgingReport,
  type CeoDashboard,
  type DealRow,
  type FinanceDashboard,
  type PipelineOpportunityRow,
  type PortfolioBasis,
  type RenewalRow,
  type ReportByBu,
  type ReportByOwner,
  type ReportByStage,
  type SowGmReport,
  type TurnaroundReport,
} from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import {
  GlobalFilters,
  emptyGlobalFilters,
  type GlobalFilterValues,
} from "./reports/GlobalFilters";
import { PortfolioReport } from "./reports/PortfolioReport";
import { MarginReport } from "./reports/MarginReport";
import { RevenueReport } from "./reports/RevenueReport";
import { RenewalsReport } from "./reports/RenewalsReport";
import { ApprovalTurnaroundReport } from "./reports/ApprovalTurnaroundReport";
import type { ExportHandler } from "./reports/exports";

const CEO_ROLES = new Set(["CEO", "SystemAdmin"]);

type TabKey =
  | "pipeline"
  | "portfolio"
  | "margin"
  | "revenue"
  | "renewals"
  | "turnaround";

const TABS: { key: TabKey; label: string }[] = [
  // S20 W4 Session 6 · default tab is the pipeline rollup so the proof
  // numbers (by-stage / by-owner / by-BU / SOW GM / aging) land first.
  { key: "pipeline", label: "Pipeline rollups" },
  { key: "portfolio", label: "Portfolio" },
  { key: "margin", label: "Margin" },
  { key: "revenue", label: "Revenue" },
  { key: "renewals", label: "Renewals" },
  { key: "turnaround", label: "Approval turnaround" },
];

async function safe<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) return null;
    throw err;
  }
}

interface ReportsData {
  ceo: CeoDashboard | null;
  finance: FinanceDashboard | null;
  deals: DealRow[];
  // S20 L17/L18/T42: opportunities carry `stage_label`; deals carry
  // `sales_stage` which is often a numeric HubSpot id. Portfolio uses
  // pipeline opportunities for the stage chart so labels are human.
  pipelineOpps: PipelineOpportunityRow[];
  basis: PortfolioBasis | null;
  turnaround: TurnaroundReport | null;
  renewals: RenewalRow[];
  // S20 W4 Session 6 · aggregate rollups backed by hubspot_pipeline.
  byStage: ReportByStage | null;
  byOwner: ReportByOwner | null;
  byBu: ReportByBu | null;
  sowGm: SowGmReport | null;
  aging: ApprovalsAgingReport | null;
  fetchedAt: Date;
}

/**
 * Default export handler — logs the intent and would call the server
 * download endpoint in production. Kept behind a caller-supplied prop
 * so tests can assert the payload without touching the network.
 */
const defaultExport: ExportHandler = (args) => {
  // eslint-disable-next-line no-console
  console.info("[reports.export]", args.filename, args.kind, args.format);
};

export interface ReportsPageProps {
  onExport?: ExportHandler;
}

export function ReportsPage({ onExport = defaultExport }: ReportsPageProps = {}) {
  const { user } = useAuth();
  const isCeo = (user?.groups ?? []).some((g) => CEO_ROLES.has(g));

  const [tab, setTab] = useState<TabKey>("pipeline");
  const [filters, setFilters] = useState<GlobalFilterValues>(emptyGlobalFilters());
  const [data, setData] = useState<ReportsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        ceo,
        finance,
        deals,
        pipelineOpps,
        basis,
        turnaround,
        renewals,
        byStage,
        byOwner,
        byBu,
        sowGm,
        aging,
      ] = await Promise.all([
        isCeo ? safe(getCeoDashboard()) : Promise.resolve(null),
        safe(getFinanceDashboard()),
        safe(getDeals({ size: 100 })),
        safe(listPipelineOpportunities({ page_size: 100 })),
        safe(getPortfolioBasis()),
        safe(getApprovalTurnaround("30d")),
        safe(listRenewals({ size: 100 })),
        safe(getReportsByStage()),
        safe(getReportsByOwner()),
        safe(getReportsByBu()),
        safe(getSowGmReport()),
        safe(getApprovalsAging()),
      ]);
      setData({
        ceo,
        finance,
        deals: deals?.items ?? [],
        pipelineOpps: pipelineOpps?.items ?? [],
        basis,
        turnaround,
        renewals: renewals?.items ?? [],
        byStage,
        byOwner,
        byBu,
        sowGm,
        aging,
        fetchedAt: new Date(),
      });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [isCeo]);

  useEffect(() => {
    void load();
  }, [load]);

  const revenueProps = useMemo(() => {
    // Revenue tab shows contracted/forecast/recognized/backlog only if the
    // server materialized them. `null` degrades to "Unavailable"; invoice
    // and cash always render the "not sourced" caveat by default because
    // no invoice/cash datasource exists yet (spec §17).
    return {
      contractedValue: null as string | null,
      forecastRevenue:
        data?.finance?.approved_vs_forecast_vs_actual.forecast_gp ?? null,
      recognizedRevenue:
        data?.finance?.approved_vs_forecast_vs_actual.actual_gp ?? null,
      backlog: null as string | null,
      sourcing: { invoiceSourced: false, cashSourced: false },
    };
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Portfolio, margin, revenue, renewals and approval turnaround — each labelled with basis, freshness and completeness."
      />

      <div className="pb-4">
        <GlobalFilters
          values={filters}
          onChange={(patch) => setFilters((v) => ({ ...v, ...patch }))}
        />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList aria-label="Report tabs">
          {TABS.map((t) => (
            <TabsTrigger
              key={t.key}
              value={t.key}
              data-testid={`tab-${t.key}`}
            >
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={tab} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading report…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load the report"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
              onRetry={() => void load()}
            />
          ) : tab === "pipeline" ? (
            <PipelineRollupsTab
              byStage={data?.byStage ?? null}
              byOwner={data?.byOwner ?? null}
              byBu={data?.byBu ?? null}
              sowGm={data?.sowGm ?? null}
              aging={data?.aging ?? null}
              fetchedAt={data?.fetchedAt ?? null}
            />
          ) : tab === "portfolio" ? (
            <PortfolioReport
              ceo={data?.ceo ?? null}
              finance={data?.finance ?? null}
              deals={data?.deals ?? []}
              pipelineOpps={data?.pipelineOpps ?? []}
              basis={data?.basis ?? null}
              fetchedAt={data?.fetchedAt ?? null}
              onExport={onExport}
            />
          ) : tab === "margin" ? (
            <MarginReport
              finance={data?.finance ?? null}
              fetchedAt={data?.fetchedAt ?? null}
              onExport={onExport}
            />
          ) : tab === "revenue" ? (
            <RevenueReport
              contractedValue={revenueProps.contractedValue}
              forecastRevenue={revenueProps.forecastRevenue}
              recognizedRevenue={revenueProps.recognizedRevenue}
              backlog={revenueProps.backlog}
              sourcing={revenueProps.sourcing}
              fetchedAt={data?.fetchedAt ?? null}
              onExport={onExport}
            />
          ) : tab === "renewals" ? (
            <RenewalsReport
              renewals={data?.renewals ?? []}
              fetchedAt={data?.fetchedAt ?? null}
              onExport={onExport}
            />
          ) : (
            <ApprovalTurnaroundReport
              fetchedAt={data?.fetchedAt ?? null}
              onExport={onExport}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// -----------------------------------------------------------------------------
// S20 W4 Session 6 · Pipeline rollups tab — by-stage / by-owner / by-BU /
// SOW GM / approvals aging + CSV export. All numbers come from the
// `/reports/pipeline/*` endpoints, which share `hubspot_pipeline`'s base
// filter. "Not mirrored" is shown explicitly for BU (W1-D10).
// -----------------------------------------------------------------------------

interface PipelineRollupsProps {
  byStage: ReportByStage | null;
  byOwner: ReportByOwner | null;
  byBu: ReportByBu | null;
  sowGm: SowGmReport | null;
  aging: ApprovalsAgingReport | null;
  fetchedAt: Date | null;
}

function fmtMoney(value: string | null | undefined): string {
  if (!value) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function fmtPct(value: string | null | undefined): string {
  if (!value) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `${(n * 100).toFixed(1)}%`;
}

function PipelineRollupsTab({
  byStage,
  byOwner,
  byBu,
  sowGm,
  aging,
  fetchedAt,
}: PipelineRollupsProps) {
  return (
    <div className="flex flex-col gap-6" data-testid="pipeline-rollups">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-section text-text">Pipeline rollups</h2>
          <p className="text-secondary text-text-secondary">
            By stage · by owner · by BU · SOW GM · approvals aging. Every
            number comes from the same base filter the Pipeline page
            uses (A5/T35 totals-before-pagination). CSV export streams
            the open set with totals computed before any rows.
            {fetchedAt
              ? ` · As of ${fetchedAt.toLocaleTimeString()}`
              : null}
          </p>
        </div>
        <a
          href={`/api${reportsPipelineCsvUrl}`}
          className="rounded-control border border-divider bg-surface px-3 py-2 text-body text-text hover:bg-primary-subtle/20"
          download="pipeline.csv"
          data-testid="reports-csv-export"
        >
          Export CSV
        </a>
      </header>

      {/* By stage */}
      <section aria-label="By stage" className="rounded-panel border border-divider bg-surface p-4">
        <h3 className="text-section text-text">By stage</h3>
        {byStage ? (
          <>
            <p className="text-secondary text-text-secondary">
              {byStage.total_count} open · {fmtMoney(byStage.total_open_value_usd)}
            </p>
            <table className="mt-3 w-full text-body">
              <thead>
                <tr className="text-left text-text-secondary text-secondary">
                  <th className="py-1">Stage</th>
                  <th className="py-1 text-right">Count</th>
                  <th className="py-1 text-right">Open value (USD)</th>
                </tr>
              </thead>
              <tbody>
                {byStage.rows.map((r) => (
                  <tr key={r.stage_id ?? r.stage_label} className="border-t border-divider">
                    <td className="py-1">{r.stage_label}</td>
                    <td className="py-1 text-right tnum">{r.count}</td>
                    <td className="py-1 text-right tnum">{fmtMoney(r.open_value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-text-secondary">Unavailable — endpoint did not respond.</p>
        )}
      </section>

      {/* By owner */}
      <section aria-label="By owner" className="rounded-panel border border-divider bg-surface p-4">
        <h3 className="text-section text-text">By deal owner</h3>
        {byOwner ? (
          <>
            <p className="text-secondary text-text-secondary">
              {byOwner.total_count} open · {fmtMoney(byOwner.total_open_value_usd)}
            </p>
            <table className="mt-3 w-full text-body">
              <thead>
                <tr className="text-left text-text-secondary text-secondary">
                  <th className="py-1">Owner</th>
                  <th className="py-1 text-right">Count</th>
                  <th className="py-1 text-right">Open value (USD)</th>
                </tr>
              </thead>
              <tbody>
                {byOwner.rows.map((r, i) => (
                  <tr key={`${r.owner_name}-${i}`} className="border-t border-divider">
                    <td className="py-1">{r.owner_name}</td>
                    <td className="py-1 text-right tnum">{r.count}</td>
                    <td className="py-1 text-right tnum">{fmtMoney(r.open_value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-text-secondary">Unavailable — endpoint did not respond.</p>
        )}
      </section>

      {/* By BU — honestly says "not mirrored" when the staging HubSpot
          portal has no BU property on deals (W1-D10). */}
      <section
        aria-label="By business unit"
        className="rounded-panel border border-divider bg-surface p-4"
        data-testid="reports-by-bu"
      >
        <h3 className="text-section text-text">By business unit</h3>
        {byBu ? (
          <>
            <p className="text-secondary text-text-secondary">{byBu.note}</p>
            <table className="mt-3 w-full text-body">
              <thead>
                <tr className="text-left text-text-secondary text-secondary">
                  <th className="py-1">BU</th>
                  <th className="py-1 text-right">Count</th>
                  <th className="py-1 text-right">Open value (USD)</th>
                </tr>
              </thead>
              <tbody>
                {byBu.rows.map((r) => (
                  <tr key={r.business_unit} className="border-t border-divider">
                    <td className="py-1">{r.business_unit}</td>
                    <td className="py-1 text-right tnum">{r.count}</td>
                    <td className="py-1 text-right tnum">{fmtMoney(r.open_value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-text-secondary">Unavailable — endpoint did not respond.</p>
        )}
      </section>

      {/* SOW GM per component */}
      <section
        aria-label="SOW GM"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text">SOW GM per component</h3>
        {sowGm ? (
          <>
            <p className="text-secondary text-text-secondary">
              US floor {fmtPct(sowGm.us_floor_pct)} · India floor{" "}
              {fmtPct(sowGm.india_floor_pct)} · {sowGm.note}
            </p>
            {sowGm.rows.length === 0 ? (
              <p className="mt-3 text-text-secondary">
                No GM models materialised for the open set — the table is
                empty by honest derivation, not a bug.
              </p>
            ) : (
              <table className="mt-3 w-full text-body">
                <thead>
                  <tr className="text-left text-text-secondary text-secondary">
                    <th className="py-1">Deal</th>
                    <th className="py-1">Component</th>
                    <th className="py-1 text-right">Revenue</th>
                    <th className="py-1 text-right">GM</th>
                    <th className="py-1 text-right">Floor</th>
                    <th className="py-1">Pass</th>
                  </tr>
                </thead>
                <tbody>
                  {sowGm.rows.map((r, i) => (
                    <tr key={`${r.opportunity_id}-${r.component}-${i}`} className="border-t border-divider">
                      <td className="py-1">{r.deal_name ?? r.hubspot_deal_id}</td>
                      <td className="py-1">{r.component}</td>
                      <td className="py-1 text-right tnum">{fmtMoney(r.revenue)}</td>
                      <td className="py-1 text-right tnum">{fmtPct(r.gm_pct)}</td>
                      <td className="py-1 text-right tnum">{fmtPct(r.floor_pct)}</td>
                      <td className="py-1">
                        {r.floor_pass === null
                          ? "—"
                          : r.floor_pass
                            ? "pass"
                            : "FAIL"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <p className="text-text-secondary">Unavailable — endpoint did not respond.</p>
        )}
      </section>

      {/* Approvals aging */}
      <section
        aria-label="Approvals aging"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text">Approvals aging</h3>
        {aging ? (
          <table className="mt-3 w-full text-body">
            <thead>
              <tr className="text-left text-text-secondary text-secondary">
                <th className="py-1">Lane</th>
                <th className="py-1 text-right">Total</th>
                <th className="py-1 text-right">≤24h</th>
                <th className="py-1 text-right">1-3d</th>
                <th className="py-1 text-right">3-7d</th>
                <th className="py-1 text-right">&gt;7d</th>
              </tr>
            </thead>
            <tbody>
              {aging.lanes.map((lane) => (
                <tr key={lane.status} className="border-t border-divider">
                  <td className="py-1">{lane.status.replace(/_/g, " ")}</td>
                  <td className="py-1 text-right tnum">{lane.total}</td>
                  {lane.buckets.map((b) => (
                    <td key={b.label} className="py-1 text-right tnum">
                      {b.count}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-text-secondary">Unavailable — endpoint did not respond.</p>
        )}
      </section>
    </div>
  );
}
