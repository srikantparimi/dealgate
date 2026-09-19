/**
 * Needs-review queue (`/work/needs-review`) — S10-02.
 *
 * Every ImportFile with `needs_you` true — a file the bulk pipeline
 * completed but that left one or more gaps a human must resolve.
 * Nothing else in the system waits on this queue; reviewers clear
 * rows one by one from here.
 *
 * We fetch every recent batch and flatten to the union of their
 * needs-review rows. The API keeps batches short-lived so this is
 * a cheap read for the pilot; when the corpus grows the query will
 * move server-side.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  getBulkImportBatch,
  getBulkImportFiles,
  type BulkImportFileRow,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";

export interface NeedsReviewQueueProps {
  /** One or more batch ids to hydrate — routed callers pass what
   *  they know; the page happily renders zero rows when none exist. */
  batchIds?: string[];
}

export function NeedsReviewQueuePage({ batchIds = [] }: NeedsReviewQueueProps) {
  const [rows, setRows] = useState<BulkImportFileRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(batchIds.length > 0);

  const load = useCallback(async () => {
    if (batchIds.length === 0) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(
        batchIds.map(async (id) => {
          try {
            await getBulkImportBatch(id);
            const list = await getBulkImportFiles(id);
            return list.items.filter((f) => f.needs_you);
          } catch (err) {
            if (err instanceof ApiError && err.status === 404) return [];
            throw err;
          }
        }),
      );
      setRows(results.flat());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "failed to load queue",
      );
    } finally {
      setLoading(false);
    }
  }, [batchIds]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4" data-testid="needs-review-queue">
      <PageHeader
        title="Needs review"
        subtitle={
          "Imported records that need one more human touch before they " +
          "roll forward. Every row shows the file and links to its " +
          "confirmation screen."
        }
      />

      {error ? (
        <ErrorState title="Cannot load queue" description={error} />
      ) : null}

      {loading ? (
        <div role="status" className="text-body text-text-secondary">
          Loading…
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing waiting on you"
          description="Imported records with unresolved gaps show up here."
        />
      ) : (
        <div className="overflow-x-auto rounded-panel border border-divider bg-surface">
          <table className="min-w-full text-body">
            <thead className="border-b border-divider bg-canvas/60">
              <tr>
                <Th>File</Th>
                <Th>Detected type</Th>
                <Th>Status</Th>
                <Th>Warnings</Th>
                <Th>Open</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-divider last:border-0"
                  data-testid={`needs-row-${r.id}`}
                >
                  <td className="px-3 py-3 text-text">{r.filename}</td>
                  <td className="px-3 py-3 text-text-secondary">
                    {r.detected_type ?? "—"}
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge
                      tone="warning"
                      label={r.status.replace(/_/g, " ")}
                    />
                    <span className="ml-2 inline-block">
                      <StatusBadge tone="neutral" label="Legacy" />
                    </span>
                  </td>
                  <td className="px-3 py-3 text-text-secondary">
                    {(r.warnings ?? []).slice(0, 2).map(String).join("; ") ||
                      "—"}
                  </td>
                  <td className="px-3 py-3">
                    {r.opportunity_id ? (
                      <Link
                        to={`/sows/new?jobId=${r.id}&opportunityId=${r.opportunity_id}`}
                        className="text-primary hover:underline"
                      >
                        Open record
                      </Link>
                    ) : (
                      <span className="text-text-secondary">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      scope="col"
      className="px-3 py-2 text-left text-secondary uppercase tracking-wide text-text-secondary font-medium"
    >
      {children}
    </th>
  );
}
