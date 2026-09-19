/**
 * Revenue report (spec §17). Contracted value · forecast revenue ·
 * period recognized revenue · backlog. Invoice/cash are shown ONLY if
 * sourced — spec §17 forbids combining them under a single "Revenue"
 * heading, and this component surfaces the caveat by default.
 *
 * The caveat renders even when the sourcing flags return "unknown" so a
 * missing configuration cannot silently imply "sourced".
 */

import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import { Button } from "../../../ui-v2/primitives/button";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface RevenueSourcing {
  invoiceSourced: boolean;
  cashSourced: boolean;
}

export interface RevenueReportProps {
  contractedValue: string | null;
  forecastRevenue: string | null;
  recognizedRevenue: string | null;
  backlog: string | null;
  sourcing: RevenueSourcing;
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

export function RevenueReport({
  contractedValue,
  forecastRevenue,
  recognizedRevenue,
  backlog,
  sourcing,
  fetchedAt,
  onExport,
}: RevenueReportProps) {
  const snapshot = {
    contractedValue,
    forecastRevenue,
    recognizedRevenue,
    backlog,
    sourcing,
  };
  return (
    <section aria-label="Revenue report" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
        <SourceFreshness
          source="Governance + Finance"
          asOf={fetchedAt ? fetchedAt.toLocaleString() : "Unknown"}
          basis="Contracted, forecast and recognized shown as separate lines."
        />
      </div>

      <div
        className="rounded-panel border border-warning/40 bg-warning-surface p-3"
        role="note"
        data-testid="revenue-invoice-cash-caveat"
      >
        <div className="flex items-start gap-2">
          <StatusBadge tone="warn" label="Basis" />
          <p className="text-body text-text">
            Invoice and cash are shown only when sourced by an authoritative
            system. They are never combined with contracted, forecast or
            recognized revenue under a single &ldquo;Revenue&rdquo; heading.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Line label="Contracted value" value={contractedValue} />
        <Line label="Forecast revenue" value={forecastRevenue} />
        <Line label="Period recognized revenue" value={recognizedRevenue} />
        <Line label="Backlog" value={backlog} />
        <SourcedLine
          label="Invoice"
          sourced={sourcing.invoiceSourced}
          value={null}
        />
        <SourcedLine
          label="Cash"
          sourced={sourcing.cashSourced}
          value={null}
        />
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-divider pt-3">
        <Button
          variant="secondary"
          size="sm"
          type="button"
          data-testid="export-revenue-csv"
          onClick={() =>
            onExport?.({
              kind: "revenue",
              format: "csv",
              filename: buildExportFilename("revenue", "csv"),
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

function Line({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <div className="mt-1 text-metric tnum text-text">
        {value ?? <span className="text-text-secondary">Unavailable</span>}
      </div>
    </div>
  );
}

function SourcedLine({
  label,
  sourced,
  value,
}: {
  label: string;
  sourced: boolean;
  value: string | null;
}) {
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="text-secondary text-text-secondary uppercase tracking-wide">
          {label}
        </span>
        <StatusBadge
          tone={sourced ? "ok" : "neutral"}
          label={sourced ? "Sourced" : "Not sourced"}
        />
      </div>
      <div className="mt-1 text-metric tnum text-text">
        {sourced && value ? (
          value
        ) : (
          <span className="text-text-secondary">No verified source</span>
        )}
      </div>
    </div>
  );
}
