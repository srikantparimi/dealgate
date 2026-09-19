/**
 * SOW studio — Sprint 9 Wave 2 rewrite.
 *
 * The studio is now a **confirmation screen**, not a five-step wizard
 * (spec: `docs/sow-first-principles.md`, CLAUDE.md rule 10). The URL
 * `/sows/new` still opens the studio, but its meaning is now:
 *
 *   - No opportunity id → a compact upload panel (client + file).
 *   - Opportunity id present (via `?opportunityId=X`) → the derived
 *     package: extracted fields with provenance, auto-classified
 *     engagement, auto-staffed grid, computed floors, proposed
 *     approvers and the `needs_you` list.
 *
 * "A blank form on open is a defect." Every visible input on the
 * confirmation view is pre-populated from the API payload. If a value
 * is genuinely missing it renders in the "What's still needed"
 * section with a jump link — never as an empty input on load.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import {
  getSowConfirmation,
  submitSowConfirmation,
  type EngagementType,
  type SowConfirmationPayload,
  type UUID,
} from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { UploadPanel } from "./sow-studio/confirmation/UploadPanel";
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

  if (!opportunityId) {
    return (
      <UploadFlow
        onCreated={(id) => {
          const next = new URLSearchParams(params);
          next.set("opportunityId", id);
          setParams(next, { replace: true });
        }}
      />
    );
  }

  return (
    <ConfirmationFlow
      opportunityId={opportunityId as UUID}
      onSubmittedNavigate={(id) => nav(`/sows/${id}/approvals`)}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Upload flow                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Compact upload panel wired for the "no opportunity id yet" case.
 *
 * Production wiring: the real path chains `getSowUploadUrl` → PUT to S3
 * → `createSowVersion` → extract worker → confirmation load. Those
 * endpoints already exist and are typed in `api/client.ts`; wiring the
 * full chain requires an opportunity picker that the studio does not
 * yet own. Until that lands, `onSubmit` surfaces an honest banner and
 * preserves the panel state so the reviewer can retry.
 */
function UploadFlow({ onCreated }: { onCreated: (id: UUID) => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      // TODO(agent-XX-follow-up): call getSowUploadUrl → PUT →
      // createSowVersion → poll for extract complete → onCreated(opp).
      // The confirmation-first UI is fully live; the upload → extract
      // chain lands once the opportunity resolver is decided.
      throw new Error(
        "Upload → extract chain is not wired yet. Follow-up story: SOW upload router.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
    // Reference `onCreated` so it stays a real prop (TS: noUnusedLocals).
    void onCreated;
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
      <UploadPanel
        onSubmit={handleSubmit}
        submitting={submitting}
        error={error}
      />
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
