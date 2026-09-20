/**
 * SOW version history — revise, delete, discard (S10-06).
 *
 * MSA and NDA are mother documents: one per legal entity, long-lived, with
 * their own state machine (`Agreement.state`, including `superseded`). A SOW
 * is per engagement and gets revised during negotiation, so it needs a
 * version chain instead — and, until now, had no way to use it.
 *
 * What was wrong: uploading a corrected SOW created a *second opportunity*
 * for the same engagement, because the upload path always created a new one.
 * And nothing in the API could remove a bad upload at all.
 *
 * Two different endings, because they are two different situations:
 *
 *   - **Delete** — the version never reached an approval package. A wrong
 *     file, a bad extraction, a test run. Nobody has relied on it, so it
 *     goes, and an audit row records that it existed and was removed.
 *   - **Discard** — the version has been submitted. Someone acted on it, so
 *     the row and the file stay; it just leaves every board. Required by
 *     CLAUDE.md rule 4: approval records are immutable.
 *
 * The server decides which applies (`can_delete` / `can_discard`) so the rule
 * is not re-derived here and cannot drift.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSowRevision,
  deleteSowVersion,
  discardSowVersion,
  listSowVersions,
  type SowVersionRow,
  type UUID,
} from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import { EmptyState } from "../../../ui-v2/EmptyState";

export function versionTone(v: SowVersionRow): StatusTone {
  if (v.discarded_at) return "neutral";
  if (v.is_current) return "ok";
  return "neutral";
}

export function versionLabel(v: SowVersionRow): string {
  if (v.discarded_at) return "discarded";
  if (v.is_current) return "current";
  return "superseded";
}

export interface SowVersionHistoryProps {
  opportunityId: UUID;
  /** Injectable for tests; defaults to the real loader. */
  load?: typeof listSowVersions;
}

export function SowVersionHistory({
  opportunityId,
  load = listSowVersions,
}: SowVersionHistoryProps) {
  const [rows, setRows] = useState<SowVersionRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await load(opportunityId);
      setRows(res.versions);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not load versions");
    }
  }, [opportunityId, load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "that did not work");
    } finally {
      setBusy(false);
    }
  }

  function handleUpload(file: File) {
    void withBusy(async () => {
      await createSowRevision(opportunityId, file);
      if (fileRef.current) fileRef.current.value = "";
    });
  }

  function handleDelete(v: SowVersionRow) {
    // Irreversible, so it asks. Discard does not — that one is recoverable.
    const reason = window.prompt(
      `Delete version ${v.version_no}? This cannot be undone.\n\nReason (optional):`,
    );
    if (reason === null) return;
    void withBusy(async () => {
      await deleteSowVersion(v.id, reason || undefined);
    });
  }

  function handleDiscard(v: SowVersionRow) {
    // A reason is required: a discarded SOW leaves every board, and months
    // later this sentence is the only explanation anyone will have.
    const reason = window.prompt(
      `Discard version ${v.version_no}? It stays in the record but leaves every board.\n\nReason (required):`,
    );
    if (!reason || !reason.trim()) return;
    void withBusy(async () => {
      await discardSowVersion(v.id, reason.trim());
    });
  }

  return (
    <section data-testid="sow-version-history" className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-heading-4">SOW versions</h3>
          <p className="text-secondary text-text-secondary">
            A revision becomes the next version of this SOW — it never creates a
            second opportunity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            data-testid="new-version"
          >
            {busy ? "Working…" : "New version"}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf,.docx"
            className="hidden"
            data-testid="version-file-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
            }}
          />
        </div>
      </div>

      {error ? (
        <p className="mb-3 text-secondary text-danger" data-testid="version-error">
          {error}
        </p>
      ) : null}

      {rows === null ? null : rows.length === 0 ? (
        <EmptyState
          title="No SOW uploaded yet"
          description="Upload a SOW and its versions will be listed here."
        />
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {rows.map((v) => (
            <li
              key={v.id}
              className="flex flex-wrap items-center gap-3 px-4 py-3"
              data-testid={`version-row-${v.version_no}`}
            >
              <span className="font-medium">v{v.version_no}</span>
              <StatusBadge tone={versionTone(v)} label={versionLabel(v)} />
              <span className="text-text-secondary">{v.file_name ?? "—"}</span>
              <span className="text-text-secondary">
                {v.uploaded_at ? v.uploaded_at.slice(0, 10) : ""}
              </span>
              {v.discard_reason ? (
                <span className="text-text-secondary italic">
                  {v.discard_reason}
                </span>
              ) : null}
              <span className="ml-auto flex items-center gap-2">
                {v.can_delete ? (
                  <button
                    type="button"
                    disabled={busy}
                    className="text-text-secondary hover:text-danger"
                    data-testid={`delete-${v.version_no}`}
                    onClick={() => handleDelete(v)}
                  >
                    Delete
                  </button>
                ) : null}
                {v.can_discard ? (
                  <button
                    type="button"
                    disabled={busy}
                    className="text-text-secondary hover:text-warning"
                    data-testid={`discard-${v.version_no}`}
                    onClick={() => handleDiscard(v)}
                  >
                    Discard
                  </button>
                ) : null}
                {!v.can_delete && !v.can_discard && !v.discarded_at ? (
                  // Submitted and already dealt with — nothing to offer, and
                  // saying why beats an unexplained absence of buttons.
                  <span className="text-text-secondary">in approval record</span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
