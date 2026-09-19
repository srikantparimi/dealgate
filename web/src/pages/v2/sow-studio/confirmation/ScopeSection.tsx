/**
 * Section 2 — Scope & terms.
 *
 * Ten extracted rows in one uniform grid. Each row: label · value ·
 * provenance chip · change. The section is a "read → maybe change"
 * surface, not a form: every row opens pre-populated from the payload.
 */
import type { SowConfirmationPayload } from "../../../../api/client";
import { Section } from "./Section";
import { FieldRow } from "./FieldRow";
import { SCOPE_FIELDS, readField } from "./helpers";

export interface ScopeSectionProps {
  payload: SowConfirmationPayload;
  onOverrideField: (fieldKey: string, value: string) => void;
}

export function ScopeSection({
  payload,
  onOverrideField,
}: ScopeSectionProps) {
  const fields = payload.sow_version.extracted_fields as
    | Record<string, unknown>
    | null;
  return (
    <Section
      id="section-scope"
      title="Scope & terms"
      description="Every row is what the extractor read from the SOW; edit in place if the SOW is wrong."
    >
      <div className="flex flex-col gap-3">
        {SCOPE_FIELDS.map(({ key, label }) => (
          <FieldRow
            key={key}
            fieldKey={key}
            label={label}
            entry={readField(fields, key)}
            onSaveOverride={onOverrideField}
          />
        ))}
      </div>
    </Section>
  );
}
