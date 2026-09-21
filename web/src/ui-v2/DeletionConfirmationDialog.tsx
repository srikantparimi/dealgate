/**
 * Delete + archive confirmation dialog (S13a-FE).
 *
 * Governance directive:
 * `docs/directives/s13a-delete-reset.md` — delete is not one behavior. The
 * server-side assessment returns:
 *
 *  - ``draft``           → hard delete allowed; render a red primary Delete
 *                          button that lists every cascaded row count.
 *  - ``approved``        → hard delete refused; render the reason and offer
 *                          Archive instead. Approval trails are append-only
 *                          (blueprint §5), so we never destroy them.
 *  - ``hubspot_linked``  → hard delete refused; a live HubSpot deal would
 *                          resurrect the record on the next sync, so archive
 *                          also writes the governance status back to HubSpot.
 *
 * The confirmation text tells the truth (CLAUDE.md rule 11): the counts the
 * server returned are the counts we render. No hidden buttons and no button
 * whose label doesn't match what happens on click.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  archiveClient,
  archiveOpportunity,
  assessClientDeletion,
  assessOpportunityDeletion,
  deleteBulkImportBatch,
  deleteClient,
  deleteOpportunity,
  type DeletionAssessmentResponse,
  type DeletionState,
  type UUID,
} from "../api/client";
import { Button } from "./primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./primitives/dialog";

/** What kind of record the dialog operates on. */
export type DeletionKind = "client" | "opportunity" | "batch";

export interface DeletionConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: DeletionKind;
  /** Record id — client id, opportunity id, or import-batch id. */
  id: UUID;
  /** Human-readable label of the record (client name, deal id, batch name). */
  name: string;
  /** Fired after a successful delete or archive so the parent can refresh. */
  onConfirmed: (result: DeletionAssessmentResponse) => void;
}

/**
 * Human-readable row names for the cascade summary. Anything not in this
 * table falls back to the raw server key so a new backend column never
 * hides from the user — the dialog would just show ``foo_bars: 3``,
 * which is truthful if slightly ugly.
 */
const COUNT_LABELS: Record<string, { one: string; many: string }> = {
  clients: { one: "client", many: "clients" },
  client: { one: "client", many: "clients" },
  opportunities: { one: "opportunity", many: "opportunities" },
  opportunity: { one: "opportunity", many: "opportunities" },
  sows: { one: "SOW", many: "SOWs" },
  sow_versions: { one: "SOW version", many: "SOW versions" },
  sow_versions_deleted: { one: "SOW version", many: "SOW versions" },
  sow_upload_jobs: { one: "SOW upload job", many: "SOW upload jobs" },
  sow_version: { one: "SOW version", many: "SOW versions" },
  gm_models: { one: "GM model", many: "GM models" },
  gm_models_deleted: { one: "GM model", many: "GM models" },
  resource_lines: { one: "resource line", many: "resource lines" },
  cost_lines: { one: "cost line", many: "cost lines" },
  client_contacts: { one: "contact", many: "contacts" },
  client_aliases: { one: "alias", many: "aliases" },
  client_rate_cards: { one: "rate card", many: "rate cards" },
  client_rate_card_rows: { one: "rate card row", many: "rate card rows" },
  legal_entities: { one: "legal entity", many: "legal entities" },
  agreements: { one: "agreement", many: "agreements" },
  import_files: { one: "import file", many: "import files" },
  import_file_rows: { one: "import file row", many: "import file rows" },
  import_batches: { one: "import batch", many: "import batches" },
  skipped_approved: { one: "approved SOW (kept)", many: "approved SOWs (kept)" },
};

function labelFor(key: string, count: number): string {
  const entry = COUNT_LABELS[key];
  if (!entry) return key.replace(/_/g, " ");
  return count === 1 ? entry.one : entry.many;
}

/**
 * Server rows we never render on their own: `sow_versions_deleted` and
 * `gm_models_deleted` are counting the same rows we already reported
 * with a name; `sow_versions` is the count *before* the delete. Rendering
 * both would double-count the cascade for the user.
 */
const DUPLICATE_COUNT_KEYS = new Set(["sow_versions", "gm_models"]);

interface CascadeLine {
  key: string;
  count: number;
  label: string;
}

function cascadeLines(counts: Record<string, number>): CascadeLine[] {
  const out: CascadeLine[] = [];
  for (const [key, count] of Object.entries(counts)) {
    if (!count) continue;
    if (DUPLICATE_COUNT_KEYS.has(key)) continue;
    out.push({ key, count, label: labelFor(key, count) });
  }
  out.sort((a, b) => a.label.localeCompare(b.label));
  return out;
}

function titleFor(kind: DeletionKind, name: string): string {
  if (kind === "client") return `Delete client "${name}"?`;
  if (kind === "opportunity") return `Delete opportunity ${name}?`;
  return `Delete import batch ${name}?`;
}

function subtitleFor(kind: DeletionKind): string {
  if (kind === "client") {
    return (
      "Removes the client and every draft opportunity, SOW, GM model and " +
      "contact linked to it. Approved records archive instead of deleting."
    );
  }
  if (kind === "opportunity") {
    return (
      "Removes the opportunity and every draft SOW, GM model and staffing " +
      "line linked to it. Approved SOWs archive instead of deleting."
    );
  }
  return (
    "Removes every record this bulk-import batch produced. Any file that " +
    "reached approval keeps its own row and is reported as kept."
  );
}

async function callAssess(
  kind: DeletionKind,
  id: UUID,
): Promise<DeletionAssessmentResponse> {
  if (kind === "client") return assessClientDeletion(id);
  if (kind === "opportunity") return assessOpportunityDeletion(id);
  // Batch cleanup has no separate assessment endpoint — the server drives
  // the per-record checks on DELETE. Surface a synthetic "draft" so the
  // dialog can render a Delete button; the write path enforces the rules.
  return {
    state: "draft",
    reason: "bulk-import batch cleanup — per-file rules enforced on delete",
    counts: {},
  };
}

async function callDelete(
  kind: DeletionKind,
  id: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  if (kind === "client") return deleteClient(id, reason);
  if (kind === "opportunity") return deleteOpportunity(id, reason);
  return deleteBulkImportBatch(id);
}

async function callArchive(
  kind: DeletionKind,
  id: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  if (kind === "client") return archiveClient(id, reason);
  if (kind === "opportunity") return archiveOpportunity(id, reason);
  // Batches don't archive — the directive only defines a hard-delete
  // path for bulk-import cleanup. Surface a truthful error so no button
  // can lie about what it does (CLAUDE.md rule 11).
  throw new ApiError(
    400,
    null,
    "import batches cannot be archived; delete them or leave them in place",
  );
}

type Mode =
  | { phase: "loading" }
  | { phase: "assessed"; assessment: DeletionAssessmentResponse }
  | { phase: "working"; assessment: DeletionAssessmentResponse }
  | { phase: "error"; message: string };

export function DeletionConfirmationDialog({
  open,
  onOpenChange,
  kind,
  id,
  name,
  onConfirmed,
}: DeletionConfirmationDialogProps) {
  const [mode, setMode] = useState<Mode>({ phase: "loading" });
  const [reason, setReason] = useState<string>("");
  const [actionError, setActionError] = useState<string | null>(null);
  const requestId = useRef(0);

  const runAssessment = useCallback(async () => {
    const rid = ++requestId.current;
    setMode({ phase: "loading" });
    setActionError(null);
    try {
      const assessment = await callAssess(kind, id);
      if (requestId.current !== rid) return;
      setMode({ phase: "assessed", assessment });
    } catch (err) {
      if (requestId.current !== rid) return;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to assess deletion";
      setMode({ phase: "error", message });
    }
  }, [kind, id]);

  // Assess every time the dialog opens for a fresh record.
  useEffect(() => {
    if (!open) return;
    setReason("");
    setActionError(null);
    void runAssessment();
  }, [open, runAssessment]);

  const assessment =
    mode.phase === "assessed" || mode.phase === "working"
      ? mode.assessment
      : null;

  const lines = useMemo(
    () => (assessment ? cascadeLines(assessment.counts) : []),
    [assessment],
  );

  const canHardDelete: boolean = assessment?.state === "draft";
  const mustArchive: boolean =
    assessment?.state === "approved" || assessment?.state === "hubspot_linked";

  const performDelete = useCallback(async () => {
    if (!assessment) return;
    setActionError(null);
    setMode({ phase: "working", assessment });
    try {
      const result = await callDelete(
        kind,
        id,
        reason.trim() ? reason.trim() : undefined,
      );
      onConfirmed(result);
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Delete failed";
      setActionError(message);
      setMode({ phase: "assessed", assessment });
    }
  }, [assessment, kind, id, reason, onConfirmed, onOpenChange]);

  const performArchive = useCallback(async () => {
    if (!assessment) return;
    setActionError(null);
    setMode({ phase: "working", assessment });
    try {
      const result = await callArchive(
        kind,
        id,
        reason.trim() ? reason.trim() : undefined,
      );
      onConfirmed(result);
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Archive failed";
      setActionError(message);
      setMode({ phase: "assessed", assessment });
    }
  }, [assessment, kind, id, reason, onConfirmed, onOpenChange]);

  const working = mode.phase === "working";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby="deletion-dialog-body"
        data-testid="deletion-dialog"
      >
        <DialogHeader>
          <DialogTitle data-testid="deletion-dialog-title">
            {titleFor(kind, name)}
          </DialogTitle>
          <DialogDescription>{subtitleFor(kind)}</DialogDescription>
        </DialogHeader>

        <div
          id="deletion-dialog-body"
          className="flex flex-col gap-3 text-body text-text"
        >
          {mode.phase === "loading" ? (
            <p role="status" data-testid="deletion-loading">
              Checking approvals, HubSpot links and cascade counts…
            </p>
          ) : mode.phase === "error" ? (
            <div
              role="alert"
              data-testid="deletion-error"
              className="rounded-panel border border-danger/40 bg-danger/10 p-3 text-danger"
            >
              {mode.message}
            </div>
          ) : assessment ? (
            <>
              {canHardDelete ? (
                <CascadeSummary kind={kind} lines={lines} />
              ) : mustArchive ? (
                <ArchiveNotice
                  state={assessment.state}
                  serverReason={assessment.reason}
                  reason={reason}
                  onReasonChange={setReason}
                />
              ) : (
                <p role="status">
                  Result: <strong>{assessment.state}</strong> —{" "}
                  {assessment.reason}
                </p>
              )}

              {actionError ? (
                <div
                  role="alert"
                  data-testid="deletion-action-error"
                  className="rounded-panel border border-danger/40 bg-danger/10 p-3 text-danger"
                >
                  {actionError}
                </div>
              ) : null}
            </>
          ) : null}
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={working}
            data-testid="deletion-cancel"
          >
            Cancel
          </Button>
          {mode.phase === "error" ? (
            <Button
              variant="secondary"
              onClick={() => void runAssessment()}
              data-testid="deletion-retry"
            >
              Retry
            </Button>
          ) : null}
          {canHardDelete ? (
            <Button
              variant="destructive"
              onClick={() => void performDelete()}
              disabled={working}
              data-testid="deletion-confirm"
            >
              {working ? "Deleting…" : "Delete"}
            </Button>
          ) : null}
          {mustArchive ? (
            <Button
              variant="destructive"
              onClick={() => void performArchive()}
              disabled={working}
              data-testid="deletion-archive"
            >
              {working ? "Archiving…" : "Archive instead"}
            </Button>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface CascadeSummaryProps {
  kind: DeletionKind;
  lines: CascadeLine[];
}

function CascadeSummary({ kind, lines }: CascadeSummaryProps) {
  if (lines.length === 0) {
    return (
      <p data-testid="deletion-cascade-empty">
        Nothing cascades — this{" "}
        {kind === "client"
          ? "client"
          : kind === "opportunity"
            ? "opportunity"
            : "batch"}{" "}
        has no child records.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <p>This will delete:</p>
      <ul
        className="list-disc space-y-1 pl-6"
        data-testid="deletion-cascade-list"
      >
        {lines.map((line) => (
          <li key={line.key} data-testid={`deletion-cascade-${line.key}`}>
            <strong className="tnum">{line.count}</strong> {line.label}
          </li>
        ))}
      </ul>
      <p className="text-secondary text-text-secondary">
        The audit trail records the deletion; the deleted rows themselves are
        gone.
      </p>
    </div>
  );
}

interface ArchiveNoticeProps {
  state: DeletionState;
  serverReason: string;
  reason: string;
  onReasonChange: (v: string) => void;
}

function ArchiveNotice({
  state,
  serverReason,
  reason,
  onReasonChange,
}: ArchiveNoticeProps) {
  return (
    <div className="flex flex-col gap-3">
      <div
        role="alert"
        data-testid="deletion-cannot-delete"
        className="rounded-panel border border-danger/40 bg-danger/10 p-3 text-danger"
      >
        <p className="font-medium">Cannot delete.</p>
        <p className="mt-1 text-body">
          {state === "hubspot_linked"
            ? "Linked to a live HubSpot deal — hard-deleting would resurrect the record on the next sync. Archive instead; the governance status writes back to HubSpot."
            : "This record has an approval package or a signed SOW. Approval trails are append-only, so it can only be archived."}
        </p>
        <p
          className="mt-2 text-secondary"
          data-testid="deletion-server-reason"
        >
          Reason: {serverReason}
        </p>
      </div>
      <label className="flex flex-col gap-1 text-body">
        <span className="text-secondary text-text-secondary">
          Archive reason (optional)
        </span>
        <textarea
          className="min-h-[72px] rounded-control border border-input-border bg-surface p-2 text-body text-text focus-visible:outline-focus"
          value={reason}
          onChange={(e) => onReasonChange(e.target.value)}
          data-testid="deletion-archive-reason"
          placeholder="Why is this record being archived?"
        />
      </label>
    </div>
  );
}
