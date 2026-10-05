import { request } from "./client";
import type { DemandSource } from "./people-demand";

export interface SourcingRule {
  skill: string;
  location: string;
  lead_days: number;
}
export interface SourcingRules {
  state: "unconfigured" | "configured";
  id: string | null;
  revision: number | null;
  rules: SourcingRule[];
  reason?: string;
  created_at?: string;
}
export interface SourcingSource extends DemandSource {
  publication_id: string | null;
}
export interface SourcingRow {
  id: string;
  role: string;
  skills: string[];
  level: string;
  location: string;
  timezone: string;
  quantity: number;
  retained_quantity: number;
  incremental_quantity: number;
  matched_quantity: number;
  gap_quantity: number;
  continuity_gap_quantity: number;
  incremental_gap_quantity: number;
  gap_fte: string;
  start: string;
  end_exclusive: string;
  sourcing_by: string | null;
  missing: string[];
}
export interface SourcingDraft {
  id: string;
  draft_id: string;
  revision: number;
  demand_version_id: string;
  rule_version_id: string;
  source_watermark: string;
  reason: string;
  created_by: string;
  created_at: string;
  is_reservation: false;
  snapshot: {
    title: string;
    probability: string | null;
    lifecycle: string;
    source_version_id: string;
    source_url: string | null;
    complete: boolean;
    missing: string[];
    calculation_version: string;
    is_reservation: false;
    rows: SourcingRow[];
  };
}
export interface SourcingHistory {
  items: SourcingDraft[];
  current_version_id: string | null;
  state: "missing" | "current" | "stale";
}
export const getSourcingRules = () =>
  request<SourcingRules>("/people/sourcing/rules");
export const saveSourcingRules = (body: {
  rules: SourcingRule[];
  expected_version_id: string | null;
  request_key: string;
  reason: string;
}) =>
  request<SourcingRules>("/people/sourcing/rules", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const getSourcingSources = () =>
  request<{ items: SourcingSource[] }>("/people/demand");
export const getSourcingHistory = (publicationId: string, page = 1) =>
  request<SourcingHistory>(
    `/people/sourcing/drafts?publication_id=${encodeURIComponent(publicationId)}&page=${page}&size=50`,
  );
export const prepareSourcingDraft = (body: {
  publication_id: string;
  expected_demand_version_id: string;
  expected_rule_version_id: string;
  expected_draft_version_id: string | null;
  request_key: string;
  reason: string;
}) =>
  request<SourcingDraft>("/people/sourcing/drafts", {
    method: "POST",
    body: JSON.stringify(body),
  });
