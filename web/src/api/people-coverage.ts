import { request } from "./client";
import type { DemandSources } from "./people-demand";

export interface CoverageMapping {
  plan_line_key: string;
  project_line_key: string;
  plan_slots: number[];
  project_slots: number[];
  start_date: string;
  end_date: string;
}
export interface CoverageVersion {
  id: string;
  version_id: string;
  revision: number;
  plan_publication_id: string;
  project_publication_id: string;
  plan_version_id: string;
  project_version_id: string;
  mappings: CoverageMapping[];
  reason: string;
  created_by: string;
  created_at: string;
  state: "current" | "stale";
  is_reservation: false;
}
export interface CoverageEnvelope {
  items: CoverageVersion[];
  current_version_id: string | null;
  is_reservation: false;
}
export interface CoverageInput {
  plan_publication_id: string;
  project_publication_id: string;
  expected_plan_version_id: string;
  expected_project_version_id: string;
  expected_mapping_version_id: string | null;
  request_key: string;
  reason: string;
  mappings: CoverageMapping[];
}
export const getCoverage = (planId: string, rootId?: string, page = 1) => {
  const query = new URLSearchParams({
    plan_publication_id: planId,
    page: String(page),
    size: "50",
  });
  if (rootId) query.set("root_id", rootId);
  return request<CoverageEnvelope>(`/people/demand/coverage?${query}`);
};
export const getCoverageSources = () =>
  request<DemandSources>("/people/demand");
export const saveCoverage = (body: CoverageInput) =>
  request<CoverageVersion>("/people/demand/coverage", {
    method: "POST",
    body: JSON.stringify(body),
  });
