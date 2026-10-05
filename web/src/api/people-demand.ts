import { request } from "./client";

export interface DemandLine {
  line_key: string;
  component_id: string;
  assignment_id: string;
  role: string;
  skills: string[];
  level: string;
  location: string;
  timezone: string;
  quantity: number | null;
  allocation: string | null;
  start_date: string | null;
  end_date: string | null;
  delivery_model: string;
  retained_person_ids?: string[];
  evidence: string[];
  missing: string[];
}
export interface DemandSource {
  source_id?: string;
  source_kind?: "plan" | "project";
  project_id?: string | null;
  plan_id: string | null;
  account_id: string;
  account_name?: string | null;
  source_url?: string | null;
  title: string;
  source_version_id: string;
  source_revision: number;
  lifecycle: string;
  selected: boolean;
  probability: string | null;
  publication_id?: string | null;
  publication_version_id: string | null;
  state: "pending" | "current" | "stale";
  missing: string[];
  lines: DemandLine[];
}
export interface DemandSources {
  items: DemandSource[];
  scope_label: string;
  is_reservation: false;
  schema_version: string;
}
export interface DemandEnrichment {
  skills?: string[];
  level?: string;
  evidence: string[];
}
export interface PublishDemandInput {
  plan_id?: string | null;
  project_id?: string;
  expected_source_version_id: string;
  expected_publication_version_id: string | null;
  request_key: string;
  reason: string;
  enrichments: Record<string, DemandEnrichment>;
}
export interface DemandPublication {
  publication_id: string;
  version_id: string;
  revision: number;
  source_version_id: string;
  missing: string[];
  is_reservation: false;
}
export const getDemandSources = (signal?: AbortSignal) =>
  request<DemandSources>("/people/demand", { signal });
export const publishDemand = (body: PublishDemandInput) =>
  request<DemandPublication>(body.project_id ? "/people/demand/project-publications" : "/people/demand/publications", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const demandSourceId = (source: DemandSource | undefined) =>
  source?.source_id ?? source?.project_id ?? source?.plan_id ?? "";
