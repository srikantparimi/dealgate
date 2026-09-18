/**
 * Legal dashboard — NDA/MSA coverage summary, packages awaiting legal,
 * notice dates approaching.
 */

import { useCallback, useEffect, useState } from "react";
import { getLegalDashboard, type LegalDashboard } from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard } from "./shared";

export function LegalDashboardPage() {
  const [data, setData] = useState<LegalDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getLegalDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data)
    return <EmptyState title="Loading" hint="Fetching Legal dashboard." />;

  const pkgCols: Column<{ id: string } & LegalDashboard["packages_awaiting_legal"][number]>[] = [
    { key: "id", header: "Package", render: (r) => r.id.slice(0, 8) + "…" },
    { key: "opp", header: "Opportunity", render: (r) => r.opportunity_id.slice(0, 8) + "…" },
    { key: "sub", header: "Submitted", render: (r) => r.submitted_at ?? "—" },
  ];
  const pkgRows = data.packages_awaiting_legal.map((r) => ({ ...r, id: r.id }));

  const noticeCols: Column<{ id: string } & LegalDashboard["notice_dates_approaching"][number]>[] = [
    { key: "id", header: "Agreement", render: (r) => r.agreement_id.slice(0, 8) + "…" },
    { key: "kind", header: "Kind", render: (r) => r.kind },
    { key: "state", header: "State", render: (r) => r.state },
    { key: "due", header: "Due", render: (r) => r.due_date ?? "—" },
    { key: "next", header: "Next action", render: (r) => r.next_action ?? "—" },
    { key: "owner", header: "Owner", render: (r) => r.owner_email ?? "—" },
  ];
  const noticeRows = data.notice_dates_approaching.map((r) => ({
    ...r,
    id: r.agreement_id,
  }));

  return (
    <div>
      <PageHeader
        title="Legal dashboard"
        subtitle="Coverage, packages awaiting legal, notice dates."
      />

      <DashboardCard title="NDA / MSA coverage summary">
        {Object.keys(data.nda_msa_coverage_summary).length === 0 ? (
          <EmptyState title="No clients" />
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {Object.entries(data.nda_msa_coverage_summary).map(([state, count]) => (
              <li key={state} style={{ marginBottom: 4 }}>
                <strong>{state}</strong>: {count}
              </li>
            ))}
          </ul>
        )}
      </DashboardCard>

      <DashboardCard title="Packages awaiting legal">
        {pkgRows.length === 0 ? (
          <EmptyState title="No packages awaiting legal" />
        ) : (
          <Table ariaLabel="Packages awaiting legal" columns={pkgCols} rows={pkgRows} />
        )}
      </DashboardCard>

      <DashboardCard title="Notice dates approaching (30 days)">
        {noticeRows.length === 0 ? (
          <EmptyState title="No notice dates in the next 30 days" />
        ) : (
          <Table ariaLabel="Notice dates" columns={noticeCols} rows={noticeRows} />
        )}
      </DashboardCard>
    </div>
  );
}
