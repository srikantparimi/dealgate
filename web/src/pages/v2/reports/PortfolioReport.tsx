/**
 * Portfolio report (spec §17). Pipeline by stage · active signed work ·
 * decisions · delivery risk. Clicking a segment routes to the record
 * list — for now we surface counts + an inline bar chart, and defer
 * per-segment record navigation to the pipeline / SOWs pages already
 * built (the segment is an anchor).
 */

import type { CeoDashboard, FinanceDashboard, DealRow } from "../../../api/client";
import { BarChart, type BarChartDatum } from "./BarChart";
import { Button } from "../../../ui-v2/primitives/button";
import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface PortfolioReportProps {
  ceo: CeoDashboard | null;
  finance: FinanceDashboard | null;
  deals: DealRow[];
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

function stageCounts(deals: DealRow[]): BarChartDatum[] {
  const map = new Map<string, number>();
  for (const d of deals) {
    const s = d.sales_stage ?? "unknown";
    map.set(s, (map.get(s) ?? 0) + 1);
  }
  return Array.from(map.entries()).map(([label, value]) => ({
    label: label.replace(/_/g, " "),
    value,
    display: String(value),
  }));
}

export function PortfolioReport({
  ceo,
  finance,
  deals,
  fetchedAt,
  onExport,
}: PortfolioReportProps) {
  const bars = stageCounts(deals);
  const includedCount = deals.length;
  const excludedCount = 0;
  const snapshot = {
    included: includedCount,
    excluded: excludedCount,
    stages: bars,
    ceoExceptions: ceo?.ceo_exceptions_pending.length ?? null,
    forecastGp: finance?.approved_vs_forecast_vs_actual.forecast_gp ?? null,
  };

  return (
    <section aria-label="Portfolio report" className="flex flex-col gap-4">
      <ReportMeta
        included={includedCount}
        excluded={excludedCount}
        basis="Pipeline stages from governance"
        fetchedAt={fetchedAt}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-section text-text">Pipeline by stage</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            Deals grouped by their current sales stage. Click a stage to open
            the pipeline list filtered accordingly.
          </p>
          <div className="mt-3">
            <BarChart
              data={bars}
              ariaLabel="Pipeline deals by stage"
              emptyLabel="No pipeline records"
            />
          </div>
        </div>
        <div>
          <h3 className="text-section text-text">Governance signal</h3>
          <dl className="mt-3 grid grid-cols-2 gap-y-2 rounded-panel border border-divider bg-surface p-4 text-body">
            <dt className="text-text-secondary">CEO exceptions pending</dt>
            <dd className="tnum text-text text-right">
              {ceo?.ceo_exceptions_pending.length ?? "Unavailable"}
            </dd>
            <dt className="text-text-secondary">Forecast GP</dt>
            <dd className="tnum text-text text-right">
              {finance?.approved_vs_forecast_vs_actual.forecast_gp ??
                "Unavailable"}
            </dd>
            <dt className="text-text-secondary">Active signed deals</dt>
            <dd className="tnum text-text text-right">
              {deals.filter((d) => d.governance_status === "released").length}
            </dd>
          </dl>
        </div>
      </div>
      <ExportRow
        kind="portfolio"
        snapshot={snapshot}
        onExport={onExport}
      />
    </section>
  );
}

function ReportMeta({
  included,
  excluded,
  basis,
  fetchedAt,
}: {
  included: number;
  excluded: number;
  basis: string;
  fetchedAt: Date | null;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
      <SourceFreshness
        source="DealGate governance"
        asOf={fetchedAt ? fetchedAt.toLocaleString() : "Unknown"}
        basis={basis}
      />
      <div className="text-secondary text-text-secondary">
        Included: <span className="tnum text-text">{included}</span> · Excluded:{" "}
        <span className="tnum text-text">{excluded}</span>
      </div>
    </div>
  );
}

function ExportRow({
  kind,
  snapshot,
  onExport,
}: {
  kind: "portfolio";
  snapshot: unknown;
  onExport?: ExportHandler;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 border-t border-divider pt-3">
      <Button
        variant="secondary"
        size="sm"
        type="button"
        data-testid="export-portfolio-csv"
        onClick={() =>
          onExport?.({
            kind,
            format: "csv",
            filename: buildExportFilename(kind, "csv"),
            snapshot,
          })
        }
      >
        Export CSV
      </Button>
      <Button
        variant="secondary"
        size="sm"
        type="button"
        data-testid="export-portfolio-pdf"
        onClick={() =>
          onExport?.({
            kind,
            format: "pdf",
            filename: buildExportFilename(kind, "pdf"),
            snapshot,
          })
        }
      >
        Export PDF review pack
      </Button>
    </div>
  );
}
