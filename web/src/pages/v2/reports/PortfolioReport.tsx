/**
 * Portfolio report (spec §17, S20 L17/L18/T42 rework).
 *
 * Pipeline-by-stage now reads `stage_label` off pipeline opportunities
 * — the review's L17 finding was that this page displayed numeric
 * stage IDs. Rows without a label render under the `Unknown stage`
 * bucket rather than as a raw HubSpot stage id.
 *
 * Population/basis (T42): the top strip explicitly declares Included /
 * Excluded counts and why, and links to the report's basis (source
 * watermark + as-of).
 */

import type {
  CeoDashboard,
  DealRow,
  FinanceDashboard,
  PipelineOpportunityRow,
  PortfolioBasis,
} from "../../../api/client";
import { BarChart, type BarChartDatum } from "./BarChart";
import { Button } from "../../../ui-v2/primitives/button";
import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface PortfolioReportProps {
  ceo: CeoDashboard | null;
  finance: FinanceDashboard | null;
  deals: DealRow[];
  pipelineOpps: PipelineOpportunityRow[];
  basis: PortfolioBasis | null;
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

const UNKNOWN_STAGE_LABEL = "Unknown stage";

function stageCounts(opps: PipelineOpportunityRow[]): BarChartDatum[] {
  // L17/T42: chart labels are human stage names (`stage_label`), NEVER
  // numeric HubSpot ids. If a row is missing its label we bucket it as
  // `Unknown stage` so callers still see it — a silent drop would give
  // a wrong total.
  const map = new Map<string, number>();
  for (const o of opps) {
    const label = (o.stage_label ?? "").trim() || UNKNOWN_STAGE_LABEL;
    map.set(label, (map.get(label) ?? 0) + 1);
  }
  return Array.from(map.entries()).map(([label, value]) => ({
    label,
    value,
    display: String(value),
  }));
}

export function PortfolioReport({
  ceo,
  finance,
  deals,
  pipelineOpps,
  basis,
  fetchedAt,
  onExport,
}: PortfolioReportProps) {
  const bars = stageCounts(pipelineOpps);

  // Explicit population accounting (T42). Prefer basis returned by the
  // server so the numbers line up with the reconciler — fall back to
  // the fetched slice.
  const included = basis?.population.included ?? pipelineOpps.length;
  const excludedArchived = basis?.population.excluded_archived ?? 0;
  const excludedNonHubspot = basis?.population.excluded_non_hubspot ?? 0;
  const totalExcluded = excludedArchived + excludedNonHubspot;

  const snapshot = {
    included,
    excludedArchived,
    excludedNonHubspot,
    stages: bars,
    ceoExceptions: ceo?.ceo_exceptions_pending.length ?? null,
    forecastGp: finance?.approved_vs_forecast_vs_actual.forecast_gp ?? null,
    basis: basis?.basis ?? null,
  };

  const asOf = basis?.basis?.as_of
    ? new Date(basis.basis.as_of).toLocaleString()
    : fetchedAt
      ? fetchedAt.toLocaleString()
      : "Unknown";

  const reconcileAt =
    basis?.basis?.watermarks?.hubspot_reconcile?.last_success_at ?? null;

  return (
    <section aria-label="Portfolio report" className="flex flex-col gap-4">
      <ReportMeta
        included={included}
        excludedArchived={excludedArchived}
        excludedNonHubspot={excludedNonHubspot}
        basis={
          reconcileAt
            ? `Pipeline stages via HubSpot mirror. Last reconcile: ${new Date(
                reconcileAt,
              ).toLocaleString()}.`
            : "Pipeline stages via HubSpot mirror. Reconcile watermark unavailable."
        }
        asOf={asOf}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-section text-text">Pipeline by stage</h3>
          <p className="mt-1 text-secondary text-text-secondary">
            Deals grouped by their current sales stage. Labels are human names
            resolved from the HubSpot pipeline mirror; rows missing a label
            appear under {UNKNOWN_STAGE_LABEL}.
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

      {totalExcluded > 0 ? (
        <div
          className="rounded-panel border border-divider bg-canvas p-3 text-body text-text-secondary"
          aria-label="Excluded records reasons"
        >
          <p className="text-text font-medium">Excluded from this report</p>
          <ul className="mt-1 list-disc pl-5 tnum">
            {excludedArchived > 0 ? (
              <li>
                <span className="text-text">{excludedArchived}</span> archived
                HubSpot deal(s). Reason:{" "}
                {basis?.population.reasons.excluded_archived ??
                  "source=hubspot AND archived_at IS NOT NULL"}
                .
              </li>
            ) : null}
            {excludedNonHubspot > 0 ? (
              <li>
                <span className="text-text">{excludedNonHubspot}</span>{" "}
                non-HubSpot opportunity(ies). Reason:{" "}
                {basis?.population.reasons.excluded_non_hubspot ??
                  "source != 'hubspot' (SOW-first / imported)"}
                .
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}

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
  excludedArchived,
  excludedNonHubspot,
  basis,
  asOf,
}: {
  included: number;
  excludedArchived: number;
  excludedNonHubspot: number;
  basis: string;
  asOf: string;
}) {
  const totalExcluded = excludedArchived + excludedNonHubspot;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
      <SourceFreshness
        source="DealGate HubSpot mirror"
        asOf={asOf}
        basis={basis}
      />
      <div className="text-secondary text-text-secondary">
        Included: <span className="tnum text-text">{included}</span> · Excluded:{" "}
        <span className="tnum text-text">{totalExcluded}</span>
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
