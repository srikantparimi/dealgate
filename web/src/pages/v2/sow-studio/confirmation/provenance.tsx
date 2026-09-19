/**
 * Provenance chip helpers (Sprint 9 Wave 2 · sow-first §1 rule 10).
 *
 * Every visible field on the confirmation screen carries one of five
 * provenance flavours. The tag maps to a v2.1 status tone:
 *
 *   extracted  → `progress` (violet-subtle, most common; quiet)
 *   looked_up  → `neutral`  (grey, master-data lookup)
 *   calculated → `success`  (green, GM library)
 *   defaulted  → `warning`  (amber, "fallback in play")
 *   manual     → `warning`  with a border, LOUDER — spec asks that
 *                any hand-edited field is highlighted so the reviewer
 *                sees the human override at a glance.
 *
 * The tag is display-only; the underlying provenance value comes from
 * the API (`SowProvenanceEntry.provenance`), never inferred here.
 */
import type { ReactNode } from "react";
import type { SowProvenance, SowProvenanceEntry } from "../../../../api/client";
import { StatusBadge, type StatusTone } from "../../../../ui-v2/StatusBadge";
import { cn } from "../../../../lib/cn";

export const PROVENANCE_TONE: Record<SowProvenance, StatusTone> = {
  extracted: "progress",
  looked_up: "neutral",
  calculated: "success",
  defaulted: "warning",
  manual: "warning",
};

export function provenanceLabel(entry: SowProvenanceEntry | undefined): string {
  if (!entry) return "unknown";
  const prov = entry.provenance;
  switch (prov) {
    case "extracted":
      return entry.page_ref != null
        ? `extracted · p.${entry.page_ref}`
        : "extracted";
    case "looked_up":
      return entry.source_id
        ? `looked up · ${shortSource(entry.source_id)}`
        : "looked up";
    case "calculated":
      return "calculated";
    case "defaulted":
      return entry.warning ? `defaulted · ${entry.warning}` : "defaulted";
    case "manual":
      return "manual";
    default:
      return String(prov);
  }
}

function shortSource(source: string): string {
  // UUID? show the first 6 chars. Otherwise keep the whole string.
  if (/^[0-9a-f-]{20,}$/i.test(source)) {
    return source.slice(0, 6);
  }
  return source.length > 40 ? `${source.slice(0, 37)}…` : source;
}

export interface ProvenanceChipProps {
  entry: SowProvenanceEntry | undefined;
  className?: string;
}

/**
 * Renders the provenance badge for a single field. Manual entries get a
 * loud outline via `data-manual="true"` so the reviewer sees the human
 * override at a glance (spec rule 10 — "manual is loud").
 */
export function ProvenanceChip({ entry, className }: ProvenanceChipProps) {
  const prov = entry?.provenance ?? "manual";
  const tone = PROVENANCE_TONE[prov];
  const isManual = prov === "manual";
  return (
    <StatusBadge
      tone={tone}
      label={provenanceLabel(entry)}
      data-provenance={prov}
      data-manual={isManual ? "true" : undefined}
      data-testid={`provenance-${prov}`}
      className={cn(
        isManual && "ring-1 ring-warning/50",
        className,
      )}
    />
  );
}

/** Small helper: pull the display value out of a mixed provenance entry. */
export function displayValue(entry: SowProvenanceEntry | undefined): ReactNode {
  if (!entry) return null;
  const v = entry.value;
  if (v === null || v === undefined || v === "") return null;
  if (Array.isArray(v)) {
    return v.length ? v.join(", ") : null;
  }
  if (typeof v === "object") {
    return JSON.stringify(v);
  }
  return String(v);
}
