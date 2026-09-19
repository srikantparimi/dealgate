/**
 * Approval turnaround report (spec §17). Median + tail elapsed time,
 * outstanding age, function/owner, rework loops. We always publish the
 * clock basis and pauses — a "3-day median" without a basis is a
 * meaningless statistic (blueprint §2 non-negotiable: honest numbers).
 *
 * The current API does not yet expose turnaround aggregates — we
 * degrade to "No verified source" and never fabricate a median.
 */

import { SourceFreshness } from "../../../ui-v2/SourceFreshness";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { Button } from "../../../ui-v2/primitives/button";
import type { ExportHandler } from "./exports";
import { buildExportFilename } from "./exports";

export interface ApprovalTurnaroundReportProps {
  fetchedAt: Date | null;
  onExport?: ExportHandler;
}

export function ApprovalTurnaroundReport({
  fetchedAt,
  onExport,
}: ApprovalTurnaroundReportProps) {
  return (
    <section
      aria-label="Approval turnaround report"
      className="flex flex-col gap-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-primary-subtle/30 p-3">
        <SourceFreshness
          source="Approval workflow"
          asOf={fetchedAt ? fetchedAt.toLocaleString() : "Unknown"}
          basis="Clock basis: package submission to functional decision. Excludes pauses."
        />
      </div>

      <EmptyState
        title="No verified source"
        description="Approval turnaround aggregates require the server-side rollup. Median, tail, outstanding age, function/owner and rework loops will appear here once the /reports/turnaround endpoint is live."
      />

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-divider pt-3">
        <Button
          variant="secondary"
          size="sm"
          type="button"
          data-testid="export-turnaround-csv"
          onClick={() =>
            onExport?.({
              kind: "approval_turnaround",
              format: "csv",
              filename: buildExportFilename("approval_turnaround", "csv"),
              snapshot: null,
            })
          }
        >
          Export CSV
        </Button>
      </div>
    </section>
  );
}
