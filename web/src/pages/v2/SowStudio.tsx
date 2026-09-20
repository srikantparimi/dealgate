/**
 * SOW studio — Sprint 9 Wave 2 rewrite, with the S10-01 upload chain
 * wired into it.
 *
 * The studio is now a **confirmation screen**, not a five-step wizard
 * (spec: `docs/sow-first-principles.md`, CLAUDE.md rule 10). The URL
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
  getSowConfirmation,
  submitSowConfirmation,
  uploadSow,
  type EngagementType,
  type SowConfirmationPayload,
  type SowUploadJobResponse,
  type SowUploadRejected422,
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

function ConfirmationFlow({
  opportunityId,
  onSubmittedNavigate,
}: {
  opportunityId: UUID;
  onSubmittedNavigate: (opportunityId: UUID) => void;
}) {
  const [payload, setPayload] = useState<SowConfirmationPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

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
   * When the user overrides a value the row flips to `manual`. We do
   * this optimistically in the local copy so the provenance chip
   * updates the moment the user hits save. A follow-up story will
   * persist the change via `PATCH /sow/versions/:id/fields/:name`
   * which already exists (see `confirmSowField` in api/client.ts).
   */
  const handleOverride = useCallback(
    (fieldKey: string, newValue: string) => {
      setPayload((prev) => {
        if (!prev) return prev;
        const fields = {
          ...(prev.sow_version.extracted_fields ?? {}),
        } as Record<string, unknown>;
        fields[fieldKey] = {
          value: newValue,
          provenance: "manual",
          status: "confirmed",
        };
        // The blank-row → manual-with-value flip may resolve a
        // `needs_you` entry; drop it from the list optimistically.
        const filtered = prev.needs_you.filter(
          (n) => n.field !== fieldKey || newValue === "",
        );
        return {
          ...prev,
          sow_version: {
            ...prev.sow_version,
            extracted_fields: fields,
          },
          needs_you: filtered,
        };
      });
    },
    [],
  );

  const handleEngagementPick = useCallback((_type: EngagementType) => {
    setPayload((prev) => {
      if (!prev) return prev;
      // The chosen type overrides the classifier's ambiguity — flip
      // engagement to auto_confirm so the chooser hides and the chip
      // renders. Confidence is 1.0 because the human picked.
      return {
        ...prev,
        engagement: {
          ...prev.engagement,
          primary: { type: _type, confidence: 1 },
          secondary: null,
          auto_confirm: true,
          rule_matched: "manual_pick",
        },
        needs_you: prev.needs_you.filter((n) => n.field !== "engagement_type"),
      };
    });
  }, []);

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
  const canSubmit = blockers === 0 && !submitting;

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
                {submitting ? "Submitting…" : "Submit for approval"}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
            <p
              id="submit-hint"
              className="text-secondary text-text-secondary"
            >
              {blockers === 0
                ? "Ready to submit."
                : `${blockers} field${blockers === 1 ? "" : "s"} still block submit.`}
            </p>
          </div>
        }
      />

      <SourceSection
        payload={payload}
        onOverrideField={handleOverride}
        onChooseEngagement={handleEngagementPick}
      />
      <ScopeSection payload={payload} onOverrideField={handleOverride} />
      <RateCardSection payload={payload} />
      <StaffingGmSection payload={payload} />
      <ApproversSection payload={payload} />
      <NeedsYouSection payload={payload} />

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
