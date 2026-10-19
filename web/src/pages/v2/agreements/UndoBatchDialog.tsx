// S24-AG1 F4 · undo a batch. The count comes from the server (GET /agreements/batches/{label}); the undo
// is a job like the batch (202, then the browser polls until it is undone). Undo removes only the rows
// that batch attached and that are still standard copies; client copies, marks, the standard files,
// the cutover date and every relationship stay. Opened only for SystemAdmin (the page locks it).
import { useEffect, useRef, useState } from "react";

import { getBatch, undoBatch, type Batch } from "../../../api/agreements";
import { ApiError } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { AgreementsDrawer, useOpenSession } from "./UploadDialog";
import { AgreementNote, ProgressBar, errorText, pacificDate, plural, useSafeToast } from "./UploadForm";

export interface UndoBatchDialogProps {
  open: boolean;
  /** The batch label, e.g. AG-0001. */
  label: string | null;
  onOpenChange: (open: boolean) => void;
  onChanged: () => void;
}

/** How often a running batch or undo is polled. Tests shorten it. */
export const BATCH_POLL = { ms: 1500 };

/**
 * Polls GET /agreements/batches/{label} while `active` and the batch is running or undoing, and hands
 * every answer to `onBatch`. A failed poll is reported and retried; closing the dialog stops it.
 */
export function useBatchPolling(
  label: string | null,
  active: boolean,
  onBatch: (batch: Batch) => void,
  onError: (message: string | null) => void,
) {
  const onBatchRef = useRef(onBatch);
  const onErrorRef = useRef(onError);
  onBatchRef.current = onBatch;
  onErrorRef.current = onError;
  useEffect(() => {
    if (!active || !label) return;
    const ctl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = () => {
      getBatch(label, ctl.signal)
        .then((batch) => {
          if (ctl.signal.aborted) return;
          onErrorRef.current(null);
          onBatchRef.current(batch);
          if (batch.status === "running" || batch.status === "undoing") timer = setTimeout(tick, BATCH_POLL.ms);
        })
        .catch((err: unknown) => {
          if (ctl.signal.aborted) return;
          onErrorRef.current(errorText(err, "Progress could not be read. Trying again."));
          timer = setTimeout(tick, BATCH_POLL.ms * 2);
        });
    };
    timer = setTimeout(tick, BATCH_POLL.ms);
    return () => {
      ctl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [label, active]);
}

export function UndoBatchDialog(props: UndoBatchDialogProps) {
  const session = useOpenSession(props.open);
  return <UndoSession key={session} {...props} />;
}

function UndoSession({ open, label, onOpenChange, onChanged }: UndoBatchDialogProps) {
  const toast = useSafeToast();
  const [batch, setBatch] = useState<Batch | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollNote, setPollNote] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!open || !label) return;
    const ctl = new AbortController();
    setLoadError(null);
    getBatch(label, ctl.signal)
      .then((next) => {
        if (ctl.signal.aborted) return;
        setBatch(next);
        if (next.status === "undoing") setPolling(true);
      })
      .catch((err: unknown) => {
        if (!ctl.signal.aborted) setLoadError(errorText(err, `Batch ${label} could not load.`));
      });
    return () => ctl.abort();
  }, [open, label, reload]);

  const finished = (done: Batch) => {
    const n = done.undone_count;
    toast(
      typeof n === "number"
        ? `Batch ${done.id} undone: ${n} ${plural(n, "attachment", "attachments")} removed.`
        : `Batch ${done.id} undone.`,
    );
    onChanged();
    onOpenChange(false);
  };

  useBatchPolling(
    label,
    polling,
    (next) => {
      setBatch(next);
      if (next.status === "undoing") return;
      setPolling(false);
      if (next.status === "undone") finished(next);
      else
        setError(
          next.error || "The undo stopped before it finished. Press Undo again to finish removing the standard copies.",
        );
    },
    setPollNote,
  );

  async function submit() {
    if (!label || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const next = await undoBatch(label);
      setBatch(next);
      if (next.status === "undone") finished(next);
      else setPolling(true);
    } catch (err) {
      setError(errorText(err, `Batch ${label} could not be undone.`));
      // 409: it is already undone or undoing; show where it stands now.
      if (err instanceof ApiError && err.status === 409) setReload((n) => n + 1);
    } finally {
      setSubmitting(false);
    }
  }

  const id = batch?.id ?? label ?? "";
  // When the body changes under the person (confirm → undoing → error), focus moves to the title so a
  // keyboard user is not left on a control that is gone.
  const view = loadError ? "error" : !batch ? "loading" : polling || batch.status === "undoing" ? "undoing" : batch.status;
  const titleRef = useRef<HTMLHeadingElement>(null);
  const firstView = useRef(true);
  useEffect(() => {
    if (firstView.current) {
      firstView.current = false;
      return;
    }
    titleRef.current?.focus();
  }, [view]);
  let body;
  if (loadError) {
    body = (
      <div role="alert" className="flex flex-col items-start gap-2">
        <AgreementNote tone="warning">{loadError}</AgreementNote>
        <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
          Try again
        </Button>
      </div>
    );
  } else if (!batch) {
    body = (
      <p role="status" className="text-body text-text-secondary">
        {`Loading batch ${id}…`}
      </p>
    );
  } else if (polling || batch.status === "undoing") {
    body = (
      <div className="flex flex-col gap-2">
        <p className="text-body text-text">{`Removing the standard attachments made by batch ${id}…`}</p>
        <ProgressBar label="Undo progress" value={null} valueText="Undoing" />
        {pollNote ? <p className="text-secondary text-text-secondary">{pollNote}</p> : null}
      </div>
    );
  } else if (batch.status === "undone") {
    body = (
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">
          {`Batch ${id} was undone${batch.undone_by ? ` by ${batch.undone_by}` : ""}${
            batch.undone_at ? ` on ${pacificDate(batch.undone_at)}` : ""
          }.`}
        </p>
        <div>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </div>
    );
  } else if (batch.status === "running") {
    body = (
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">{`Batch ${id} is still running. You can undo it when it finishes.`}</p>
        <div>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </div>
    );
  } else {
    const n = batch.undo_would_remove;
    body = (
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">
          {typeof n === "number" ? (
            <>
              This removes the <strong>{n}</strong>
              {` standard ${plural(n, "attachment", "attachments")} made by batch ${id}.`}
            </>
          ) : (
            `This removes the standard attachments made by batch ${id} that are still in place.`
          )}{" "}
          It does not touch client copies, marks, or anything attached another way. The standard files and the cutover
          date stay.
        </p>
        {error ? (
          <p role="alert" className="text-secondary text-danger">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="destructive" onClick={() => void submit()} aria-busy={submitting || undefined}>
            Undo batch
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <AgreementsDrawer open={open} onOpenChange={onOpenChange} kicker="Undo" title={`Undo batch ${id}`} titleRef={titleRef}>
      {body}
    </AgreementsDrawer>
  );
}
