/**
 * Report export helpers (spec §17). Real CSV / PDF generation is a
 * server responsibility (definitions + data freshness metadata are
 * only trustworthy there). This module just packages the caller intent
 * so the wiring stays testable: each report page hands us a `kind`
 * plus a `payload` snapshot, we shape the download filename and
 * delegate the actual write to a caller-supplied handler.
 *
 * Scheduled report delivery uses verified recipients — that is a
 * server-side job trigger, not a client concern; documented here for
 * spec traceability.
 */

export type ReportKind =
  | "portfolio"
  | "margin"
  | "revenue"
  | "renewals"
  | "approval_turnaround";

export type ExportFormat = "csv" | "pdf";

export interface ExportHandlerArgs {
  kind: ReportKind;
  format: ExportFormat;
  filename: string;
  /** Snapshot the page already rendered — server will re-derive from
   *  authoritative sources but the snapshot documents what the user
   *  actually saw. */
  snapshot: unknown;
}

export type ExportHandler = (args: ExportHandlerArgs) => void | Promise<void>;

export function buildExportFilename(
  kind: ReportKind,
  format: ExportFormat,
): string {
  const stamp = new Date().toISOString().slice(0, 10);
  return `dealgate-${kind}-${stamp}.${format}`;
}
