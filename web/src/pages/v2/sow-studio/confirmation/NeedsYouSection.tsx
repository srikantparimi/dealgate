/**
 * S15 · D2 + D6 — Every blocker is an editor. Section retitled.
 *
 * Renders the `needs_you` list. Each row's inline editor comes from
 * `blockerRegistry` — CLAUDE.md rule 13. When the list is empty the
 * section proudly reads that every field is derived. When the row's
 * blocker is not resolvable inline (staffing prerequisites, source
 * fields), the editor is a redirect that names where to jump.
 *
 * The signatories fix in S12 was a one-off; S15 turned it into the
 * pattern via `blockerRegistry`.
 */
import type {
  PickedSignatory,
  SowConfirmationPayload,
} from "../../../../api/client";
import { CheckCircle2 } from "lucide-react";
import { Section } from "./Section";
import { lookupBlocker, type BlockerRegistryEntry } from "./blockerRegistry";

export interface NeedsYouSectionProps {
  payload: SowConfirmationPayload;
  /** Called after any inline editor writes so the parent refetches the
   * confirmation payload. */
  onChanged: () => void;
  /** Optional signatories change hook — the picker owns its own network
   * write, and the parent's optimistic payload update needs the new list. */
  onSignatoriesChange?: (next: PickedSignatory[]) => void;
}

const EMPTY_COPY =
  "Nothing left to confirm — every field is derived from the SOW, master data, or the calculation.";

export function NeedsYouSection({
  payload,
  onChanged,
  onSignatoriesChange,
}: NeedsYouSectionProps) {
  const items = payload.needs_you ?? [];
  return (
    <Section
      id="section-needs-you"
      // D6: retitled so the section reads as the fast path, not dead text.
      title="Finish these to submit"
      description="Only these fields block submit. Every one has an editor here."
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
            const entry: BlockerRegistryEntry | null = lookupBlocker(item.field);
            const label = entry?.label ?? humanFieldName(item.field);
            const jumpHref = entry?.jumpTo ?? `field-row-${item.field}`;
            return (
              <li
                key={`${item.field}-${i}`}
                className="flex flex-col gap-2 rounded-panel border border-warning/40 bg-warning-surface p-3"
                data-testid={`needs-you-item-${item.field}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-body text-text font-medium">{label}</p>
                    <p className="text-secondary text-text-secondary">
                      {item.reason}
                    </p>
                  </div>
                  {entry?.jumpTo ? (
                    <a
                      href={`#${jumpHref}`}
                      className="text-secondary text-primary underline underline-offset-2"
                      data-testid={`needs-you-jump-${item.field}`}
                    >
                      Jump to field
                    </a>
                  ) : null}
                </div>
                {entry ? (
                  <entry.Editor
                    payload={payload}
                    onChanged={onChanged}
                    onSignatoriesChange={onSignatoriesChange}
                  />
                ) : (
                  <p className="text-secondary text-text-secondary">
                    No inline editor is registered for <code>{item.field}</code>.
                    This is a Rule 13 bug — file it in{" "}
                    <code>docs/questions.md</code>.
                  </p>
                )}
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
