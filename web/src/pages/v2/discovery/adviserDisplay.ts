/**
 * Adviser view helpers — spec §10.
 *
 * The Adviser endpoint returns either an `AdviserEstimate` (research
 * succeeded, priced team + evidence) or an `AdviserQuestions` object
 * (input insufficient). These helpers normalise the source array —
 * every citation is required to carry at least a `url` and a
 * `retrieved_at`; anything without them is dropped so the UI cannot
 * fabricate a URL (spec §10 non-negotiable, blueprint §6).
 */
import type { AdviserResult, AdviserEstimate } from "../../../api/client";

export interface EvidenceSource {
  url: string;
  title: string;
  retrievedAt: string;
  relevance: string | null;
}

/**
 * Filter + shape the raw `sources[]` array to what the UI can render.
 * A source without a URL never appears — that is the "no fabricated
 * citation" rule. Retrieved date defaults to "Unknown" only when the
 * source itself omits it; we never invent one.
 */
export function toEvidence(
  sources: Array<Record<string, unknown>> | undefined | null,
): EvidenceSource[] {
  if (!Array.isArray(sources)) return [];
  const rows: EvidenceSource[] = [];
  for (const s of sources) {
    if (!s || typeof s !== "object") continue;
    const rawUrl = (s as { url?: unknown }).url;
    if (typeof rawUrl !== "string" || rawUrl.length === 0) continue;
    const url = rawUrl.trim();
    if (!/^https?:\/\//i.test(url)) continue;
    const title =
      typeof (s as { title?: unknown }).title === "string" &&
      (s as { title: string }).title.trim().length > 0
        ? (s as { title: string }).title
        : url;
    const retrievedAt =
      typeof (s as { retrieved_at?: unknown }).retrieved_at === "string"
        ? (s as { retrieved_at: string }).retrieved_at
        : typeof (s as { retrievedAt?: unknown }).retrievedAt === "string"
          ? (s as { retrievedAt: string }).retrievedAt
          : "Unknown";
    const relevance =
      typeof (s as { relevance?: unknown }).relevance === "string"
        ? (s as { relevance: string }).relevance
        : typeof (s as { snippet?: unknown }).snippet === "string"
          ? (s as { snippet: string }).snippet
          : null;
    rows.push({ url, title, retrievedAt, relevance });
  }
  return rows;
}

/**
 * A saved-estimate label used in the versions list. Uses the API's
 * `label` when present, otherwise a stable "Estimate • hash" fallback
 * so the row never renders "undefined".
 */
export function estimateLabel(est: AdviserEstimate): string {
  return est.label && est.label.trim().length > 0
    ? est.label
    : `Estimate ${est.id.slice(0, 8)}`;
}

export function isQuestionsResult(
  r: AdviserResult,
): r is Extract<AdviserResult, { kind: "questions" }> {
  return r.kind === "questions";
}

export function isEstimateResult(
  r: AdviserResult,
): r is Extract<AdviserResult, { kind: "estimate" }> {
  return r.kind === "estimate";
}

/** Human confidence tone for the section-confidence chip. */
export function confidenceTone(
  c: string | undefined,
): "ok" | "warn" | "neutral" {
  if (!c) return "neutral";
  const v = c.toLowerCase();
  if (v === "high") return "ok";
  if (v === "medium") return "warn";
  return "neutral";
}
