/**
 * SOW studio — Sprint 9 Wave 2 rewrite, with the S10-01 upload chain
 * wired into it.
 *
 * The studio is now a **confirmation screen**, not a five-step wizard
 * (spec: `docs/directives/sow-first.md`, CLAUDE.md rule 10). The URL
 * `/sows/new` still opens the studio, but its meaning is now:
 *
 *   - No opportunity id and no job id → the compact upload panel
 *     (single file input). Submitting it kicks off the upload pipeline.
 *   - Job id (via `?jobId=X`) → the pipeline progress card + picker.
 *   - Opportunity id (via `?opportunityId=X`) → the derived
 *     confirmation package.
 *
 * "A blank form on open is a defect." Every visible input on the
 * confirmation view is pre-populated from the API payload.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import {
  ApiError,
  confirmSowField,
  getSowConfirmation,
  submitSowConfirmation,
  uploadSow,
  type EngagementType,
  type PickedSignatory,
  type SowConfirmationPayload,
  type SowUploadJobResponse,
  type SowUploadRejected422,
  type UploadSowResponse,
  type UUID,
} from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { UploadPanel } from "./sow-studio/confirmation/UploadPanel";
import { PipelineProgress } from "./sow-studio/upload/PipelineProgress";
import { ClientPickerModal } from "./sow-studio/upload/ClientPickerModal";
import { SourceSection } from "./sow-studio/confirmation/SourceSection";
import { ScopeSection } from "./sow-studio/confirmation/ScopeSection";
import { RateCardSection } from "./sow-studio/confirmation/RateCardSection";
import { StaffingGmSection } from "./sow-studio/confirmation/StaffingGmSection";
import { ApproversSection } from "./sow-studio/confirmation/ApproversSection";
import { NeedsYouSection } from "./sow-studio/confirmation/NeedsYouSection";
import {
  blockingCount,
  engagementLabel,
} from "./sow-studio/confirmation/helpers";
import { ParallelSowPrompt } from "./sow-studio/upload/ParallelSowPrompt";

const TAGLINE = "Confirmation, not entry — the SOW is the input.";

export function SowStudioPage() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const opportunityId = params.get("opportunityId");
  const jobId = params.get("jobId");

  const setJobId = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params);
      next.set("jobId", id);
      next.delete("opportunityId");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  /**
   * Upload finished — go to the staffing gate, not straight to confirmation.
   *
   * The confirmation screen shows a gross margin, and a gross margin without
   * a staffing plan under it is either absent or invented. Routing through
   * the gate means that by the time anyone reads the confirm screen, the
   * margin on it was computed from a plan a person actually entered.
   */
  const goToStaffing = useCallback(
    (oppId: string) => {
      nav(`/sows/${oppId}/staffing`);
    },
    [nav],
  );

  const clearUploadState = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("jobId");
    next.delete("opportunityId");
    setParams(next, { replace: true });
  }, [params, setParams]);

  if (opportunityId) {
    return (
      <ConfirmationFlow
        opportunityId={opportunityId as UUID}
        onSubmittedNavigate={(id) => nav(`/sows/${id}/approvals`)}
      />
    );
  }

  return (
    <UploadFlow
      jobId={jobId}
      onJobStarted={setJobId}
      onDone={goToStaffing}
      onReset={clearUploadState}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Upload flow                                                                */
/* -------------------------------------------------------------------------- */

interface UploadFlowProps {
  jobId: string | null;
  onJobStarted: (jobId: string) => void;
  onDone: (opportunityId: string) => void;
  onReset: () => void;
}

/**
 * The single-file upload path per S10-01. Handles three phases in one
 * component:
 *
 *   1. No job yet → :class:`UploadPanel` collects the file.
 *   2. Job in flight → :class:`PipelineProgress` polls status.
 *   3. Status `needs_pick` → :class:`ClientPickerModal` overlays.
 *
 * Non-SOW 422 responses surface as a red banner + "Upload a different
 * file" button; no DB rows are created (the API guarantees this).
 */
function UploadFlow({
  jobId,
  onJobStarted,
  onDone,
  onReset,
}: UploadFlowProps) {
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<SowUploadRejected422 | null>(null);
  const [needsPickJob, setNeedsPickJob] =
    useState<SowUploadJobResponse | null>(null);
  // Other in-progress SOWs for the same client. Shown as a question, never
  // as a rejection: a client can legitimately run several contracts at once.
  const [parallel, setParallel] = useState<{
    jobId: string;
    others: NonNullable<UploadSowResponse["other_open_sows"]>;
  } | null>(null);

  const handleUpload = useCallback(
    async ({ file }: { file: File }) => {
      setSubmitting(true);
      setUploadError(null);
      setRejected(null);
      try {
        const res = await uploadSow({ file });
        if (res.duplicate && res.opportunity_id) {
          // Dupe with a fully-resolved opportunity → jump straight to
          // confirmation so the reviewer sees the derived package.
          onDone(res.opportunity_id);
          return;
        }
        const others = res.other_open_sows ?? [];
        if (others.length > 0) {
          // Stop and ask. Continuing silently is how the same engagement
          // ends up in the pipeline twice with separate approval trails.
          setParallel({ jobId: res.job_id, others });
          return;
        }
        onJobStarted(res.job_id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 422) {
          const detail = e.detail as { detail?: SowUploadRejected422 } | null;
          const payload = detail?.detail ?? null;
          if (payload && payload.detected_type) {
            setRejected(payload);
            return;
          }
        }
        setUploadError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setSubmitting(false);
      }
    },
    [onDone, onJobStarted],
  );

  const handleNeedsPick = useCallback((job: SowUploadJobResponse) => {
    setNeedsPickJob(job);
  }, []);

  const handleDone = useCallback(
    (job: SowUploadJobResponse) => {
      if (job.opportunity_id) {
        onDone(job.opportunity_id);
      }
    },
    [onDone],
  );

  const handlePicked = useCallback(
    (job: SowUploadJobResponse) => {
      setNeedsPickJob(null);
      if (job.status === "done" && job.opportunity_id) {
        onDone(job.opportunity_id);
      }
    },
    [onDone],
  );

  const handleRetry = useCallback(() => {
    setNeedsPickJob(null);
    onReset();
  }, [onReset]);

  if (parallel) {
    // Stop and ask before creating a second opportunity for this client.
    return (
      <ParallelSowPrompt
        others={parallel.others}
        onContinueNew={() => {
          const id = parallel.jobId;
          setParallel(null);
          onJobStarted(id);
        }}
        onOpenExisting={(opportunityId) => {
          setParallel(null);
          window.location.assign(`/sows/${opportunityId}`);
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="New SOW"
        subtitle={TAGLINE}
        actions={
          <StatusBadge tone="progress" label="Upload → confirmation" />
        }
      />

      {rejected ? (
        <div
          role="alert"
          className="rounded-panel border border-danger/40 bg-danger-surface p-4 text-danger"
          data-testid="upload-rejected-banner"
        >
          <p className="text-body">{rejected.message}</p>
          <Button
            type="button"
            variant="ghost"
            className="mt-2"
            onClick={() => {
              setRejected(null);
              onReset();
            }}
            data-testid="upload-rejected-retry"
          >
            Upload a different file
          </Button>
        </div>
      ) : null}

      {jobId ? (
        <>
          <PipelineProgress
            jobId={jobId}
            onNeedsPick={handleNeedsPick}
            onDone={handleDone}
            onRetry={handleRetry}
          />
          {needsPickJob && needsPickJob.needs_pick ? (
            <ClientPickerModal
              open
              jobId={jobId}
              needsPick={needsPickJob.needs_pick}
              onPicked={handlePicked}
              onCancel={handleRetry}
            />
          ) : null}
        </>
      ) : (
        <UploadPanel
          onSubmit={handleUpload}
          submitting={submitting}
          error={uploadError}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Confirmation flow                                                          */
/* -------------------------------------------------------------------------- */

/**
 * Display key on this screen → the extracted field it writes to.
 *
 * Only rows that map to a real extracted field are editable. `client_entity`
 * is a resolved client record, `sow_title` is derived from the client and
 * scope, and `file` is a stored object — PATCHing any of them would 422 with
 * "unknown field", so they are absent here on purpose and the row renders
 * read-only rather than offering an edit that cannot work.
 */
const EDITABLE_FIELD_KEYS: Record<string, string> = {
  price: "price",
  currency: "currency",
  term_start: "term_start",
  term_end: "term_end",
  notice_date: "notice_date",
  billing_basis: "billing_basis",
  deliverables: "deliverables",
  milestones: "milestones",
  acceptance_criteria: "acceptance_criteria",
  assumptions: "assumptions",
  exclusions: "exclusions",
  signatories: "signatories",
  scope_summary: "scope_summary",
  client_legal_name: "client_legal_name",
  client_domain: "client_domain",
  engagement_type: "engagement_type_suggested",
};

/** Fields the extractor stores as a list, not a string. */
const LIST_FIELDS = new Set([
  "deliverables",
  "milestones",
  "signatories",
  "assumptions",
  "exclusions",
]);

/**
 * Turn an edited display string back into a list.
 *
 * The row renders a list joined with ", ", so writing the edited string
 * straight back would replace a list of four deliverables with one sentence
 * — and `FieldPatch.value` is typed `Any` server-side, so nothing would
 * reject it. Splits on the separators these fields actually use.
 */
export function splitList(raw: string): string[] {
  const text = raw.trim();
  if (!text) return [];
  const sep = [";", "|"].find((c) => text.includes(c)) ?? ",";
  return text
    .split(sep)
    .map((part) => part.trim())
    .filter(Boolean);
}

function ConfirmationFlow({
  opportunityId,
  onSubmittedNavigate,
}: {
  opportunityId: UUID;
  onSubmittedNavigate: (opportunityId: UUID) => void;
}) {
  const [payload, setPayload] = useState<SowConfirmationPayload | null>(null);
  const [costsDirty, setCostsDirty] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  const sowVersionId = payload?.sow_version.id ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const p = await getSowConfirmation(opportunityId);
      setPayload(p);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [opportunityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const blockers = useMemo(
    () => (payload ? blockingCount(payload) : 0),
    [payload],
  );

  /**
   * Persist an override.
   *
   * This used to be `setState` and nothing else — the row flipped to
   * `manual`, the value changed on screen, and the reviewer had every reason
   * to think it had saved. It had not: a reload re-read the untouched
   * database row and every edit was gone. That is what "not able to edit"
   * meant.
   *
   * Three things the naive wiring would have got wrong, so they are handled
   * here rather than discovered in production:
   *
   * - Three of the rows on this screen are not extracted fields. `client
   *   entity` is a resolved client record, `sow title` is derived, `file` is
   *   a stored object. PATCHing them by their display key would 422 with
   *   "unknown field". Only rows that map to a real extracted field are
   *   editable; `EDITABLE_FIELD_KEYS` is that map.
   * - List-valued fields (deliverables, milestones, signatories) render as
   *   a joined string. Writing that string back would replace a list with a
   *   sentence and corrupt the type for every downstream reader, so they are
   *   split back into a list on the way out.
   * - The optimistic update stays, because the round-trip is slow enough to
   *   feel broken without it — but the server response is authoritative, so
   *   the payload is reloaded after, and a failure surfaces instead of
   *   leaving a lie on screen.
   */
  const handleOverride = useCallback(
    (fieldKey: string, newValue: string) => {
      const target = EDITABLE_FIELD_KEYS[fieldKey];
      if (!target) {
        setOverrideError(
          `"${fieldKey}" is derived from other records and cannot be edited here.`,
        );
        return;
      }
      const value = LIST_FIELDS.has(target) ? splitList(newValue) : newValue;

      // Optimistic, then reconciled against the server.
      setPayload((prev) => {
        if (!prev) return prev;
        const fields = {
          ...(prev.sow_version.extracted_fields ?? {}),
        } as Record<string, unknown>;
        fields[target] = {
          value,
          provenance: "manual",
          status: "confirmed",
        };
        return {
          ...prev,
          sow_version: { ...prev.sow_version, extracted_fields: fields },
          needs_you: prev.needs_you.filter(
            (n) => n.field !== target || newValue === "",
          ),
        };
      });

      setOverrideError(null);
      void confirmSowField(sowVersionId as UUID, target as never, value)
        .then(() => load())
        .catch((e: unknown) => {
          setOverrideError(
            e instanceof Error ? e.message : "could not save that change",
          );
          // Put the real values back rather than leaving the optimistic
          // edit standing as if it had saved.
          void load();
        });
    },
    [sowVersionId, load],
  );

  /**
   * The picker owns the PATCH — this handler just reconciles the local
   * copy so the ``signatories`` blocker drops off the "What's still needed"
   * list without waiting on a reload. A follow-up `load()` re-syncs
   * everything the server derived from the write (provenance stamp,
   * status flip).
   */
  const handleSignatoriesChange = useCallback(
    (next: PickedSignatory[]) => {
      setPayload((prev) => {
        if (!prev) return prev;
        const fields = {
          ...(prev.sow_version.extracted_fields ?? {}),
        } as Record<string, unknown>;
        const existing = fields["signatories"] as
          | { page_ref?: number | null; source_id?: string | null }
          | undefined;
        fields["signatories"] = {
          value: next,
          provenance: "manual",
          status: next.length > 0 ? "confirmed" : "unconfirmed",
          page_ref: existing?.page_ref ?? null,
          source_id: existing?.source_id ?? null,
        };
        return {
          ...prev,
          sow_version: { ...prev.sow_version, extracted_fields: fields },
          needs_you:
            next.length > 0
              ? prev.needs_you.filter(
                  (n) =>
                    n.field !== "signatories" &&
                    !n.field.startsWith("signatories"),
                )
              : prev.needs_you,
        };
      });
      void load();
    },
    [load],
  );

  const handleEngagementPick = useCallback(
    (type: EngagementType) => {
      setPayload((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          engagement: {
            ...prev.engagement,
            primary: { type, confidence: 1 },
            secondary: null,
            auto_confirm: true,
            rule_matched: "manual_pick",
          },
          needs_you: prev.needs_you.filter((n) => n.field !== "engagement_type"),
        };
      });
      // The pick is a decision about the record, not a view preference — it
      // has to outlive the page. `engagement_type_suggested` is the stored
      // field; confirm_field also stamps `engagement_type_confirmed`.
      void confirmSowField(
        sowVersionId as UUID,
        "engagement_type_suggested" as never,
        type,
      )
        .then(() => load())
        .catch((e: unknown) => {
          setOverrideError(
            e instanceof Error ? e.message : "could not save the engagement type",
          );
          void load();
        });
    },
    [sowVersionId, load],
  );

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitSowConfirmation(opportunityId);
      onSubmittedNavigate(opportunityId);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !payload) {
    return (
      <div className="space-y-4">
        <PageHeader title="Confirming SOW" subtitle={TAGLINE} />
        <div
          data-testid="confirmation-loading"
          className="h-40 animate-pulse rounded-card border border-divider bg-surface-sunken"
        />
      </div>
    );
  }

  if (loadError || !payload) {
    return (
      <div className="space-y-4">
        <PageHeader title="Confirm SOW" subtitle={TAGLINE} />
        <ErrorState
          title="We couldn't load the confirmation package"
          description={loadError ?? "The server returned no payload."}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  const engagementChip = engagementLabel(payload.engagement.primary.type);
  const canSubmit = blockers === 0 && !submitting && !costsDirty;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Confirm SOW"
        subtitle={TAGLINE}
        actions={
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <StatusBadge
                tone={payload.engagement.auto_confirm ? "progress" : "warning"}
                label={engagementChip}
                data-testid="engagement-chip"
              />
              <Button
                type="button"
                variant="primary"
                onClick={handleSubmit}
                disabled={!canSubmit}
                data-testid="confirmation-submit"
                aria-describedby="submit-hint"
              >
                {submitting ? "Confirming…" : "Complete scope"}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
            <p
              id="submit-hint"
              className="text-secondary text-text-secondary"
            >
              {costsDirty ? "Unsaved direct costs." : blockers === 0
                ? "Ready to confirm scope."
                : `${blockers} field${blockers === 1 ? "" : "s"} still block confirmation.`}
            </p>
          </div>
        }
      />

      <SourceSection
        payload={payload}
        onOverrideField={handleOverride}
        onChooseEngagement={handleEngagementPick}
      />
      {overrideError ? (
        <p className="text-secondary text-danger" data-testid="override-error">
          {overrideError}
        </p>
      ) : null}
      <ScopeSection
        payload={payload}
        onOverrideField={handleOverride}
        onSignatoriesChange={handleSignatoriesChange}
      />
      <RateCardSection payload={payload} />
      <StaffingGmSection payload={payload} opportunityId={opportunityId} onSaved={load} onDirtyChange={setCostsDirty} />
      <ApproversSection payload={payload} />
      <NeedsYouSection
        payload={payload}
        onSignatoriesChange={handleSignatoriesChange}
      />

      {submitError ? (
        <div
          role="alert"
          className="rounded-panel border border-danger/40 bg-danger-surface p-3 text-danger"
          data-testid="submit-error"
        >
          {submitError}
        </div>
      ) : null}
    </div>
  );
}
