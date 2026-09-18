/**
 * CEO dashboard — five widgets, blueprint §9. Every number is server-side
 * math (:mod:`app.services.dashboards.ceo_view`); this page only renders.
 */

import { useCallback, useEffect, useState } from "react";
import { getCeoDashboard, type CeoDashboard } from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { StatusChip } from "../../ui/StatusChip";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard, StatValue, money, pct } from "./shared";

export function CEODashboard() {
  const [data, setData] = useState<CeoDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getCeoDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data) return <EmptyState title="Loading" hint="Fetching CEO dashboard." />;

  const belowFloorCols: Column<{ id: string } & CeoDashboard["below_floor_deals"][number]>[] = [
    { key: "deal", header: "Deal", render: (r) => r.hubspot_deal_id },
    { key: "gov", header: "Governance", render: (r) => r.governance_status },
    { key: "revenue", header: "Revenue", render: (r) => money(r.revenue) },
    { key: "gm_us", header: "GM US", render: (r) => pct(r.gm_us) },
    { key: "gm_india", header: "GM India", render: (r) => pct(r.gm_india) },
  ];
  const belowFloorRows = data.below_floor_deals.map((r) => ({
    ...r,
    id: r.opportunity_id,
  }));

  const excCols: Column<{ id: string } & CeoDashboard["ceo_exceptions_pending"][number]>[] = [
    { key: "id", header: "Exception", render: (r) => r.id.slice(0, 8) + "…" },
    { key: "package", header: "Package", render: (r) => r.package_id.slice(0, 8) + "…" },
    { key: "drafted", header: "Drafted", render: (r) => r.drafted_at ?? "—" },
    {
      key: "rationale",
      header: "Rationale",
      render: (r) =>
        r.has_rationale ? (
          <StatusChip tone="ok">present</StatusChip>
        ) : (
          <StatusChip tone="warn">missing</StatusChip>
        ),
    },
  ];
  const excRows = data.ceo_exceptions_pending.map((r) => ({ ...r, id: r.id }));

  return (
    <div>
      <PageHeader title="CEO dashboard" subtitle="Pipeline, GP and exceptions." />

      <DashboardCard title="Pipeline + GP">
        <StatValue label="Pipeline value" value={money(data.pipeline_value)} />
        <StatValue
          label="Approved GP"
          value={money(data.approved_vs_forecast_gp.approved_gp)}
        />
        <StatValue
          label="Forecast GP"
          value={money(data.approved_vs_forecast_gp.forecast_gp)}
        />
      </DashboardCard>

      <DashboardCard
        title="Below-floor deals"
        subtitle="Latest gm_model under the US or India floor."
      >
        {belowFloorRows.length === 0 ? (
          <EmptyState title="No deals below floor" />
        ) : (
          <Table
            ariaLabel="Below floor deals"
            columns={belowFloorCols}
            rows={belowFloorRows}
          />
        )}
      </DashboardCard>

      <DashboardCard title="CEO exceptions pending">
        {excRows.length === 0 ? (
          <EmptyState title="Nothing awaiting a CEO decision" />
        ) : (
          <Table ariaLabel="CEO exceptions" columns={excCols} rows={excRows} />
        )}
      </DashboardCard>

      <DashboardCard
        title="Revenue expiring in 90 days"
        subtitle={
          data.notes?.revenue_expiring_in_90_days ??
          "Renewal periods; empty when the source table isn't populated."
        }
      >
        {data.revenue_expiring_in_90_days.length === 0 ? (
          <EmptyState title="No expiring revenue" />
        ) : (
          <div style={{ color: "#6b7280", fontSize: 14 }}>
            {data.revenue_expiring_in_90_days.length} rows
          </div>
        )}
      </DashboardCard>

      <DashboardCard title="Aged blockers by owner">
        {Object.keys(data.aged_blockers_by_owner).length === 0 ? (
          <EmptyState title="No aged blockers" />
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {Object.entries(data.aged_blockers_by_owner).map(([owner, tasks]) => (
              <li key={owner} style={{ marginBottom: 6 }}>
                <strong>{owner}</strong> — {tasks.length} blocker(s)
              </li>
            ))}
          </ul>
        )}
      </DashboardCard>
    </div>
  );
}
