// S24-AG1 F4 · "Attach standard copies": the one-time backfill, in the prototype's three steps, backed by
// the server. Step 1 picks the standard copies (and can upload one). Step 2 is the server's dry run: the
// counts and a tickable list (existing clients and net-new clients past stage 1 start ticked; stage-1-only
// clients and test data start unticked with their reason). Step 3 re-runs the dry run with the final
// choices, so the typed "ATTACH n" is the server's own n, then starts the job (202) and polls it.
//
// One idempotency key per opening, so a double click or a retry returns the same batch; reopening while
// a batch runs shows its progress and never starts a second one (the server also answers 409).
// SystemAdmin only (the page locks the button; the server answers 403).
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import {
  AGREEMENT_KINDS,
  getAgreementsWorkspace,
  getStandardDocuments,
  listBatches,
  previewBatch,
  startBatch,
  type AgreementKind,
  type Batch,
  type BatchPreview,
  type BatchTarget,
  type StandardDocuments,
} from "../../../api/agreements";
import { ApiError, type UUID } from "../../../api/client";
import { cn } from "../../../lib/cn";
import { AgreementTag } from "../../../ui-v2/AgreementStateTag";
import { Button } from "../../../ui-v2/primitives/button";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { Input } from "../../../ui-v2/primitives/input";
import { useBatchPolling } from "./UndoBatchDialog";
import { AgreementsDrawer, useOpenSession } from "./UploadDialog";
import {
  AgreementNote,
  FIELD_LABEL,
  ProgressBar,
  UploadForm,
  calendarText,
  errorText,
  kindsText,
  pacificDate,
  plural,
} from "./UploadForm";

export interface AttachWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when a batch finished or a standard was uploaded from step 1, so the page refetches. */
  onChanged: () => void;
}

type Phase = "loading" | "error" | "steps" | "upload" | "running" | "done" | "failed" | "undone";
type Step = 1 | 2 | 3;

const STEP_LABELS = ["1 · Standard copies", "2 · Review", "3 · Confirm and run"] as const;

/** Batch.attached_clients is additive on the wire (agreement_status.batch_payload). */
type BatchWithClients = Batch & { attached_clients?: number };

function newKey(): string {
  return crypto.randomUUID();
}

function targetTag(target: BatchTarget): { text: string; tone: "progress" | "warning" } | null {
  if (target.reason === "test_data") return { text: "Test data", tone: "warning" };
  if (target.reason === "stage_1_only") return { text: "Deals only in stage 1", tone: "warning" };
  if (target.relationship === "net_new") return { text: "Net new · in pipeline", tone: "progress" };
  return null;
}

export function AttachWizard(props: AttachWizardProps) {
  const session = useOpenSession(props.open);
  return <WizardSession key={session} {...props} />;
}

function WizardSession({ open, onOpenChange, onChanged }: AttachWizardProps) {
  const ids = useId();
  const keyRef = useRef<string>(newKey());
  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [standard, setStandard] = useState<StandardDocuments | null>(null);
  const [undoingLabel, setUndoingLabel] = useState<string | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [chosen, setChosen] = useState<Record<AgreementKind, boolean>>({ NDA: false, MSA: false });
  const [preview, setPreview] = useState<BatchPreview | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [ticks, setTicks] = useState<Record<UUID, boolean>>({});
  const [confirm, setConfirm] = useState<BatchPreview | null>(null);
  const [typed, setTyped] = useState("");
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchWithClients | null>(null);
  const [pollNote, setPollNote] = useState<string | null>(null);
  const [cutover, setCutover] = useState<string | null>(null);
  const [uploadKind, setUploadKind] = useState<AgreementKind>("NDA");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [reload, setReload] = useState(0);
  const selection = useRef<{ include: UUID[]; exclude: UUID[] }>({ include: [], exclude: [] });
  const titleRef = useRef<HTMLHeadingElement>(null);
  const firstView = useRef(true);

  // Each step or state replaces the body: focus moves to the title so a keyboard user is never left on
  // a control that is gone (the prototype focuses the drawer's own control each time it redraws).
  useEffect(() => {
    if (phase === "loading") return;
    if (firstView.current) {
      firstView.current = false;
      return;
    }
    titleRef.current?.focus();
  }, [phase, step]);

  const chosenKinds = useMemo(() => AGREEMENT_KINDS.filter((k) => chosen[k]), [chosen]);
  const kindsKey = chosenKinds.join(",");

  // Open: a running batch takes over (F4 reopen); otherwise step 1 with the current standard copies.
  useEffect(() => {
    if (!open) return;
    let live = true;
    setPhase("loading");
    setLoadError(null);
    Promise.all([listBatches(), getStandardDocuments()])
      .then(([batches, docs]) => {
        if (!live) return;
        setStandard(docs);
        setChosen({ NDA: Boolean(docs.NDA), MSA: Boolean(docs.MSA) });
        const latest = batches.items[0];
        setUndoingLabel(latest?.status === "undoing" ? latest.id : null);
        if (latest?.status === "running") {
          setBatch(latest);
          setStep(3);
          setPhase("running");
        } else {
          setPhase("steps");
        }
      })
      .catch((err: unknown) => {
        if (!live) return;
        setLoadError(errorText(err, "The attach step could not load."));
        setPhase("error");
      });
    return () => {
      live = false;
    };
  }, [open, reload]);

  // Step 2: the server's dry run for the chosen kinds (again whenever the kinds change).
  const runPreview = useCallback(() => {
    if (!chosenKinds.length) return;
    setPreviewing(true);
    setPreviewError(null);
    previewBatch({ kinds: chosenKinds, include_net_new_past_stage_1: true })
      .then((next) => {
        setPreview(next);
        setPreviewKey(kindsKey);
        setTicks(Object.fromEntries(next.targets.map((t) => [t.client_id, t.included])));
      })
      .catch((err: unknown) => setPreviewError(errorText(err, "The dry run could not run.")))
      .finally(() => setPreviewing(false));
  }, [chosenKinds, kindsKey]);

  useEffect(() => {
    if (phase === "steps" && step === 2 && previewKey !== kindsKey && !previewing && !previewError) runPreview();
  }, [phase, step, previewKey, kindsKey, previewing, previewError, runPreview]);

  // The live counts while the admin ticks and unticks (anchored on the server's numbers).
  const counts = useMemo(() => {
    if (!preview) return null;
    let delta = 0;
    let netDelta = 0;
    for (const t of preview.targets) {
      const change = (ticks[t.client_id] ? 1 : 0) - (t.included ? 1 : 0);
      delta += change;
      if (t.relationship === "net_new") netDelta += change;
    }
    return {
      willReceive: preview.will_receive + delta,
      netIncluded: preview.net_new_included + netDelta,
      alreadyHold: preview.already_hold,
      netUntouched: Math.max(0, preview.net_new_untouched - netDelta),
    };
  }, [preview, ticks]);

  async function toConfirm() {
    if (!preview || previewing) return;
    const include = preview.targets.filter((t) => !t.included && ticks[t.client_id]).map((t) => t.client_id);
    const exclude = preview.targets.filter((t) => t.included && !ticks[t.client_id]).map((t) => t.client_id);
    selection.current = { include, exclude };
    setPreviewing(true);
    setPreviewError(null);
    try {
      const next = await previewBatch({
        kinds: chosenKinds,
        include_net_new_past_stage_1: true,
        include_client_ids: include,
        exclude_client_ids: exclude,
      });
      setConfirm(next);
      setTyped("");
      setRunError(null);
      setStep(3);
    } catch (err) {
      setPreviewError(errorText(err, "The dry run could not run."));
    } finally {
      setPreviewing(false);
    }
  }

  const missingStandard = chosenKinds.filter((k) => !standard?.[k]);
  const word = confirm ? `ATTACH ${confirm.will_receive}` : "";

  async function refreshConfirm() {
    try {
      const next = await previewBatch({
        kinds: chosenKinds,
        include_net_new_past_stage_1: true,
        include_client_ids: selection.current.include,
        exclude_client_ids: selection.current.exclude,
      });
      setConfirm(next);
      setTyped("");
    } catch {
      // The refusal message already says what to do.
    }
  }

  async function run() {
    if (!confirm || starting || typed.trim() !== word) return;
    setStarting(true);
    setRunError(null);
    try {
      const started = await startBatch({
        kinds: chosenKinds,
        include_net_new_past_stage_1: true,
        include_client_ids: selection.current.include,
        exclude_client_ids: selection.current.exclude,
        idempotency_key: keyRef.current,
        confirm: word,
      });
      followBatch(started);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // A batch is already running: follow it instead of starting a second one.
        try {
          const running = (await listBatches()).items.find((b) => b.status === "running");
          if (running) {
            followBatch(running);
            return;
          }
        } catch {
          // Fall through to the server's message.
        }
        setRunError(errorText(err, "A batch is already running."));
      } else {
        setRunError(errorText(err, "The batch could not start."));
        if (err instanceof ApiError && err.status === 422) void refreshConfirm();
      }
    } finally {
      setStarting(false);
    }
  }

  const loadCutover = () => {
    getAgreementsWorkspace({ page: 1, page_size: 25 })
      .then((ws) => setCutover(ws.cutover.date ?? null))
      .catch(() => setCutover(null));
  };

  function followBatch(next: BatchWithClients) {
    setBatch(next);
    setStep(3);
    if (next.status === "done") {
      setPhase("done");
      loadCutover();
      onChanged();
    } else if (next.status === "failed") {
      setPhase("failed");
      onChanged();
    } else if (next.status === "undoing" || next.status === "undone") {
      // Someone undid it while this dialog followed it.
      setPhase("undone");
      onChanged();
    } else {
      setPhase("running");
    }
  }

  useBatchPolling(
    batch?.id ?? null,
    phase === "running",
    (next) => {
      if (next.status === "running") {
        setBatch(next);
        return;
      }
      followBatch(next);
    },
    setPollNote,
  );

  function reviewAgain() {
    keyRef.current = newKey();
    setBatch(null);
    setConfirm(null);
    setTyped("");
    setRunError(null);
    setPreview(null);
    setPreviewKey("");
    setStep(2);
    setPhase("steps");
  }

  // --- render ---------------------------------------------------------------------------------------

  const stepsStrip = (
    <ol aria-label="Steps" className="grid grid-cols-3 gap-2">
      {STEP_LABELS.map((label, i) => {
        const current = step === i + 1;
        return (
          <li
            key={label}
            aria-current={current ? "step" : undefined}
            className={cn(
              "rounded-control px-2 py-1 text-center text-secondary",
              current ? "bg-primary-subtle font-semibold text-primary-text" : "bg-surface-sunken text-text-secondary",
            )}
          >
            {label}
          </li>
        );
      })}
    </ol>
  );

  let body;
  if (phase === "loading") {
    body = (
      <p role="status" className="text-body text-text-secondary">
        Loading the standard copies…
      </p>
    );
  } else if (phase === "error") {
    body = (
      <div role="alert" className="flex flex-col items-start gap-2">
        <AgreementNote tone="warning">{loadError}</AgreementNote>
        <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
          Try again
        </Button>
      </div>
    );
  } else if (phase === "upload") {
    body = (
      <UploadForm
        target={{ mode: "standard", kind: uploadKind, lockTarget: true, fromWizard: true }}
        canWrite
        cancelLabel="Back to attach"
        onCancel={() => setPhase("steps")}
        onBusyChange={setBusy}
        onUploaded={(result, message) => {
          setStatus(message);
          onChanged();
          setChosen((current) => ({ ...current, [result.kind]: true }));
          getStandardDocuments()
            .then(setStandard)
            .catch(() => undefined);
          setStep(1);
          setPhase("steps");
        }}
      />
    );
  } else if (phase === "running" && batch) {
    const pct = batch.target_count > 0 ? Math.min(100, Math.round((batch.done_count / batch.target_count) * 100)) : 0;
    body = (
      <>
        {stepsStrip}
        <p className="text-body text-text">Attaching in groups of 25. You can leave this open; it keeps running.</p>
        <ProgressBar
          label="Attach progress"
          value={pct}
          valueText={`${pct}% · ${batch.done_count} of ${batch.target_count} clients`}
        />
        <p className="text-secondary text-text-secondary">{`${pct}%`}</p>
        {pollNote ? <p className="text-secondary text-text-secondary">{pollNote}</p> : null}
      </>
    );
  } else if (phase === "done" && batch) {
    const clients = batch.attached_clients;
    body = (
      <>
        {stepsStrip}
        <AgreementNote tone="info">
          <strong>Done.</strong>{" "}
          {typeof clients === "number"
            ? `Batch ${batch.id} attached ${kindsText(batch.kinds)} to ${clients} ${plural(clients, "client", "clients")}.`
            : `Batch ${batch.id} attached ${kindsText(batch.kinds)} (${batch.attached_count} ${plural(batch.attached_count, "attachment", "attachments")}).`}{" "}
          {`Every attachment is credited to ${batch.created_by} and recorded in the audit log.`}
        </AgreementNote>
        <p className="text-body text-text">
          {`Existing and net new are now fixed as of ${cutover ? calendarText(cutover) : "the cutover date"}. You can undo this batch from the page header. Undo removes only what this batch attached.`}
        </p>
        <div>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </>
    );
  } else if (phase === "failed" && batch) {
    body = (
      <>
        {stepsStrip}
        <p role="alert" className="text-body text-danger">
          {batch.error ||
            `Batch ${batch.id} stopped after ${batch.done_count} of ${batch.target_count} ${plural(batch.target_count, "client", "clients")}.`}
        </p>
        <p className="text-body text-text">
          {`The copies batch ${batch.id} attached stay. Review again to finish the rest.`}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={reviewAgain}>Review again</Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </>
    );
  } else if (phase === "undone" && batch) {
    body = (
      <>
        {stepsStrip}
        <p className="text-body text-text">{`Batch ${batch.id} ${batch.status === "undoing" ? "is being undone" : "was undone"}.`}</p>
        <div>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </>
    );
  } else if (step === 1) {
    body = (
      <>
        {stepsStrip}
        <p className="text-body text-text">
          Attach your standard copies to existing clients in one step. Nothing is attached until you confirm on the
          last step.
        </p>
        {undoingLabel ? (
          <AgreementNote tone="warning">{`Batch ${undoingLabel} is being undone. You can attach again when it finishes.`}</AgreementNote>
        ) : null}
        {AGREEMENT_KINDS.map((kind) => {
          const doc = standard?.[kind] ?? null;
          const boxId = `${ids}-${kind}`;
          return (
            <div key={kind} className="flex flex-col gap-2 rounded-card border border-border bg-surface-sunken p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id={boxId}
                    checked={chosen[kind]}
                    onCheckedChange={(value) => setChosen((current) => ({ ...current, [kind]: value === true }))}
                  />
                  <label htmlFor={boxId} className="text-section text-text">
                    {`Attach the standard ${kind}`}
                  </label>
                </div>
                {doc ? (
                  <AgreementTag tone="progress" wrap={false}>{`v${doc.version}`}</AgreementTag>
                ) : (
                  <AgreementTag tone="warning" wrap={false}>
                    Not uploaded
                  </AgreementTag>
                )}
              </div>
              {doc ? (
                <p className="break-words text-secondary text-text-secondary [overflow-wrap:anywhere]">
                  {`${doc.file_name} · uploaded ${pacificDate(doc.uploaded_at)} by ${doc.uploaded_by}`}
                </p>
              ) : (
                <div>
                  <Button
                    onClick={() => {
                      setUploadKind(kind);
                      setPhase("upload");
                    }}
                  >
                    <span aria-hidden="true">{"↑ "}</span>
                    {`Upload standard ${kind}`}
                  </Button>
                </div>
              )}
            </div>
          );
        })}
        <div>
          <Button
            onClick={() => {
              setPreviewError(null);
              setStep(2);
            }}
            disabled={!chosenKinds.length}
          >
            Review who gets them
            <span aria-hidden="true">{" →"}</span>
          </Button>
        </div>
      </>
    );
  } else if (step === 2) {
    body = (
      <>
        {stepsStrip}
        <p className="text-body text-text">This is a dry run. No client changes yet.</p>
        {previewError ? (
          <div role="alert" className="flex flex-col items-start gap-2">
            <AgreementNote tone="warning">{previewError}</AgreementNote>
            <Button variant="secondary" onClick={runPreview}>
              Try again
            </Button>
          </div>
        ) : !preview || !counts || previewKey !== kindsKey ? (
          <p role="status" className="text-body text-text-secondary">
            Running the dry run…
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-body">
              <dt className="text-text">Clients that will receive copies</dt>
              <dd className="tnum text-right font-semibold text-text">{counts.willReceive}</dd>
              <dt className="text-text">of which net-new clients in the pipeline past stage 1</dt>
              <dd className="tnum text-right font-semibold text-text">{counts.netIncluded}</dd>
              <dt className="text-text">Clients already holding the chosen documents</dt>
              <dd className="tnum text-right font-semibold text-text">{counts.alreadyHold}</dd>
              <dt className="text-text">Net-new clients not included (stage 1 or no active deal)</dt>
              <dd className="tnum text-right font-semibold text-text">{counts.netUntouched}</dd>
            </dl>
            <h3 className="text-section text-text">Clients</h3>
            <p className="text-secondary text-text-secondary">
              Existing clients and net-new clients past stage 1 start ticked. Untick any client to leave it out. Clients
              with deals only in stage 1 and test data start unticked.
            </p>
            {preview.targets.length ? (
              <ul className="max-h-80 overflow-y-auto rounded-card border border-border" aria-label="Clients">
                {preview.targets.map((target, i) => {
                  const tag = targetTag(target);
                  const boxId = `${ids}-target-${i}`;
                  return (
                    <li
                      key={target.client_id}
                      className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2 last:border-b-0"
                    >
                      <Checkbox
                        id={boxId}
                        checked={Boolean(ticks[target.client_id])}
                        onCheckedChange={(value) =>
                          setTicks((current) => ({ ...current, [target.client_id]: value === true }))
                        }
                      />
                      <label htmlFor={boxId} className="min-w-0 break-words text-body text-text [overflow-wrap:anywhere]">
                        {target.name}
                      </label>
                      {tag ? <AgreementTag tone={tag.tone}>{tag.text}</AgreementTag> : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-secondary text-text-secondary">No clients need copies.</p>
            )}
          </>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setStep(1)}>
            <span aria-hidden="true">{"← "}</span>
            Back
          </Button>
          <Button
            onClick={() => void toConfirm()}
            disabled={!counts || counts.willReceive <= 0 || previewKey !== kindsKey}
            aria-busy={previewing || undefined}
          >
            Continue
            <span aria-hidden="true">{" →"}</span>
          </Button>
        </div>
      </>
    );
  } else {
    const n = confirm?.will_receive ?? 0;
    const net = confirm?.net_new_included ?? 0;
    const typedId = `${ids}-typed`;
    body = (
      <>
        {stepsStrip}
        <p className="text-body text-text">
          You are about to attach <strong>{kindsText(chosenKinds)}</strong> to <strong>{n}</strong>
          {` ${plural(n, "client", "clients")} (${n - net} existing, ${net} net new in the pipeline). A client that already has one keeps it. Net-new clients that receive a copy stay net new and show “Standard copy”; replace it from the client panel when they need their own version.`}
        </p>
        {missingStandard.length ? (
          <AgreementNote tone="warning">
            {`The standard ${kindsText(missingStandard)} ${plural(missingStandard.length, "is", "are")} not uploaded yet. Upload it in step 1 before you attach.`}
          </AgreementNote>
        ) : null}
        <div className="flex flex-col gap-1">
          <label htmlFor={typedId} className={FIELD_LABEL}>
            Type <b className="text-text">{word}</b> to confirm
          </label>
          <Input
            id={typedId}
            autoComplete="off"
            value={typed}
            disabled={missingStandard.length > 0 || starting}
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        {runError ? (
          <p role="alert" className="text-secondary text-danger">
            {runError}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setStep(2)} disabled={starting}>
            <span aria-hidden="true">{"← "}</span>
            Back
          </Button>
          <Button
            onClick={() => void run()}
            disabled={!confirm || typed.trim() !== word || missingStandard.length > 0 || n <= 0}
            aria-busy={starting || undefined}
          >
            Attach now
          </Button>
        </div>
      </>
    );
  }

  const uploading = phase === "upload";
  return (
    <AgreementsDrawer
      open={open}
      onOpenChange={onOpenChange}
      kicker={uploading ? "Standard copy" : "One-time backfill"}
      title={uploading ? `Upload standard ${uploadKind}` : "Attach standard copies"}
      busy={busy}
      titleRef={titleRef}
    >
      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>
      {body}
    </AgreementsDrawer>
  );
}
