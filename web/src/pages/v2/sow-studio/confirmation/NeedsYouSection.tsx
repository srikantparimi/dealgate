/**
 * Section 7 — What's still needed.
 *
 * Renders the `needs_you` list with a jump-to-field link per item.
 * When the list is empty the section proudly reads that every field is
 * derived — this is the sow-first spec's "confirmation, not entry"
 * moment.
 */
import type { SowConfirmationPayload } from "../../../../api/client";
import { CheckCircle2 } from "lucide-react";
import { Section } from "./Section";

export interface NeedsYouSectionProps {
  payload: SowConfirmationPayload;
}

const EMPTY_COPY =
  "Nothing left to confirm — every field is derived from the SOW, master data, or the calculation.";

/**
 * Map a `needs_you.field` name to the DOM id of the row we want to
 * scroll to. Falls back to the containing section so the reviewer at
 * least lands on the right block.
 */
function targetFor(field: string): string {
  if (field === "engagement_type") return "engagement-chooser";
  if (field === "staffing") return "section-staffing";
  if (field === "rate_card") return "section-ratecard";
  return `field-row-${field}`;
}

export function NeedsYouSection({ payload }: NeedsYouSectionProps) {
  const items = payload.needs_you ?? [];
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
            return (
              <li
                key={`${item.field}-${i}`}
                className="flex items-start justify-between gap-3 rounded-panel border border-warning/40 bg-warning-surface p-3"
                data-testid={`needs-you-item-${item.field}`}
              >
                <div className="min-w-0">
                  <p className="text-body text-text font-medium">
                    {humanFieldName(item.field)}
                  </p>
                  <p className="text-secondary text-text-secondary">
                    {item.reason}
                  </p>
                </div>
                <a
                  href={`#${target}`}
                  className="text-secondary text-primary underline underline-offset-2"
                  data-testid={`needs-you-jump-${item.field}`}
                >
                  Jump to field
                </a>
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
