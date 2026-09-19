/**
 * Renewals report (spec §17). Expiring value by month · notice
 * deadlines · owner response · renewal outcomes. Original and
 * replacement contracts are distinguished so a renewed-then-replaced
 * SOW is never double-counted.
 */

import { BarChart } from "./BarChart";
import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import type { RenewalRow } from "../../../api/client";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface RenewalsReportProps {
  renewals: RenewalRow[];
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

export function RenewalsReport({
  renewals,
  fetchedAt,
  onExport,
}: RenewalsReportProps) {
  const byMonth = new Map<string, number>();
  for (const r of renewals) {
    if (r.status === "closed" || r.status === "churn") continue;
    const key = monthKey(r.term_end);
    byMonth.set(key, (byMonth.get(key) ?? 0) + 1);
  }
  const bars = Array.from(byMonth.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, value]) => ({
      label,
      value,
      display: `${value} renewal(s)`,
    }));

  const snapshot = { bars, renewals };

  return (
    <section aria-label="Renewals report" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
        <SourceFreshness
          source="Renewals workflow"
          asOf={fetchedAt ? fetchedAt.toLocaleString() : "Unknown"}
          basis="Original vs replacement contracts kept distinct."
        />
        <div className="text-secondary text-text-secondary">
          Included: <span className="tnum text-text">{renewals.length}</span>
        </div>
      </div>

      <div>
        <h3 className="text-section text-text">Expiring by month</h3>
        <div className="mt-3">
          <BarChart
            data={bars}
            ariaLabel="Renewals expiring by month"
            emptyLabel="No open renewals"
          />
        </div>
      </div>

      <div className="overflow-x-auto rounded-panel border border-divider">
        <table
          className="w-full text-body"
          aria-label="Renewals detail"
          data-testid="renewals-detail-table"
        >
          <thead className="bg-primary-subtle/40">
            <tr className="text-left text-secondary text-text-secondary">
              <th className="px-3 py-2 font-medium">Deal / Opportunity</th>
              <th className="px-3 py-2 font-medium">Expiry</th>
              <th className="px-3 py-2 font-medium text-right">Days remaining</th>
              <th className="px-3 py-2 font-medium">Owner response</th>
              <th className="px-3 py-2 font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {renewals.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-6 text-center text-text-secondary"
                >
                  No verified source
                </td>
              </tr>
            ) : (
              renewals.map((r) => (
                <tr key={r.id} className="border-t border-divider">
                  <td className="px-3 py-3 align-top text-text">
                    {r.hubspot_deal_id ?? r.opportunity_id.slice(0, 8)}
                  </td>
                  <td className="px-3 py-3 align-top tnum text-text-secondary">
                    {r.term_end}
                  </td>
                  <td className="px-3 py-3 align-top tnum text-right">
                    {r.days_until_end}
                  </td>
                  <td className="px-3 py-3 align-top text-text-secondary">
                    {r.outcome_summary ?? "No response"}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <StatusBadge
                      tone={
                        r.status === "closed"
                          ? "neutral"
                          : r.status === "churn"
                            ? "danger"
                            : r.status === "extended"
                              ? "ok"
                              : "warn"
                      }
                      label={r.status.replace(/_/g, " ")}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-divider pt-3">
        <Button
          variant="secondary"
          size="sm"
          type="button"
          data-testid="export-renewals-csv"
          onClick={() =>
            onExport?.({
              kind: "renewals",
              format: "csv",
              filename: buildExportFilename("renewals", "csv"),
              snapshot,
            })
          }
        >
          Export CSV
        </Button>
      </div>
    </section>
  );
}
