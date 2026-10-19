// S24-AG1 · the ONE label and tone map for an agreement's seven states, used by
// the Agreements page, the client panel, the Pipeline tags and the on-file
// strips, so the wording cannot drift. Wording follows the approved prototype;
// tones map its colours onto the kit (violet → progress, green → success,
// amber → warning, red → danger).
import type { ReactNode } from "react";

import type { DocState, Relationship } from "../api/agreements";
import { cn } from "../lib/cn";
import { Badge } from "./primitives/badge";

type Tone = "neutral" | "success" | "warning" | "danger" | "progress";

export const DOC_STATE_TEXT: Record<DocState, string> = {
  client: "✓ Client copy",
  standard: "✓ Standard copy",
  covered: "✓ Marked covered",
  missing: "Missing",
  due_later: "Due at stage 2",
  not_needed: "Not needed now",
  existing_none: "Existing · none attached",
};

/** The plain label (no check mark), for CSV-like text and screen-reader sentences. */
export const DOC_STATE_LABEL: Record<DocState, string> = {
  client: "Client copy",
  standard: "Standard copy",
  covered: "Marked covered",
  missing: "Missing",
  due_later: "Due at stage 2",
  not_needed: "Not needed now",
  existing_none: "Existing, none attached",
};

export const DOC_STATE_TONE: Record<DocState, Tone> = {
  client: "success",
  standard: "progress",
  covered: "success",
  missing: "danger",
  due_later: "warning",
  not_needed: "neutral",
  existing_none: "neutral",
};

/** A compact tag: the kit's Badge without the leading dot; wraps instead of widening its column. */
export function AgreementTag({
  tone = "neutral",
  children,
  className,
  wrap = true,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  wrap?: boolean;
}) {
  return (
    <Badge
      tone={tone}
      showDot={false}
      className={cn("h-auto min-h-[22px] py-[3px] leading-tight", wrap ? "whitespace-normal" : "whitespace-nowrap", className)}
    >
      {children}
    </Badge>
  );
}

/** One kind's state, e.g. "✓ Standard copy". `kind` adds an accessible prefix ("NDA: …") when the column has no header. */
export function AgreementStateTag({ state, kind, srKind = false }: { state: DocState; kind?: "NDA" | "MSA"; srKind?: boolean }) {
  return (
    <AgreementTag tone={DOC_STATE_TONE[state]}>
      {kind && srKind ? <span className="sr-only">{kind}: </span> : null}
      {DOC_STATE_TEXT[state]}
    </AgreementTag>
  );
}

export function RelationshipTag({ relationship }: { relationship: Relationship }) {
  return relationship === "existing" ? (
    <AgreementTag tone="success" wrap={false}>
      Existing
    </AgreementTag>
  ) : (
    <AgreementTag tone="progress" wrap={false}>
      Net new
    </AgreementTag>
  );
}

export const FLAG_TEXT: Record<string, { text: string; tone: Tone }> = {
  possible_duplicate: { text: "Possible duplicate", tone: "warning" },
  test_data: { text: "Test data", tone: "neutral" },
  unknown_company: { text: "Unknown company", tone: "warning" },
  no_hubspot_link: { text: "No HubSpot link", tone: "neutral" },
};
