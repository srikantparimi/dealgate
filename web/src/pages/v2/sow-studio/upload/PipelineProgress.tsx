/**
 * S10-01 — the "Deriving your SOW" status card.
 *
 * Polls ``GET /sows/jobs/{id}`` every 1500ms with an ``AbortController``
 * so navigating away cancels the in-flight request cleanly. When the
 * job flips to ``needs_pick`` the enclosing flow renders the
 * :class:`ClientPickerModal`; when it flips to ``done`` the flow
 * navigates to ``/sows/new?opportunityId=<id>``. Failures surface an
 * error banner + a Retry button that re-fires the initial upload.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import {
  getSowJob,
  type SowUploadJobResponse,
  type SowUploadJobStatus,
} from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Section } from "../confirmation/Section";

const POLL_INTERVAL_MS = 1500;

interface Row {
  status: SowUploadJobStatus | "queued";
  label: string;
}

const ROWS: Row[] = [
  { status: "queued", label: "Uploading" },
  { status: "extracting", label: "Extracting" },
  { status: "classifying", label: "Classifying" },
  { status: "matching_client", label: "Matching client" },
  { status: "deriving_gm", label: "Deriving GM" },
];

const STATUS_ORDER: SowUploadJobStatus[] = [
  "queued",
  "extracting",
  "classifying",
  "matching_client",
  "deriving_gm",
  "done",
];

function stateFor(
  jobStatus: SowUploadJobStatus,
  row: SowUploadJobStatus | "queued",
): "pending" | "current" | "done" {
  const rowIdx = STATUS_ORDER.indexOf(row as SowUploadJobStatus);
  const jobIdx = STATUS_ORDER.indexOf(jobStatus);
  if (jobStatus === "done") return "done";
  if (jobStatus === "needs_pick") {
    // Needs-pick pauses at matching_client — render every earlier row
    // as done and matching_client as current so the reviewer sees where
    // the pipeline stopped.
    if (row === "queued" || row === "extracting" || row === "classifying") {
      return "done";
    }
    if (row === "matching_client") return "current";
    return "pending";
  }
  if (jobStatus === "failed") {
    if (rowIdx < jobIdx) return "done";
    return "pending";
  }
  if (rowIdx < jobIdx) return "done";
  if (rowIdx === jobIdx) return "current";
  return "pending";
}

export interface PipelineProgressProps {
  jobId: string;
  onNeedsPick: (job: SowUploadJobResponse) => void;
  onDone: (job: SowUploadJobResponse) => void;
  onRetry: () => void;
}

export function PipelineProgress({
  jobId,
  onNeedsPick,
  onDone,
  onRetry,
}: PipelineProgressProps) {
  const [job, setJob] = useState<SowUploadJobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Latest handlers via a ref so the polling loop never captures a
  // stale callback (the flow re-renders when the URL changes).
  const handlersRef = useRef({ onNeedsPick, onDone });
  handlersRef.current = { onNeedsPick, onDone };

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function poll() {
      while (!cancelled) {
        try {
          const next = await getSowJob(jobId);
          if (cancelled) return;
          setJob(next);
          setError(null);
          if (next.status === "needs_pick") {
            handlersRef.current.onNeedsPick(next);
            return;
          }
          if (next.status === "done") {
            handlersRef.current.onDone(next);
            return;
          }
          if (next.status === "failed") {
            setError(next.error ?? "Pipeline failed");
            return;
          }
        } catch (e) {
          if (cancelled) return;
          setError(e instanceof Error ? e.message : "Poll failed");
          // Back-off is unnecessary — user can hit Retry.
          return;
        }
        await new Promise<void>((resolve) => {
          const t = setTimeout(resolve, POLL_INTERVAL_MS);
          controller.signal.addEventListener("abort", () => {
            clearTimeout(t);
            resolve();
          });
        });
      }
    }

    void poll();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jobId]);

  const status: SowUploadJobStatus = job?.status ?? "queued";

  const rows = useMemo(() => ROWS, []);

  return (
    <Section
      id="section-pipeline"
      title="Deriving your SOW"
      description="Every step writes an audit event. This card polls every 1.5s."
    >
      <ol className="flex flex-col gap-3" data-testid="pipeline-rows">
        {rows.map((row) => {
          const state = stateFor(status, row.status);
          return (
            <li
              key={row.status}
              className="flex items-center gap-3"
              data-testid={`pipeline-row-${row.status}`}
              data-state={state}
            >
              <span aria-hidden className="flex h-6 w-6 items-center justify-center">
                {state === "done" ? (
                  <Check className="h-4 w-4 text-success" />
                ) : state === "current" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <span className="h-2 w-2 rounded-full bg-divider" />
                )}
              </span>
              <span className="text-body text-text">{row.label}</span>
              {state === "current" ? (
                <span className="text-secondary text-text-secondary">— in progress</span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {error ? (
        <div
          role="alert"
          data-testid="pipeline-error"
          className="mt-3 flex items-center gap-2 rounded-panel border border-danger/40 bg-danger-surface p-3 text-danger"
        >
          <AlertCircle className="h-4 w-4" aria-hidden />
          <span className="flex-1">{error}</span>
          <Button
            type="button"
            variant="ghost"
            onClick={onRetry}
            data-testid="pipeline-retry"
          >
            Retry
          </Button>
        </div>
      ) : null}
    </Section>
  );
}
