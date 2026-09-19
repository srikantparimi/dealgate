/**
 * One row on the confirmation screen: label · value · provenance chip · change.
 *
 * The editor is inline and pre-populated with the current value — the
 * spec's constraint is "confirmation, not entry" so the row always opens
 * with the derived value visible; the editor lets the reviewer flip
 * the provenance to `manual` when they override.
 *
 * The row never edits state on the server directly — it delegates to
 * an `onChange` callback the parent owns, so the parent can keep its
 * optimistic copy of the confirmation payload and re-render.
 */
import { useState, type ReactNode } from "react";
import { Pencil, Check, X } from "lucide-react";
import type { SowProvenanceEntry } from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { cn } from "../../../../lib/cn";
import { ProvenanceChip, displayValue } from "./provenance";
import { hasValue } from "./helpers";

export interface FieldRowProps {
  fieldKey: string;
  label: string;
  entry: SowProvenanceEntry | undefined;
  /** Optional custom renderer for the value (e.g. a link, a chip). */
  renderValue?: (entry: SowProvenanceEntry | undefined) => ReactNode;
  /** Called when the human saves an override. Provenance flips to `manual`. */
  onSaveOverride?: (fieldKey: string, newValue: string) => void;
  /** Disable the inline editor entirely (read-only rows). */
  readOnly?: boolean;
  /** Placeholder for the editor input. */
  placeholder?: string;
  /** Extra hint below the row. */
  hint?: ReactNode;
}

export function FieldRow({
  fieldKey,
  label,
  entry,
  renderValue,
  onSaveOverride,
  readOnly,
  placeholder,
  hint,
}: FieldRowProps) {
  const [editing, setEditing] = useState(false);
  const initial =
    entry?.value == null
      ? ""
      : typeof entry.value === "string"
        ? entry.value
        : Array.isArray(entry.value)
          ? entry.value.join(", ")
          : String(entry.value);
  const [draft, setDraft] = useState(initial);
  const populated = hasValue(entry);
  const rendered = renderValue ? renderValue(entry) : displayValue(entry);

  function commit() {
    if (onSaveOverride) onSaveOverride(fieldKey, draft.trim());
    setEditing(false);
  }

  return (
    <div
      data-testid={`field-row-${fieldKey}`}
      data-populated={populated ? "true" : "false"}
      className={cn(
        "flex flex-col gap-1 rounded-panel border border-divider bg-surface p-3",
        "sm:grid sm:grid-cols-[160px_minmax(0,1fr)_auto_auto] sm:items-center sm:gap-3",
      )}
    >
      <div className="text-secondary font-medium text-text-secondary">
        {label}
      </div>
      <div className="min-w-0">
        {editing ? (
          <Input
            aria-label={`Edit ${label}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={placeholder}
            data-testid={`field-edit-${fieldKey}`}
          />
        ) : populated ? (
          <div className="text-body text-text break-words">{rendered}</div>
        ) : (
          <div
            className="text-secondary text-text-secondary italic"
            data-testid={`field-missing-${fieldKey}`}
          >
            Not on the SOW — see "What's still needed"
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <ProvenanceChip entry={entry} />
      </div>
      <div className="flex items-center gap-1">
        {!readOnly && onSaveOverride ? (
          editing ? (
            <>
              <Button
                type="button"
                variant="tertiary"
                size="sm"
                onClick={commit}
                data-testid={`field-save-${fieldKey}`}
                aria-label={`Save ${label}`}
              >
                <Check className="h-4 w-4" aria-hidden />
              </Button>
              <Button
                type="button"
                variant="tertiary"
                size="sm"
                onClick={() => {
                  setDraft(initial);
                  setEditing(false);
                }}
                aria-label={`Cancel editing ${label}`}
              >
                <X className="h-4 w-4" aria-hidden />
              </Button>
            </>
          ) : (
            <Button
              type="button"
              variant="tertiary"
              size="sm"
              onClick={() => {
                setDraft(initial);
                setEditing(true);
              }}
              data-testid={`field-change-${fieldKey}`}
              aria-label={`Change ${label}`}
            >
              <Pencil className="h-4 w-4" aria-hidden />
              change
            </Button>
          )
        ) : null}
      </div>
      {hint ? (
        <div className="sm:col-span-4 text-secondary text-text-secondary">
          {hint}
        </div>
      ) : null}
    </div>
  );
}
