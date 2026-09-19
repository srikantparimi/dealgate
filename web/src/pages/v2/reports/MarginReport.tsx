/**
 * Margin report (spec §17). Approved final vs forecast final vs period
 * actual, per SOW / client / geography. Below-floor exceptions and
 * recovery owners are surfaced alongside the numbers.
 *
 * Because we render server-provided Decimal strings, we display them
 * verbatim in a data table — the accompanying bar chart is a visual
 * aid, not a source of truth (spec §17 & §4).
 */

import { MarginCell } from "../../../ui-v2/MarginCell";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import { Button } from "../../../ui-v2/primitives/button";
import type {
  FinanceDashboard,
  FinanceGmBySowRow,
} from "../../../api/client";
import { BarChart } from "./BarChart";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface MarginReportProps {
  finance: FinanceDashboard | null;
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

function formatPct(v: string | null): string | null {
  if (!v) return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return `${(n * 100).toFixed(1)}%`;
}

export function MarginReport({
  finance,
  fetchedAt,
  onExport,
}: MarginReportProps) {
  const rows: FinanceGmBySowRow[] = finance?.gm_by_sow ?? [];
  const exposures = finance?.exceptions_and_exposure ?? [];

  const bars = [
    { geo: "US", gm: finance?.gm_by_geography.US.gm ?? null },
    { geo: "India", gm: finance?.gm_by_geography.India.gm ?? null },
  ]
    .filter((b) => b.gm !== null)
    .map((b) => ({
      label: `${b.geo} GM`,
      value: Number(b.gm) * 100,
      display: `${(Number(b.gm) * 100).toFixed(1)}%`,
    }));

  const snapshot = { rows, geographies: bars, exposures };

  return (
    <section aria-label="Margin report" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
        <SourceFreshness
          source="Finance dashboard"
          asOf={fetchedAt ? fetchedAt.toLocaleString() : "Unknown"}
          basis="Approved vs forecast vs actual — server-computed Decimal"
        />
        <div className="text-secondary text-text-secondary">
          Included: <span className="tnum text-text">{rows.length}</span> SOW(s)
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-section text-text">Blended GM by geography</h3>
          <div className="mt-3">
            <BarChart
              data={bars}
              ariaLabel="GM by geography"
              emptyLabel="No verified source"
            />
          </div>
        </div>
        <div>
          <h3 className="text-section text-text">Below-floor exposures</h3>
          {exposures.length === 0 ? (
            <p className="mt-3 text-body text-text-secondary">
              No below-floor exceptions on active packages.
            </p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {exposures.map((e) => (
                <li
                  key={e.ceo_exception_id}
                  className="flex items-center justify-between gap-3 rounded-panel border border-divider bg-surface p-3"
                >
                  <div>
                    <div className="text-body text-text">
                      Package {e.package_id.slice(0, 8)}
                    </div>
                    <div className="text-secondary text-text-secondary">
                      Exception {e.ceo_exception_id.slice(0, 8)}
                    </div>
                  </div>
                  <StatusBadge tone="danger" label="Below floor" />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-panel border border-divider">
        <table
          className="w-full text-body"
          aria-label="GM by SOW"
          data-testid="margin-by-sow"
        >
          <thead className="bg-primary-subtle/40">
            <tr className="text-left text-secondary text-text-secondary">
              <th className="px-3 py-2 font-medium">Deal</th>
              <th className="px-3 py-2 font-medium">Engagement</th>
              <th className="px-3 py-2 font-medium text-right">Revenue</th>
              <th className="px-3 py-2 font-medium text-right">Cost</th>
              <th className="px-3 py-2 font-medium text-right">GM US</th>
              <th className="px-3 py-2 font-medium text-right">GM India</th>
              <th className="px-3 py-2 font-medium">Approved?</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-3 py-6 text-center text-text-secondary"
                >
                  No verified source
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.gm_model_id} className="border-t border-divider">
                  <td className="px-3 py-3 align-top text-text">
                    {r.hubspot_deal_id}
                  </td>
                  <td className="px-3 py-3 align-top text-text-secondary">
                    {r.engagement_type}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <MoneyCell value={r.revenue ?? undefined} />
                  </td>
                  <td className="px-3 py-3 align-top">
                    <MoneyCell value={r.cost ?? undefined} />
                  </td>
                  <td className="px-3 py-3 align-top">
                    <MarginCell
                      value={formatPct(r.gm_us) ?? undefined}
                      outcome={
                        r.gm_us === null
                          ? "unavailable"
                          : Number(r.gm_us) >= 0.35
                            ? "pass"
                            : "fail"
                      }
                    />
                  </td>
                  <td className="px-3 py-3 align-top">
                    <MarginCell
                      value={formatPct(r.gm_india) ?? undefined}
                      outcome={
                        r.gm_india === null
                          ? "unavailable"
                          : Number(r.gm_india) >= 0.5
                            ? "pass"
                            : "fail"
                      }
                    />
                  </td>
                  <td className="px-3 py-3 align-top">
                    <StatusBadge
                      tone={r.approved ? "ok" : "warn"}
                      label={r.approved ? "Approved" : "Draft"}
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
          data-testid="export-margin-csv"
          onClick={() =>
            onExport?.({
              kind: "margin",
              format: "csv",
              filename: buildExportFilename("margin", "csv"),
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
