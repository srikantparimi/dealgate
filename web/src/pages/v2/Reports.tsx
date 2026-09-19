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
  getCeoDashboard,
  getDeals,
  getFinanceDashboard,
  listRenewals,
  type CeoDashboard,
  type DealRow,
  type FinanceDashboard,
  type RenewalRow,
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

type TabKey = "portfolio" | "margin" | "revenue" | "renewals" | "turnaround";

const TABS: { key: TabKey; label: string }[] = [
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
  renewals: RenewalRow[];
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

  const [tab, setTab] = useState<TabKey>("portfolio");
  const [filters, setFilters] = useState<GlobalFilterValues>(emptyGlobalFilters());
  const [data, setData] = useState<ReportsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ceo, finance, deals, renewals] = await Promise.all([
        isCeo ? safe(getCeoDashboard()) : Promise.resolve(null),
        safe(getFinanceDashboard()),
        safe(getDeals({ size: 100 })),
        safe(listRenewals({ size: 100 })),
      ]);
      setData({
        ceo,
        finance,
        deals: deals?.items ?? [],
        renewals: renewals?.items ?? [],
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
          ) : tab === "portfolio" ? (
            <PortfolioReport
              ceo={data?.ceo ?? null}
              finance={data?.finance ?? null}
              deals={data?.deals ?? []}
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
