import { request } from "./client";

export interface ExtractionConflict {
  field: string;
  review_token: string;
  current: { value: unknown; provenance?: string; page_ref?: number | null; status?: string };
  candidate: { value: unknown; provenance?: string; page_ref?: number | null; status?: string };
}
export const getExtractionConflicts = (versionId: string) => request<{ items: ExtractionConflict[] }>(
  `/sow/versions/${encodeURIComponent(versionId)}/extraction-conflicts`);
export const resolveExtractionConflict = (versionId: string, field: string, body: {
  review_token: string;
  decision: "keep_confirmed" | "accept_candidate";
  reason: string;
}) => request<{ items: ExtractionConflict[] }>(
  `/sow/versions/${encodeURIComponent(versionId)}/extraction-conflicts/${encodeURIComponent(field)}`,
  { method: "POST", body: JSON.stringify(body) });
