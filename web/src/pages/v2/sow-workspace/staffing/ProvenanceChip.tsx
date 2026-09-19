/**
 * S9 — provenance chip.
 *
 * Every derived field on the SOW-first pipeline must carry a
 * provenance stamp (CLAUDE.md rule 10, docs/sow-first-principles.md).
 * The chip surfaces where the value came from so a reviewer can trust
 * or challenge it without opening a second screen. Tones follow the
 * v2.1 backlog:
 *
 *   extracted   — primary subtle (from the SOW itself, with a page ref)
 *   looked_up   — neutral (a past record, e.g. client card / past SOW)
 *   calculated  — success (deterministic math from other derived values)
 *   defaulted   — warning (fallback from a catalog or company default)
 *   manual      — warning (a human overrode the derivation)
 */
import { AlertTriangle } from "lucide-react";
import type { DeliveryLineProvenance, ProvenanceKind } from "../../../../api/client";
import { cn } from "../../../../lib/cn";

interface ProvenanceChipProps {
  meta: DeliveryLineProvenance | null | undefined;
  /** Falls back to the kind's default label when `meta.source_label` is
   *  absent; useful when the API returns bare `{provenance: "manual"}`. */
  fallbackLabel?: string;
  className?: string;
}

const KIND_LABEL: Record<ProvenanceKind, string> = {
  extracted: "extracted from SOW",
  looked_up: "looked up",
  calculated: "calculated",
  defaulted: "defaulted",
  manual: "manual",
};

const KIND_CLASSES: Record<ProvenanceKind, string> = {
  extracted: "bg-primary-subtle text-primaryText border-primary/30",
  looked_up: "bg-surface-sunken text-text-secondary border-border",
  calculated: "bg-success-surface text-success border-success/30",
  defaulted: "bg-warning-surface text-warning border-warning/30",
  manual: "bg-warning-surface text-warning border-warning/30",
};

export function ProvenanceChip({
  meta,
  fallbackLabel,
  className,
}: ProvenanceChipProps) {
  if (!meta || !meta.provenance) {
    // A missing provenance is itself a defect signal — surface it in the
    // UI so the reviewer notices, rather than silently rendering nothing.
    return (
      <span
        data-testid="provenance-missing"
        className={cn(
          "inline-flex items-center gap-1 rounded-chip border h-[22px] px-2 text-[12px] font-medium",
          "bg-danger-surface text-danger border-danger/30",
          className,
        )}
        title="No provenance recorded — this is a defect per CLAUDE.md rule 10."
      >
        <AlertTriangle className="h-3 w-3" aria-hidden />
        no provenance
      </span>
    );
  }
  const kind = meta.provenance;
  const label = meta.source_label ?? fallbackLabel ?? KIND_LABEL[kind];
  const displayLabel = kind === "extracted" && meta.page_ref != null
    ? `${label} · p.${meta.page_ref}`
    : label;
  return (
    <span
      data-testid={`provenance-chip-${kind}`}
      data-provenance={kind}
      className={cn(
        "inline-flex items-center gap-1 rounded-chip border h-[22px] px-2 text-[12px] font-medium whitespace-nowrap",
        KIND_CLASSES[kind],
        className,
      )}
      title={
        meta.confidence != null
          ? `${displayLabel} · confidence ${(meta.confidence * 100).toFixed(0)}%`
          : displayLabel
      }
    >
      <span
        aria-hidden
        className={cn(
          "inline-block h-[6px] w-[6px] rounded-avatar",
          kind === "extracted" && "bg-primary",
          kind === "looked_up" && "bg-text-secondary",
          kind === "calculated" && "bg-success",
          (kind === "defaulted" || kind === "manual") && "bg-warning",
        )}
      />
      {displayLabel}
    </span>
  );
}

/**
 * Small helper for the warning icon carried by rows whose derivation
 * needs human attention (e.g. "estimated from past SOW"). Sits next
 * to the provenance chip.
 */
export function ProvenanceWarning({
  message,
  className,
}: {
  message: string | null | undefined;
  className?: string;
}) {
  if (!message) return null;
  return (
    <span
      data-testid="provenance-warning"
      className={cn(
        "inline-flex items-center gap-1 text-warning text-[12px]",
        className,
      )}
      title={message}
    >
      <AlertTriangle className="h-3 w-3" aria-hidden />
      <span className="sr-only">Warning: </span>
      {message}
    </span>
  );
}
