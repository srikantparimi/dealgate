// S23-PL2 F3 · the "Sync health" panel. It explains the freshness line and,
// for a SystemAdmin, runs the HubSpot deal sync now. The run keeps going on the
// server after CloudFront cuts the request at 30 s, so the panel never treats
// that request's 502/503/504, a network error or an abort as a failure: it
// says "Sync started" and polls GET /hubspot/sync-health until the server records
// an attempt newer than the latest one it reports at the click (read just before
// the run is started, so a run that ended after the page loaded is not taken for
// this one; both times are the server's, so a skewed browser clock does not
// matter; at most 10 minutes), then refetches the page. The errors of the last
// attempt are told in words: the server's reasons carry HubSpot ids and codes.
import { useEffect, useRef, useState } from "react";

import { ApiError, getSyncHealth, triggerHubspotSync, type SyncHealth } from "../../../api/client";
import type { Freshness } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { PipelineDrawer, type DrawerControlProps } from "./FilterToolbar";
import { pacificDateTime, plural } from "./format";

export const SYNC_POLL_MS = 5_000;
export const SYNC_POLL_LIMIT_MS = 10 * 60_000;

const RESULT: Record<Freshness["last_status"], string> = {
  ok: "Succeeded",
  partial: "Partly failed",
  failed: "Failed",
};

type Run =
  | { phase: "idle" }
  // Reading the server's latest attempt (the baseline); the run is started once it is known.
  | { phase: "starting"; since: number }
  | { phase: "started"; since: number; baseline: number }
  | { phase: "done"; status: Freshness["last_status"] }
  | { phase: "timeout" }
  | { phase: "refused"; message: string };

function attemptTime(f: Freshness | SyncHealth | null): number {
  const t = f?.last_attempt_at ? Date.parse(f.last_attempt_at) : NaN;
  return Number.isNaN(t) ? -Infinity : t;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function statusText(run: Run): string {
  switch (run.phase) {
    case "starting":
    case "started":
      return "Sync started";
    case "done":
      return `Sync finished · ${RESULT[run.status]}`;
    case "timeout":
      return "No result after 10 minutes. The sync may still be running; open this panel again later.";
    case "refused":
      return `The sync did not start: ${run.message}`;
    default:
      return "";
  }
}

/** How hubspot_backfill.py records a deal refused for a stage the stage map does not know. */
const UNMAPPED_STAGE = /^deal: stage .+ not mapped$/;

/**
 * The last attempt's errors as sentences for the reader, never the server's own text (it
 * carries HubSpot ids and technical codes). The server lists at most five errors and counts
 * them all: a stage the mapping does not know has the prototype's sentence, every other
 * reason one counted sentence, and errors beyond the list are counted as not listed.
 */
function syncErrorLines(f: Pick<Freshness, "errors" | "error_count" | "last_status">): string[] {
  const listed = (f.errors ?? []).map((e) => e.reason.trim()).filter(Boolean);
  const total = Math.max(f.error_count ?? listed.length, listed.length);
  const stages = listed.filter((reason) => UNMAPPED_STAGE.test(reason)).length;
  const others = listed.length - stages;
  const unlisted = total - listed.length;
  if (!stages) {
    return total ? [`${total} ${plural(total, "error", "errors")} in the last attempt.`] : [];
  }
  // Only a run that saved deals and refused nothing else saved "the other deals".
  const othersSaved = f.last_status === "partial" && stages === total;
  const lines = [
    `HubSpot returned a stage the mapping does not know (${stages} ${plural(stages, "deal", "deals")}).` +
      (othersSaved ? " The other deals were saved." : ""),
  ];
  if (others) lines.push(`${others} other ${plural(others, "error", "errors")} in the last attempt.`);
  if (unlisted) lines.push(`${unlisted} more ${plural(unlisted, "error", "errors")} not listed.`);
  return lines;
}

export interface SyncHealthPanelProps extends DrawerControlProps {
  freshness: Freshness;
  /** A SystemAdmin while recovery is available: shows "Run sync now". */
  canRunSync: boolean;
  /** After a run finishes: refetch the workspace (freshness, counts and rows). */
  onSynced: () => void;
}

export function SyncHealthPanel({
  open,
  onOpenChange,
  onCloseAutoFocus,
  freshness,
  canRunSync,
  onSynced,
}: SyncHealthPanelProps) {
  // Lives outside the drawer's content, so polling continues while the panel is closed.
  const [run, setRun] = useState<Run>({ phase: "idle" });
  const [polled, setPolled] = useState<SyncHealth | null>(null);
  const onSyncedRef = useRef(onSynced);
  useEffect(() => {
    onSyncedRef.current = onSynced;
  }, [onSynced]);

  useEffect(() => {
    if (run.phase !== "started") return;
    const { since, baseline } = run;
    let cancelled = false;
    let timer = 0;
    const poll = async () => {
      try {
        const health = await getSyncHealth();
        if (cancelled) return;
        setPolled(health);
        if (attemptTime(health) > baseline) {
          setRun({ phase: "done", status: health.last_status });
          onSyncedRef.current();
          return;
        }
      } catch {
        // A failed poll is not the sync's outcome; ask again.
      }
      if (cancelled) return;
      if (Date.now() - since >= SYNC_POLL_LIMIT_MS) {
        setRun({ phase: "timeout" });
        return;
      }
      timer = window.setTimeout(() => void poll(), SYNC_POLL_MS);
    };
    timer = window.setTimeout(() => void poll(), SYNC_POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [run]);

  async function runSyncNow() {
    const since = Date.now();
    setRun({ phase: "starting", since });
    // The baseline is the server's latest attempt now, not the one the page loaded with: a
    // run that ended since then (the nightly, another admin's) must not read as this one.
    // The page's own value stands in only when that read fails.
    let baseline: number;
    try {
      baseline = attemptTime(await getSyncHealth());
    } catch {
      baseline = Math.max(attemptTime(freshness), attemptTime(polled));
    }
    setRun({ phase: "started", since, baseline });
    // Not awaited: only the polled sync-health decides the outcome. A refusal
    // (401/403/409/422) is final and shown; gateway timeouts, network errors and
    // aborts are not failures of the sync.
    triggerHubspotSync().catch((err: unknown) => {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
        setRun((current) =>
          current.phase === "started" && current.since === since ? { phase: "refused", message: err.message } : current,
        );
      }
    });
  }

  const shown: Freshness = polled && attemptTime(polled) > attemptTime(freshness) ? polled : freshness;
  const errorLines = syncErrorLines(shown);
  const running = run.phase === "starting" || run.phase === "started";

  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      kicker="Trust & freshness"
      title="Sync health"
    >
      <dl className="grid grid-cols-2 gap-4 border-y border-border py-4">
        <div className="flex flex-col gap-1">
          <dt className="text-secondary text-text-secondary">Last successful sync</dt>
          <dd className="text-section text-text">{pacificDateTime(shown.last_success_at, "None recorded")}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-secondary text-text-secondary">Last attempt</dt>
          <dd className="text-section text-text">{pacificDateTime(shown.last_attempt_at, "None recorded")}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-secondary text-text-secondary">Last attempt result</dt>
          <dd className="text-section text-text">{RESULT[shown.last_status]}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-secondary text-text-secondary">Schedule</dt>
          <dd className="text-section text-text">{capitalise(shown.schedule)}</dd>
        </div>
      </dl>
      {errorLines.length ? (
        <div className="flex flex-col gap-1 rounded-control border-l-4 border-warning bg-warning-surface px-3 py-2 text-body text-warning">
          {errorLines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}
      <div className="flex flex-col gap-2 text-body text-text-secondary">
        <h3 className="text-section text-text">How to read this page</h3>
        <p>
          The line at the top of Pipeline shows the last <em>successful</em> sync of deals, not the last attempt. If a
          run fails, the previous good data stays and the warning says so. It clears only after a successful run.
        </p>
        <p>Recovery: an administrator can run the sync from this panel.</p>
      </div>
      {canRunSync ? (
        <div className="flex flex-col gap-2">
          <div>
            <Button onClick={() => void runSyncNow()} disabled={running}>
              Run sync now
            </Button>
          </div>
          {running ? (
            <p className="text-secondary text-text-secondary">The page updates when the sync finishes.</p>
          ) : null}
        </div>
      ) : null}
      <p role="status" className="text-body font-medium text-text">
        {statusText(run)}
      </p>
    </PipelineDrawer>
  );
}
