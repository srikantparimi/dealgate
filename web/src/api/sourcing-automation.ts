import { request } from "./client";

export interface AutomationRule {
  state: "unconfigured" | "configured";
  domain: "sourcing_refresh";
  enabled: boolean;
  id: string | null;
  revision: number | null;
  source_scope: "authorized_sources";
  created_by?: string;
  created_at?: string;
  reason?: string;
}
export interface AutomationJob {
  id: string;
  status: "pending" | "failed" | "done" | "review" | "obsolete" | "disabled" | "forbidden" | "dead";
  attempts: number;
  rule_version_id: string;
  source_id: string;
  source_version: string;
  event_key: string;
  next_attempt_at: string | null;
  completed_at: string | null;
  created_at: string;
  last_error: string | null;
  result_version_id: string | null;
  can_retry: boolean;
}
export interface AutomationJobs {
  items: AutomationJob[];
  last_success_at: string | null;
}
export const getAutomationRule = () => request<AutomationRule>("/people/sourcing/automation");
export const saveAutomationRule = (body: {
  expected_version_id: string | null;
  enabled: boolean;
  request_key: string;
  reason: string;
}) => request<AutomationRule>("/people/sourcing/automation", { method: "POST", body: JSON.stringify(body) });
export const getAutomationHistory = (page = 1) => request<{
  items: AutomationRule[]; current_version_id: string | null;
}>(`/people/sourcing/automation/history?page=${page}&size=25`);
export const getAutomationJobs = (page = 1) =>
  request<AutomationJobs>(`/people/sourcing/automation/jobs?page=${page}&size=25`);
export const retryAutomationJob = (id: string, body: { expected_attempts: number; reason: string }) =>
  request<AutomationJob>(`/people/sourcing/automation/jobs/${encodeURIComponent(id)}/retry`, {
    method: "POST", body: JSON.stringify(body),
  });
