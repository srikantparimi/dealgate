/**
 * Section 1 — Source & type.
 *
 * Four confirmed rows (client + entity, SOW title, file link, engagement
 * type). Every row opens pre-populated; the engagement-type row switches
 * to a two-candidate chooser when the classifier's confidence dropped
 * below `auto_confirm`.
 */
import type {
  EngagementType,
  SowConfirmationPayload,
  SowProvenanceEntry,
} from "../../../../api/client";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { Button } from "../../../../ui-v2/primitives/button";
import { Section } from "./Section";
import { FieldRow } from "./FieldRow";
import {
  engagementIsAmbiguous,
  engagementLabel,
  readField,
} from "./helpers";

export interface SourceSectionProps {
  payload: SowConfirmationPayload;
  onOverrideField: (fieldKey: string, value: string) => void;
  onChooseEngagement: (type: EngagementType) => void;
}

export function SourceSection({
  payload,
  onOverrideField,
  onChooseEngagement,
}: SourceSectionProps) {
  const fields = payload.sow_version.extracted_fields as
    | Record<string, unknown>
    | null;
  const engagementEntry = readField(fields, "engagement_type");

  // Client, title and file are records — a resolved client row and a stored
  // object — not things the extractor emits. Reading them out of
  // `extracted_fields` (under keys `client_entity` / `sow_title` / `file`,
  // which nothing has ever written) is why all three showed "unknown".
  const src = payload.source;

  const clientEntry: SowProvenanceEntry = src?.client_name
    ? {
        value: src.legal_entity_name
          ? `${src.client_name} · ${src.legal_entity_name}`
          : src.client_name,
        provenance: "looked_up",
        source_id: src.client_id ?? undefined,
      }
    : {
        // Not resolved yet, but the extractor may still have read a name off
        // the parties clause — show it so the reviewer confirms rather than types.
        value: src?.client_legal_name_extracted ?? null,
        provenance: "extracted",
        status: src?.client_legal_name_extracted ? "unconfirmed" : "disputed",
      };

  const titleEntry: SowProvenanceEntry = {
    value: src?.sow_title ?? null,
    provenance: "calculated",
    status: src?.sow_title ? "unconfirmed" : "disputed",
  };

  const fileEntry: SowProvenanceEntry = {
    value: src?.file_name ?? null,
    provenance: "looked_up",
    source_id: src?.file_s3_key ?? undefined,
    status: src?.file_name ? "unconfirmed" : "disputed",
  };

  // Engagement type is a derived field — the classifier's own result
  // takes precedence over any manual override in extracted_fields.
  const engagementType =
    (engagementEntry?.value as string | undefined) ??
    payload.engagement.primary.type;

  const engagementProvenanceEntry: SowProvenanceEntry = {
    value: engagementLabel(engagementType),
    provenance: payload.engagement.rule_matched
      ? "calculated"
      : engagementEntry?.provenance ?? "extracted",
    confidence: payload.engagement.primary.confidence,
    source_id: payload.engagement.rule_matched ?? undefined,
  };

  const ambiguous = engagementIsAmbiguous(payload);

  return (
    <Section
      id="section-source"
      title="Source & type"
      description="Confirmation, not entry — these four rows are what the SOW says or what the system decided."
    >
      <div className="flex flex-col gap-3">
        <FieldRow
          fieldKey="client_entity"
          label="Client + entity"
          entry={clientEntry}
          refUnit={src?.ref_unit}
          onSaveOverride={onOverrideField}
        />
        <FieldRow
          fieldKey="sow_title"
          label="SOW title"
          entry={titleEntry}
          refUnit={src?.ref_unit}
          onSaveOverride={onOverrideField}
        />
        <FieldRow
          fieldKey="file"
          label="SOW file"
          entry={fileEntry}
          refUnit={src?.ref_unit}
          readOnly
          renderValue={(entry) => {
            const v = entry?.value;
            if (!v || typeof v !== "string") return null;
            if (/^https?:\/\//i.test(v)) {
              return (
                <a
                  href={v}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline underline-offset-2"
                >
                  Open source file
                </a>
              );
            }
            return v;
          }}
        />

        {/* Engagement type row — bespoke because the classifier owns the
             value + the two-candidate chooser branch. */}
        {ambiguous && payload.engagement.secondary ? (
          <EngagementChooser
            payload={payload}
            onPick={(t) => onChooseEngagement(t)}
          />
        ) : (
          <FieldRow
            fieldKey="engagement_type"
            label="Engagement type"
            entry={engagementProvenanceEntry}
            renderValue={() => (
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-chip border border-primary/40 bg-primary-subtle px-2 py-1 text-body text-primaryText font-medium">
                  {engagementLabel(engagementType)}
                </span>
                <ConfidenceHint
                  confidence={payload.engagement.primary.confidence}
                />
              </div>
            )}
            readOnly
          />
        )}
      </div>
    </Section>
  );
}

function ConfidenceHint({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const tone = confidence >= 0.85 ? "success" : "warning";
  return (
    <StatusBadge
      tone={tone}
      label={`${pct}% confidence`}
      data-testid="engagement-confidence"
    />
  );
}

function EngagementChooser({
  payload,
  onPick,
}: {
  payload: SowConfirmationPayload;
  onPick: (t: EngagementType) => void;
}) {
  const { primary, secondary } = payload.engagement;
  return (
    <div
      id="engagement-chooser"
      data-testid="engagement-chooser"
      className="rounded-panel border border-warning/40 bg-warning-surface p-3"
    >
      <p className="text-body text-text">
        Confidence below threshold — pick between the two candidates.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={() => onPick(primary.type as EngagementType)}
          data-testid={`engagement-pick-${primary.type}`}
        >
          {engagementLabel(primary.type)} · {Math.round(primary.confidence * 100)}%
        </Button>
        {secondary ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() => onPick(secondary.type as EngagementType)}
            data-testid={`engagement-pick-${secondary.type}`}
          >
            {engagementLabel(secondary.type)} ·{" "}
            {Math.round(secondary.confidence * 100)}%
          </Button>
        ) : null}
      </div>
      <p className="mt-2 text-secondary text-text-secondary">
        Picking either candidate flips this row's provenance to `manual`.
      </p>
    </div>
  );
}
