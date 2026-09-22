/**
 * Read-only helpers for the confirmation screen.
 *
 * Every derivation here is either a lookup into the payload the API
 * ships or a display-only string. There is no business math in the
 * browser (spec §21 + CLAUDE.md rule 2) — even the floor pass/fail
 * comes from `payload.floors`.
 */
import type {
  EngagementType,
  SowConfirmationApproverFunction,
  SowConfirmationPayload,
  SowProvenanceEntry,
} from "../../../../api/client";

/**
 * The scope + terms rows the confirmation screen renders. The tag
 * matches the field key inside `extracted_fields`; the API returns
 * every one wrapped in a provenance envelope.
 */
export const SCOPE_FIELDS: Array<{ key: string; label: string }> = [
  { key: "price", label: "Price" },
  { key: "currency", label: "Currency" },
  { key: "term_start", label: "Term start" },
  { key: "term_end", label: "Term end" },
  { key: "notice_date", label: "Notice date" },
  { key: "billing_basis", label: "Billing basis" },
  { key: "deliverables", label: "Deliverables" },
  { key: "milestones", label: "Milestones" },
  { key: "acceptance_criteria", label: "Acceptance" },
  { key: "signatories", label: "Signatories" },
];

/** The four Source & type rows in section 1. */
export const SOURCE_FIELDS: Array<{ key: string; label: string }> = [
  { key: "client_entity", label: "Client + entity" },
  { key: "sow_title", label: "SOW title" },
  { key: "file", label: "SOW file" },
  { key: "engagement_type", label: "Engagement type" },
];

/**
 * Return the provenance envelope for one field key. Legacy rows that
 * were stored as plain scalars degrade to `manual` on read (mirrors
 * `api/app/services/provenance.py::read`).
 */
export function readField(
  fields: Record<string, unknown> | null | undefined,
  key: string,
): SowProvenanceEntry | undefined {
  if (!fields) return undefined;
  const raw = fields[key];
  if (raw === undefined) return undefined;
  if (raw === null) {
    return { value: null, provenance: "manual" };
  }
  if (typeof raw === "object" && "provenance" in (raw as object)) {
    return raw as SowProvenanceEntry;
  }
  if (typeof raw === "object" && "value" in (raw as object)) {
    // Legacy row without provenance key — infer from page_ref presence.
    const r = raw as { value: unknown; page_ref?: number | null; status?: string };
    return {
      value: r.value,
      provenance: r.page_ref != null ? "extracted" : "manual",
      page_ref: r.page_ref ?? null,
      status: (r.status ?? "unconfirmed") as
        | "unconfirmed"
        | "confirmed"
        | "disputed",
    };
  }
  return { value: raw, provenance: "manual" };
}

/**
 * True when the entry has a genuinely populated value. Used to gate
 * the "count of blank rows on open" test — the constraint is 0.
 */
export function hasValue(entry: SowProvenanceEntry | undefined): boolean {
  if (!entry) return false;
  const v = entry.value;
  if (v === null || v === undefined) return false;
  if (typeof v === "string") return v.trim().length > 0;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v as object).length > 0;
  return true;
}

/** Pretty label for one of the six engagement types. */
export const ENGAGEMENT_LABEL: Record<EngagementType, string> = {
  staff_aug: "Staff augmentation",
  single_resource: "Single resource",
  fixed_price: "Fixed price",
  assessment: "Assessment",
  tm: "Time & materials",
  managed_service: "Managed service",
};

export function engagementLabel(type: string | null | undefined): string {
  if (!type) return "Unknown";
  return (
    ENGAGEMENT_LABEL[type as EngagementType] ??
    type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/** Human-facing label for the four functions. */
export const FUNCTION_LABEL: Record<SowConfirmationApproverFunction, string> = {
  delivery: "Delivery",
  hr: "HR",
  finance: "Finance",
  legal: "Legal",
};

/**
 * Given the full payload, return the count of `needs_you` items that
 * still block submit. Zero means the primary button can enable.
 */
export function blockingCount(payload: SowConfirmationPayload): number {
  return (payload.scope_blockers ?? payload.needs_you)?.length ?? 0;
}

/**
 * True when the classifier is confident enough that no picker is
 * required. Mirrors the server-side threshold (default 0.85) — we do
 * not re-run the threshold here; we consult `engagement.auto_confirm`.
 */
export function engagementIsAmbiguous(
  payload: SowConfirmationPayload,
): boolean {
  return !payload.engagement.auto_confirm;
}

/** Money display — the string is already formatted by the API. Never math here. */
export function displayMoney(
  value: string | null | undefined,
  currency: string | null | undefined,
): string | null {
  if (value == null || value === "") return null;
  const cur = currency ? ` ${currency}` : "";
  return `${value}${cur}`;
}
