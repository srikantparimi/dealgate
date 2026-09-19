/**
 * Actuals tab (spec §15). Period picker + import status; reconciled
 * revenue/cost/GM come from the server per SOW. Actions surfaced:
 * Upload · preview/match · resolve exceptions · approve reconciliation ·
 * inspect source. Partially-reconciled periods stay labelled so a
 * silent completion state is impossible.
 *
 * Duplicate postings are prevented server-side by source keys — the UI
 * only labels the outcome (spec §15 "prevent duplicate postings").
 */

import { useMemo } from "react";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import type { ActualBatch } from "../../../api/client";

export interface ActualsTabProps {
  /** ISO month string, e.g. "2026-09". Controlled by the parent so the
   *  filter chip in the header stays in sync with the tab. */
  periodMonth: string;
  onPeriodChange: (periodMonth: string) => void;
  batches: ActualBatch[];
  /** Only Finance and SystemAdmin see the primary Upload action — the
   *  server independently enforces it (CLAUDE.md rule 5). */
  canUpload: boolean;
  onUpload?: () => void;
  reconciliation?: {
    revenue: string | null;
    cost: string | null;
    gm: string | null;
    rowsTotal: number;
    rowsReconciled: number;
    exceptionsCount: number;
  } | null;
}

function batchTone(status: string): StatusTone {
  if (status === "committed") return "ok";
  if (status === "validated") return "primarySubtle";
  if (status === "failed") return "danger";
  return "warn";
}

function batchLabel(status: string): string {
  if (status === "committed") return "Committed";
  if (status === "validated") return "Validated";
  if (status === "failed") return "Failed";
  if (status === "uploading") return "Uploading";
  return status;
}

export function ActualsTab({
  periodMonth,
  onPeriodChange,
  batches,
  canUpload,
  onUpload,
  reconciliation,
}: ActualsTabProps) {
  const partial = useMemo(() => {
    if (!reconciliation) return false;
    return reconciliation.rowsReconciled < reconciliation.rowsTotal;
  }, [reconciliation]);

  return (
    <section aria-label="Period actuals" className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="actuals-period"
            className="text-secondary text-text-secondary uppercase tracking-wide"
          >
            Reconciliation period
          </label>
          <Input
            id="actuals-period"
            type="month"
            value={periodMonth}
            onChange={(e) => onPeriodChange(e.target.value)}
            className="w-40 tnum"
            aria-label="Reconciliation period"
          />
        </div>
        {canUpload ? (
          <Button
            type="button"
            onClick={onUpload}
            data-testid="actuals-upload-primary"
          >
            Upload actuals
          </Button>
        ) : (
          <span className="text-secondary text-text-secondary">
            Only Finance and SystemAdmin can post actuals.
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Summary
          label="Reconciled revenue"
          value={reconciliation?.revenue ?? null}
        />
        <Summary label="Reconciled cost" value={reconciliation?.cost ?? null} />
        <Summary label="Reconciled GM" value={reconciliation?.gm ?? null} />
      </div>

      {reconciliation ? (
        <div
          className="rounded-panel border border-divider bg-surface p-4"
          data-testid="reconciliation-summary"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-body text-text">
              {reconciliation.rowsReconciled} of {reconciliation.rowsTotal}{" "}
              rows reconciled
            </div>
            <div className="flex gap-2">
              {partial ? (
                <StatusBadge
                  tone="warn"
                  label={`Partially reconciled · ${reconciliation.exceptionsCount} exception(s)`}
                />
              ) : (
                <StatusBadge tone="ok" label="Fully reconciled" />
              )}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" type="button">
              Preview / match
            </Button>
            <Button variant="secondary" size="sm" type="button">
              Resolve exceptions
            </Button>
            <Button variant="secondary" size="sm" type="button">
              Approve reconciliation
            </Button>
            <Button variant="tertiary" size="sm" type="button">
              Inspect source
            </Button>
          </div>
        </div>
      ) : null}

      <div>
        <h2 className="text-section text-text">Import status</h2>
        <p className="mt-1 text-secondary text-text-secondary">
          Duplicate postings are prevented server-side by source keys. Failed
          batches surface every rejected row.
        </p>
        {batches.length === 0 ? (
          <div className="mt-3">
            <EmptyState
              title="No actuals batches yet"
              description="Uploads become batches with per-row validation before commit."
            />
          </div>
        ) : (
          <ul
            className="mt-3 flex flex-col gap-2"
            data-testid="actuals-batches"
          >
            {batches.map((b) => (
              <li
                key={b.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-divider bg-surface p-3"
                data-testid={`actuals-batch-${b.id}`}
              >
                <div className="flex flex-col">
                  <span className="text-body text-text">Batch {b.id.slice(0, 8)}</span>
                  <span className="text-secondary text-text-secondary tnum">
                    {b.row_count} row(s)
                  </span>
                </div>
                <StatusBadge tone={batchTone(b.status)} label={batchLabel(b.status)} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function Summary({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
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
