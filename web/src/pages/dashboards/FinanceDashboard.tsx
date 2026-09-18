/**
 * Finance dashboard — GM by SOW / geography, approved vs forecast vs
 * actual, missing cost inputs, exceptions + exposure. Every number is
 * server-side (:mod:`app.services.dashboards.finance_view`).
 */

import { useCallback, useEffect, useState } from "react";
import {
  getFinanceDashboard,
  type FinanceDashboard,
} from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { StatusChip } from "../../ui/StatusChip";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard, StatValue, money, pct } from "./shared";

export function FinanceDashboardPage() {
  const [data, setData] = useState<FinanceDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getFinanceDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data)
    return <EmptyState title="Loading" hint="Fetching Finance dashboard." />;

  const gmCols: Column<{ id: string } & FinanceDashboard["gm_by_sow"][number]>[] = [
    { key: "deal", header: "Deal", render: (r) => r.hubspot_deal_id },
    { key: "type", header: "Type", render: (r) => r.engagement_type },
    { key: "revenue", header: "Revenue", render: (r) => money(r.revenue) },
    { key: "cost", header: "Cost", render: (r) => money(r.cost) },
    { key: "gm_us", header: "GM US", render: (r) => pct(r.gm_us) },
    { key: "gm_india", header: "GM India", render: (r) => pct(r.gm_india) },
    { key: "gm_blended", header: "Blended", render: (r) => pct(r.gm_blended) },
    {
      key: "complete",
      header: "Complete",
      render: (r) =>
        r.complete ? (
          <StatusChip tone="ok">yes</StatusChip>
        ) : (
          <StatusChip tone="warn">no</StatusChip>
        ),
    },
    {
      key: "approved",
      header: "Approved",
      render: (r) =>
        r.approved ? <StatusChip tone="ok">yes</StatusChip> : "—",
    },
  ];
  const gmRows = data.gm_by_sow.map((r) => ({
    ...r,
    id: r.opportunity_id,
  }));

  const missingCols: Column<{ id: string } & FinanceDashboard["missing_cost_inputs"][number]>[] = [
    { key: "deal", header: "Deal", render: (r) => r.hubspot_deal_id },
    { key: "gm", header: "GM model", render: (r) => r.gm_model_id.slice(0, 8) + "…" },
  ];
  const missingRows = data.missing_cost_inputs.map((r) => ({
    ...r,
    id: r.gm_model_id,
  }));

  const exposureCols: Column<{ id: string } & FinanceDashboard["exceptions_and_exposure"][number]>[] = [
    { key: "exc", header: "Exception", render: (r) => r.ceo_exception_id.slice(0, 8) + "…" },
    {
      key: "shortfall",
      header: "Shortfall (USD)",
      render: (r) => money(r.gross_profit_shortfall_usd),
    },
  ];
  const exposureRows = data.exceptions_and_exposure.map((r) => ({
    ...r,
    id: r.ceo_exception_id,
  }));

  return (
    <div>
      <PageHeader
        title="Finance dashboard"
        subtitle="GM by SOW / geography, approved vs forecast, exceptions."
      />

      <DashboardCard title="GM by SOW">
        {gmRows.length === 0 ? (
          <EmptyState title="No GM models yet" />
        ) : (
          <Table ariaLabel="GM by SOW" columns={gmCols} rows={gmRows} />
        )}
      </DashboardCard>

      <DashboardCard title="GM by geography">
        <div style={{ display: "flex", gap: 32 }}>
          <div>
            <div style={{ color: "#6b7280", fontSize: 12 }}>US</div>
            <StatValue label="Revenue" value={money(data.gm_by_geography.US.revenue)} />
            <StatValue label="Cost" value={money(data.gm_by_geography.US.cost)} />
            <StatValue label="GM" value={pct(data.gm_by_geography.US.gm)} />
          </div>
          <div>
            <div style={{ color: "#6b7280", fontSize: 12 }}>India</div>
            <StatValue label="Revenue" value={money(data.gm_by_geography.India.revenue)} />
            <StatValue label="Cost" value={money(data.gm_by_geography.India.cost)} />
            <StatValue label="GM" value={pct(data.gm_by_geography.India.gm)} />
          </div>
        </div>
      </DashboardCard>

      <DashboardCard
        title="Approved vs Forecast vs Actual GP"
        subtitle={
          data.notes?.actual_gp ??
          "Actuals land in Sprint 6; forecast is the latest gm_model."
        }
      >
        <StatValue
          label="Approved"
          value={money(data.approved_vs_forecast_vs_actual.approved_gp)}
        />
        <StatValue
          label="Forecast"
          value={money(data.approved_vs_forecast_vs_actual.forecast_gp)}
        />
        <StatValue
          label="Actual"
          value={money(data.approved_vs_forecast_vs_actual.actual_gp)}
        />
      </DashboardCard>

      <DashboardCard title="Missing cost inputs">
        {missingRows.length === 0 ? (
          <EmptyState title="Every GM model has validated costs" />
        ) : (
          <Table
            ariaLabel="Missing cost inputs"
            columns={missingCols}
            rows={missingRows}
          />
        )}
      </DashboardCard>

      <DashboardCard title="Exceptions and exposure">
        {exposureRows.length === 0 ? (
          <EmptyState title="No open CEO exceptions" />
        ) : (
          <Table
            ariaLabel="Exceptions and exposure"
            columns={exposureCols}
            rows={exposureRows}
          />
        )}
      </DashboardCard>
    </div>
  );
}
