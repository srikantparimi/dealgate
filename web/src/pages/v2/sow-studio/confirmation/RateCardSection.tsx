/**
 * Section 4 — Rate card resolution.
 *
 * Shows which client card was applied, its effective date, and a loud
 * warning if the pipeline fell back to a company default (per sow-first
 * rule 7 — fallbacks are loud). The row is read-only; the reviewer
 * follows the link to the client-cards page to edit the underlying
 * card.
 */
import type { SowConfirmationPayload } from "../../../../api/client";
import { AlertTriangle } from "lucide-react";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { Section } from "./Section";
import { readField } from "./helpers";
import { ProvenanceChip, displayValue } from "./provenance";

export interface RateCardSectionProps {
  payload: SowConfirmationPayload;
}

export function RateCardSection({ payload }: RateCardSectionProps) {
  const fields = payload.sow_version.extracted_fields as
    | Record<string, unknown>
    | null;
  const rateCard = readField(fields, "rate_card");
  const effective = readField(fields, "rate_card_effective_from");
  const fallback = readField(fields, "rate_card_fallback");
  const fellBack = Boolean(fallback?.value);
  const cardId =
    (rateCard?.value as { id?: string } | undefined)?.id ??
    (rateCard?.source_id as string | undefined) ??
    null;

  return (
    <Section
      id="section-ratecard"
      title="Rate card resolution"
      description="Which client card the pipeline applied and any fallback."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-panel border border-divider bg-surface p-3">
          <div className="flex items-center gap-2">
            <span className="text-secondary text-text-secondary">Client card</span>
            <span className="text-body text-text font-medium">
              {displayValue(rateCard) ?? "Company default"}
            </span>
            <ProvenanceChip entry={rateCard} />
          </div>
          {cardId ? (
            <a
              href={`/settings/rate-cards?client=${encodeURIComponent(cardId)}`}
              className="text-secondary text-primary underline underline-offset-2"
              data-testid="rate-card-link"
            >
              Open client card
            </a>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface p-3">
          <span className="text-secondary text-text-secondary">
            Effective from
          </span>
          <span className="text-body text-text tnum">
            {displayValue(effective) ?? "not stated"}
          </span>
          <ProvenanceChip entry={effective} />
        </div>

        {fellBack ? (
          <div
            role="alert"
            data-testid="rate-card-fallback"
            className="flex items-start gap-2 rounded-panel border border-warning/40 bg-warning-surface p-3"
          >
            <AlertTriangle
              className="mt-[2px] h-4 w-4 text-warning"
              aria-hidden
            />
            <div className="flex-1">
              <p className="text-body text-text font-medium">
                Fallback rate card applied
              </p>
              <p className="text-secondary text-text-secondary">
                {typeof fallback?.value === "string"
                  ? fallback.value
                  : "The client had no card on the SOW effective date — the company default was used."}
              </p>
            </div>
            <StatusBadge tone="warning" label="fallback" />
          </div>
        ) : null}
      </div>
    </Section>
  );
}
