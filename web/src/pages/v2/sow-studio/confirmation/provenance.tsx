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

/** True when the extractor looked and the value simply is not in the document. */
export function isMissing(entry: SowProvenanceEntry | undefined): boolean {
  if (!entry) return true;
  const v = entry.value;
  const empty =
    v === null ||
    v === undefined ||
    v === "" ||
    (Array.isArray(v) && v.length === 0);
  return empty || entry.status === "disputed";
}

/**
 * Reference label for a citation.
 *
 * `page_ref` is a page number for a PDF but a body-block ordinal for a Word
 * file, which has no pages (see docs/adr/0002). Labelling a Word reference
 * "p.78" points the reader at a page that does not exist, so the unit comes
 * from the version's `ref_unit`.
 */
export function refLabel(pageRef: number, refUnit?: string | null): string {
  return refUnit === "block" ? `\u00b6${pageRef}` : `p.${pageRef}`;
}

export function provenanceLabel(
  entry: SowProvenanceEntry | undefined,
  refUnit?: string | null,
): string {
  if (!entry) return "unknown";
  // An absent value must never wear a citation chip. The chip asserting
  // "extracted · p.78" beside a row reading "Not on the SOW" is the badge
  // contradicting the row, and the reader cannot tell it from a real one.
  if (isMissing(entry)) return "needs you";
  const prov = entry.provenance;
  switch (prov) {
    case "extracted":
      return entry.page_ref != null
        ? `extracted · ${refLabel(entry.page_ref, refUnit)}`
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
  /** "page" for a PDF, "block" for a Word file. From the version metadata. */
  refUnit?: string | null;
  className?: string;
}

/**
 * Renders the provenance badge for a single field. Manual entries get a
 * loud outline via `data-manual="true"` so the reviewer sees the human
 * override at a glance (spec rule 10 — "manual is loud").
 */
export function ProvenanceChip({
  entry,
  refUnit,
  className,
}: ProvenanceChipProps) {
  const prov = entry?.provenance ?? "manual";
  const missing = isMissing(entry);
  // A gap is a gap regardless of which provenance flavour produced it, and
  // it reads as a warning — the reviewer has to act on it.
  const tone = missing ? "warning" : PROVENANCE_TONE[prov];
  const isManual = prov === "manual" && !missing;
  return (
    <StatusBadge
      tone={tone}
      label={provenanceLabel(entry, refUnit)}
      data-provenance={missing ? "needs_you" : prov}
      data-manual={isManual ? "true" : undefined}
      data-testid={missing ? "provenance-needs_you" : `provenance-${prov}`}
      className={cn(
        isManual && "ring-1 ring-warning/50",
        missing && "ring-1 ring-warning/60",
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
