/**
 * Section 7 — What's still needed.
 *
 * Renders the `needs_you` list with a jump-to-field link per item.
 * When the list is empty the section proudly reads that every field is
 * derived — this is the sow-first spec's "confirmation, not entry"
 * moment.
 *
 * A blocker for ``signatories`` embeds the SignatoriesPicker inline —
 * the row is the input, not a label pointing at one (docs/directives/
 * one-staffing-model.md rule 6, gm-correctness §4).
 */
import type {
  PickedSignatory,
  SowConfirmationPayload,
  UUID,
} from "../../../../api/client";
import { CheckCircle2 } from "lucide-react";
import { readField } from "./helpers";
import { Section } from "./Section";
import { SignatoriesPicker } from "./SignatoriesPicker";

export interface NeedsYouSectionProps {
  payload: SowConfirmationPayload;
  /**
   * Called with the freshly-saved list every time the inline picker
   * mutates signatories, so the parent's optimistic payload updates and
   * this row can drop off the blocker list.
   */
  onSignatoriesChange?: (next: PickedSignatory[]) => void;
}

const EMPTY_COPY =
  "Nothing left to confirm — every field is derived from the SOW, master data, or the calculation.";

/**
 * Map a `needs_you.field` name to the DOM id of the row we want to
 * scroll to. Falls back to the containing section so the reviewer at
 * least lands on the right block.
 */
/**
 * Anchor for a gap.
 *
 * Gaps that are not editable rows land on the section that owns them:
 * `staffing[0].hourly_bill_rate` has no row of its own, and a
 * `#field-row-staffing[0].hourly_bill_rate` href is not even a valid
 * fragment — the brackets make it an invalid selector. Sending it to the
 * staffing section at least puts the reviewer where the fix is.
 */
function targetFor(field: string): string {
  if (field === "engagement_type") return "engagement-chooser";
  if (field.startsWith("staffing") || field === "gm_model") {
    return "section-staffing";
  }
  if (field === "rate_card") return "section-ratecard";
  return `field-row-${field}`;
}

export function NeedsYouSection({
  payload,
  onSignatoriesChange,
}: NeedsYouSectionProps) {
  const items = payload.needs_you ?? [];
  const sowVersionId = payload.sow_version.id as UUID;
  const clientId = (payload.source?.client_id ?? null) as UUID | null;
  const fields = payload.sow_version.extracted_fields as
    | Record<string, unknown>
    | null;
  const signatoriesValue = readField(fields, "signatories")?.value;
  return (
    <Section
      id="section-needs-you"
      title="What's still needed"
      description="Only these fields block submit."
    >
      {items.length === 0 ? (
        <div
          role="status"
          data-testid="needs-you-empty"
          className="flex items-center gap-3 rounded-panel border border-success/30 bg-success-surface p-3"
        >
          <CheckCircle2 className="h-5 w-5 text-success" aria-hidden />
          <p className="text-body text-text">{EMPTY_COPY}</p>
        </div>
      ) : (
        <ol
          className="flex flex-col gap-2"
          data-testid="needs-you-list"
        >
          {items.map((item, i) => {
            const target = targetFor(item.field);
            const isSignatories =
              item.field === "signatories" ||
              item.field.startsWith("signatories");
            return (
              <li
                key={`${item.field}-${i}`}
                className="flex flex-col gap-2 rounded-panel border border-warning/40 bg-warning-surface p-3"
                data-testid={`needs-you-item-${item.field}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-body text-text font-medium">
                      {humanFieldName(item.field)}
                    </p>
                    <p className="text-secondary text-text-secondary">
                      {item.reason}
                    </p>
                  </div>
                  {isSignatories ? null : (
                    <a
                      href={`#${target}`}
                      className="text-secondary text-primary underline underline-offset-2"
                      data-testid={`needs-you-jump-${item.field}`}
                    >
                      Jump to field
                    </a>
                  )}
                </div>
                {isSignatories ? (
                  <SignatoriesPicker
                    id={`needs-you-picker-${i}`}
                    sowVersionId={sowVersionId}
                    clientId={clientId}
                    value={signatoriesValue}
                    onChange={onSignatoriesChange}
                  />
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}

function humanFieldName(field: string): string {
  return field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
