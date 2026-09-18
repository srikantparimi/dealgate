/**
 * HR dashboard — confirmed vs probability-weighted demand by role /
 * seniority / location. Demand math is server-side.
 */

import { useCallback, useEffect, useState } from "react";
import { getHrDashboard, type HrDashboard } from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard } from "./shared";

export function HRDashboardPage() {
  const [data, setData] = useState<HrDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getHrDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data) return <EmptyState title="Loading" hint="Fetching HR dashboard." />;

  const cols: Column<{ id: string } & HrDashboard["demand_by_skill"][number]>[] = [
    { key: "role", header: "Role", render: (r) => r.role },
    { key: "seniority", header: "Seniority", render: (r) => r.seniority },
    { key: "loc", header: "Location", render: (r) => r.location },
    { key: "confirmed", header: "Confirmed FTE", render: (r) => r.confirmed_fte ?? "—" },
    { key: "weighted", header: "Weighted FTE", render: (r) => r.weighted_fte ?? "—" },
  ];
  const rows = data.demand_by_skill.map((r, i) => ({
    ...r,
    id: `${r.role}|${r.seniority}|${r.location}|${i}`,
  }));

  return (
    <div>
      <PageHeader
        title="HR dashboard"
        subtitle="Confirmed + probability-weighted demand by skill."
      />
      <DashboardCard
        title="Demand by skill"
        subtitle="Confirmed = released package. Weighted = 50% of open pipeline."
      >
        {rows.length === 0 ? (
          <EmptyState title="No demand data yet" />
        ) : (
          <Table ariaLabel="Demand by skill" columns={cols} rows={rows} />
        )}
      </DashboardCard>
    </div>
  );
}
