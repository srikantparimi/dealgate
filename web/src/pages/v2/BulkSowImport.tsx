/**
 * Bulk SOW import (`/settings/data-imports/sows`) — S10-02.
 *
 * A ZIP or a set of PDFs lands here; the server drives each file
 * through the shared upload pipeline (same code path the single-file
 * upload uses). The queue table shows what happened per file, the
 * right-side summary shows totals + a CSV log download + a re-run
 * button.
 *
 * Legacy imports never fabricate approvals. The `governance_status`
 * lands as `legacy_not_evidenced` on the sow_version and a "Legacy"
 * chip appears on every record surface (SowBoard cards, Command
 * Center delivery-economics, client detail, renewals, reporting
 * exports).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  downloadBulkImportLog,
  getBulkImportBatch,
  getBulkImportFiles,
  rerunBulkImport,
  startBulkImport,
  type BulkImportBatchSummary,
  type BulkImportFileRow,
} from "../../api/client";
import { getIdTokenClaims } from "../../auth/cognito";
import { DeletionConfirmationDialog } from "../../ui-v2/DeletionConfirmationDialog";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge, type StatusTone } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";

/**
 * Server-enforced delete roles (mirror of
 * `api/app/routers/deletion.py::_DELETE_ROLES`). Hiding the button is
 * UX only — the server enforces the same list on the DELETE endpoint.
 */
const DELETE_ROLES: readonly string[] = [
  "SystemAdmin",
  "CEO",
  "SalesLeader",
  "Finance",
  "Legal",
];

function userCanDelete(): boolean {
  const claims = getIdTokenClaims();
  const raw = claims?.["cognito:groups"];
  const groups = Array.isArray(raw) ? (raw as string[]) : [];
  return groups.some((g) => DELETE_ROLES.includes(g));
}

const STATUS_TONE: Record<string, StatusTone> = {
  queued: "neutral",
  extracting: "progress",
  classifying: "progress",
  matching_client: "progress",
  deriving_gm: "progress",
  needs_review: "warning",
  imported: "success",
  rejected: "danger",
  duplicate: "neutral",
};

function statusTone(status: string): StatusTone {
  return STATUS_TONE[status] ?? "neutral";
}

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export function BulkSowImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [batch, setBatch] = useState<BulkImportBatchSummary | null>(null);
  const [files, setFiles] = useState<BulkImportFileRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const canDelete = useMemo(() => userCanDelete(), []);
  const navigate = useNavigate();

  const load = useCallback(async (id: string) => {
    try {
      const [b, list] = await Promise.all([
        getBulkImportBatch(id),
        getBulkImportFiles(id),
      ]);
      setBatch(b);
      setFiles(list.items);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "failed to load batch",
      );
    }
  }, []);

  const onFilesPicked = useCallback(
    async (list: FileList | null) => {
      if (!list || list.length === 0) return;
      setUploading(true);
      setError(null);
      try {
        const res = await startBulkImport(Array.from(list));
        await load(res.batch_id);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "upload failed",
        );
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [load],
  );

  useEffect(() => {
    if (!batch) return;
    // Poll for progress while the batch is still processing.
    if (batch.status !== "processing") return;
    const t = window.setTimeout(() => void load(batch.id), 2000);
    return () => window.clearTimeout(t);
  }, [batch, load]);

  const onDownloadLog = useCallback(async () => {
    if (!batch) return;
    try {
      const blob = await downloadBulkImportLog(batch.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bulk-import-${batch.id}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "log download failed",
      );
    }
  }, [batch]);

  const onRerun = useCallback(async () => {
    if (!batch) return;
    try {
      const next = await rerunBulkImport(batch.id, []);
      setBatch(next);
      await load(batch.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "re-run failed",
      );
    }
  }, [batch, load]);

  const summary = useMemo(() => {
    if (!batch) return null;
    return [
      { label: "Queued", value: batch.queued_count },
      { label: "Needs review", value: batch.needs_review_count },
      { label: "Imported", value: batch.imported_count },
      { label: "Duplicate", value: batch.duplicate_count },
      { label: "Rejected", value: batch.rejected_count },
    ];
  }, [batch]);

  return (
    <div className="flex flex-col gap-6" data-testid="bulk-sow-import">
      <PageHeader
        title="Bulk SOW import"
        subtitle={
          "Drop live SOW PDFs (or a ZIP). Every file runs through the same " +
          "pipeline as a single upload. Imported records land as Legacy — " +
          "approval never evidenced — so nothing here fabricates a signed record."
        }
      />

      <div
        role="button"
        aria-label="Drop files or ZIP"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void onFilesPicked(e.dataTransfer.files);
        }}
        className="flex flex-col items-center justify-center gap-2 rounded-panel border-2 border-dashed border-divider bg-canvas p-6 text-body text-text-secondary hover:border-primary/40"
      >
        <span>Drop PDFs or one .zip archive, or click to choose</span>
        <span className="text-secondary">
          Accepted: application/pdf, application/zip
        </span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="application/pdf,application/zip,.pdf,.zip"
          className="hidden"
          onChange={(e) => void onFilesPicked(e.target.files)}
          data-testid="bulk-file-input"
        />
      </div>

      {uploading ? (
        <div role="status" className="text-body text-text-secondary">
          Uploading and driving the pipeline…
        </div>
      ) : null}

      {error ? (
        <ErrorState
          title="Bulk import error"
          description={error}
        />
      ) : null}

      {batch ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <section aria-label="Batch queue" data-testid="bulk-queue">
            <div className="overflow-x-auto rounded-panel border border-divider bg-surface">
              <table className="min-w-full text-body">
                <thead className="border-b border-divider bg-canvas/60">
                  <tr>
                    <Th>File</Th>
                    <Th>Size</Th>
                    <Th>Type</Th>
                    <Th>Status</Th>
                    <Th>Matched client</Th>
                    <Th>Confidence</Th>
                    <Th>Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr
                      key={f.id}
                      className="border-b border-divider last:border-0"
                      data-testid={`bulk-row-${f.id}`}
                    >
                      <td className="px-3 py-3 text-body text-text">
                        {f.filename}
                      </td>
                      <td className="px-3 py-3 text-body text-text-secondary tnum">
                        {humanBytes(f.size_bytes)}
                      </td>
                      <td className="px-3 py-3 text-body text-text-secondary">
                        {f.detected_type ?? "—"}
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge
                          tone={statusTone(f.status)}
                          label={f.status.replace(/_/g, " ")}
                          data-testid={`bulk-chip-${f.status}`}
                        />
                        {f.status === "imported" ||
                        f.status === "needs_review" ? (
                          <span className="ml-2 inline-block">
                            <StatusBadge tone="neutral" label="Legacy" />
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-3 text-body text-text-secondary">
                        {f.matched_client_id ?? "—"}
                      </td>
                      <td className="px-3 py-3 text-body text-text-secondary tnum">
                        {f.matched_confidence ?? "—"}
                      </td>
                      <td className="px-3 py-3">
                        {f.opportunity_id ? (
                          <Link
                            to={`/sows/new?jobId=${f.id}&opportunityId=${f.opportunity_id}`}
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
                  {files.length === 0 ? (
                    <tr>
                      <td
                        colSpan={7}
                        className="px-3 py-6 text-center text-body text-text-secondary"
                      >
                        No files in this batch.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>

          <aside
            aria-label="Batch summary"
            className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
            data-testid="bulk-summary"
          >
            <h2 className="text-section text-text">Batch summary</h2>
            <div className="grid grid-cols-2 gap-2">
              {summary?.map((s) => (
                <div key={s.label} className="rounded-panel bg-canvas p-3">
                  <p className="text-secondary uppercase tracking-wide text-text-secondary">
                    {s.label}
                  </p>
                  <p className="mt-1 text-metric text-text tnum">{s.value}</p>
                </div>
              ))}
            </div>
            <Button variant="secondary" onClick={onDownloadLog} data-testid="bulk-log-btn">
              Download log CSV
            </Button>
            <Button variant="secondary" onClick={onRerun} data-testid="bulk-rerun-btn">
              Run again
            </Button>
            {canDelete ? (
              <Button
                variant="destructive"
                onClick={() => setDeleteOpen(true)}
                data-testid="bulk-delete-btn"
              >
                Delete batch
              </Button>
            ) : null}
          </aside>
        </div>
      ) : null}

      {batch && canDelete ? (
        <DeletionConfirmationDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          kind="batch"
          id={batch.id}
          name={batch.id.slice(0, 8)}
          onConfirmed={() => {
            setDeleteOpen(false);
            navigate("/settings/data-imports");
          }}
        />
      ) : null}
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
