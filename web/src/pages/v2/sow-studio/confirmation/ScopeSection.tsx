/**
 * Section 2 — Scope & terms.
 *
 * Ten extracted rows in one uniform grid. Each row: label · value ·
 * provenance chip · change. The section is a "read → maybe change"
 * surface, not a form: every row opens pre-populated from the payload.
 *
 * The signatories row is a picker rather than a free-text row — a
 * signatory is a person on file, not a sentence (docs/directives/
 * gm-correctness.md root cause 4, one-staffing-model.md rule 6).
 */
import type {
  PickedSignatory,
  SowConfirmationPayload,
  UUID,
} from "../../../../api/client";
import { ProvenanceChip } from "./provenance";
import { Section } from "./Section";
import { FieldRow } from "./FieldRow";
import { SCOPE_FIELDS, hasValue, readField } from "./helpers";
import { SignatoriesPicker } from "./SignatoriesPicker";

export interface ScopeSectionProps {
  payload: SowConfirmationPayload;
  onOverrideField: (fieldKey: string, value: string) => void;
  /**
   * Called with the freshly-saved list every time the picker mutates
   * signatories. The parent uses this to update its optimistic copy of
   * the payload so the ``signatories`` blocker clears immediately.
   */
  onSignatoriesChange?: (next: PickedSignatory[]) => void;
}

export function ScopeSection({
  payload,
  onOverrideField,
  onSignatoriesChange,
}: ScopeSectionProps) {
  const fields = payload.sow_version.extracted_fields as
    | Record<string, unknown>
    | null;
  const sowVersionId = payload.sow_version.id as UUID;
  const clientId = (payload.source?.client_id ?? null) as UUID | null;
  const signatoriesEntry = readField(fields, "signatories");
  return (
    <Section
      id="section-scope"
      title="Scope & terms"
      description="Every row is what the extractor read from the SOW; edit in place if the SOW is wrong."
    >
      <div className="flex flex-col gap-3">
        {SCOPE_FIELDS.map(({ key, label }) =>
          key === "signatories" ? (
            <div
              key={key}
              id={`field-row-${key}`}
              data-testid={`field-row-${key}`}
              data-populated={hasValue(signatoriesEntry) ? "true" : "false"}
              className="flex flex-col gap-2 rounded-panel border border-divider bg-surface p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-secondary font-medium text-text-secondary">
                  {label}
                </div>
                <ProvenanceChip
                  entry={signatoriesEntry}
                  refUnit={payload.source?.ref_unit}
                />
              </div>
              <SignatoriesPicker
                sowVersionId={sowVersionId}
                clientId={clientId}
                value={signatoriesEntry?.value}
                onChange={onSignatoriesChange}
              />
            </div>
          ) : (
            <FieldRow
              key={key}
              fieldKey={key}
              label={label}
              entry={readField(fields, key)}
              onSaveOverride={onOverrideField}
            />
          ),
        )}
      </div>
    </Section>
  );
}
