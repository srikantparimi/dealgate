/**
 * Delivery dashboard — estimates awaiting review, staffing gaps, upcoming
 * starts. Effort variance is a placeholder until the timesheet feed lands.
 */

import { useCallback, useEffect, useState } from "react";
import {
  getDeliveryDashboard,
  type DeliveryDashboard,
} from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard } from "./shared";

export function DeliveryDashboardPage() {
  const [data, setData] = useState<DeliveryDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getDeliveryDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data)
    return <EmptyState title="Loading" hint="Fetching Delivery dashboard." />;

  const estCols: Column<{ id: string } & DeliveryDashboard["estimates_awaiting_review"][number]>[] = [
    { key: "id", header: "Estimate", render: (r) => r.id.slice(0, 8) + "…" },
    { key: "submitted", header: "Submitted", render: (r) => r.submitted_at ?? "—" },
  ];
  const estRows = data.estimates_awaiting_review.map((r) => ({ ...r, id: r.id }));

  const gapCols: Column<{ id: string } & DeliveryDashboard["staffing_gaps"][number]>[] = [
    { key: "role", header: "Role", render: (r) => `${r.role} / ${r.seniority}` },
    { key: "loc", header: "Location", render: (r) => r.location },
    { key: "start", header: "Start", render: (r) => r.start_date },
    {
      key: "days",
      header: "Days out",
      render: (r) => `${r.days_until_start} / need ${r.lead_time_days}`,
    },
    { key: "warning", header: "Warning", render: (r) => r.warning },
  ];
  const gapRows = data.staffing_gaps.map((r) => ({ ...r, id: r.resource_line_id }));

  const startCols: Column<{ id: string } & DeliveryDashboard["upcoming_starts"][number]>[] = [
    { key: "role", header: "Role", render: (r) => `${r.role} / ${r.seniority}` },
    { key: "person", header: "Person", render: (r) => r.person_name ?? "TO HIRE" },
    { key: "loc", header: "Location", render: (r) => r.location },
    { key: "start", header: "Start", render: (r) => r.start_date },
  ];
  const startRows = data.upcoming_starts.map((r) => ({ ...r, id: r.resource_line_id }));

  return (
    <div>
      <PageHeader
        title="Delivery dashboard"
        subtitle="Estimates + staffing gaps + upcoming starts."
      />

      <DashboardCard title="Estimates awaiting review">
        {estRows.length === 0 ? (
          <EmptyState title="No estimates in the queue" />
        ) : (
          <Table
            ariaLabel="Estimates awaiting review"
            columns={estCols}
            rows={estRows}
          />
        )}
      </DashboardCard>

      <DashboardCard
        title="Staffing gaps"
        subtitle="To-hire lines starting inside the HR lead time window."
      >
        {gapRows.length === 0 ? (
          <EmptyState title="No staffing gaps" />
        ) : (
          <Table ariaLabel="Staffing gaps" columns={gapCols} rows={gapRows} />
        )}
      </DashboardCard>

      <DashboardCard title="Upcoming starts (next 30 days)">
        {startRows.length === 0 ? (
          <EmptyState title="No upcoming starts" />
        ) : (
          <Table ariaLabel="Upcoming starts" columns={startCols} rows={startRows} />
        )}
      </DashboardCard>

      <DashboardCard
        title="Effort variance"
        subtitle={
          data.notes?.effort_variance ??
          "Effort variance needs the timesheet feed; empty for now."
        }
      >
        <EmptyState title="Placeholder — Sprint 6 backlog" />
      </DashboardCard>
    </div>
  );
}
