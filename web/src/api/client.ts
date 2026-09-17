/**
 * DealGate API client (Sprint 1).
 *
 * Manual TypeScript types for now; the auto-generated client lands after the
 * FastAPI OpenAPI schema is stable. In production the caller identity is a
 * Cognito access token (attached as `Authorization: Bearer ...`); in local
 * dev a `VITE_TEST_USER` env var falls back to the `X-Test-User` header the
 * FastAPI dev auth backend accepts.
 */

import { getAccessToken } from "../auth/cognito";

export type UUID = string;
export type ISODate = string; // YYYY-MM-DD
export type ISODateTime = string; // ISO 8601

export interface DealRow {
  id: UUID;
  hubspot_deal_id: string;
  owner_id: UUID | null;
  client_name: string | null;
  engagement_type: string | null;
  sales_stage: string | null;
  governance_status: string;
  next_client_action: string | null;
  next_client_date: ISODate | null;
  coverage_state: string;
}

export interface DealListResponse {
  items: DealRow[];
  page: number;
  size: number;
  total: number;
}

export interface TaskRow {
  id: UUID;
  subject: string;
  status: string;
  due_date: ISODate | null;
  escalation_level: number;
}

export interface AuditRow {
  id: UUID;
  ts: ISODateTime;
  actor_id: UUID | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface DealDetail extends DealRow {
  tasks: TaskRow[];
  audit: AuditRow[];
}

export interface DealPatch {
  owner_id?: UUID | null;
  engagement_type?: string | null;
  next_client_action?: string | null;
  next_client_date?: ISODate | null;
}

export interface MeResponse {
  id: UUID;
  email: string;
  name: string;
  groups: string[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  const token = await getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }
  // Dev-only fallback: FastAPI accepts `X-Test-User` when the dev auth
  // backend is enabled. We deliberately gate on `import.meta.env.DEV` so a
  // stale env var can never leak into a production build.
  if (import.meta.env.DEV) {
    const testUser = import.meta.env.VITE_TEST_USER as string | undefined;
    if (testUser) {
      headers["X-Test-User"] = testUser;
    }
  }
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
      ...(init.headers ?? {}),
    },
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `API error ${res.status}`;
    throw new ApiError(res.status, body, message);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export interface ListDealsQuery {
  owner?: "me" | UUID;
  status?: string;
  stage?: string;
  page?: number;
  size?: number;
}

export function getDeals(query: ListDealsQuery = {}): Promise<DealListResponse> {
  const params = new URLSearchParams();
  if (query.owner) params.set("owner", query.owner);
  if (query.status) params.set("status", query.status);
  if (query.stage) params.set("stage", query.stage);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<DealListResponse>(`/deals${qs ? `?${qs}` : ""}`);
}

export function getDeal(id: UUID): Promise<DealDetail> {
  return request<DealDetail>(`/deals/${id}`);
}

export function patchDeal(id: UUID, patch: DealPatch): Promise<DealDetail> {
  return request<DealDetail>(`/deals/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>(`/me`);
}

// --- audit viewer (S1-E1) --------------------------------------------------

export interface AuditListRow {
  id: UUID;
  ts: ISODateTime;
  actor_id: UUID | null;
  actor_email: string | null;
  action: string;
  entity: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  correlation_id: string | null;
  prev_hash: string | null;
  row_hash: string;
}

export interface AuditListResponse {
  items: AuditListRow[];
  page: number;
  size: number;
  total: number;
}

export interface AuditFilters {
  entity?: string;
  entity_id?: string;
  actor_id?: UUID;
  action?: string;
  since?: ISODateTime;
  until?: ISODateTime;
  page?: number;
  size?: number;
}

export interface VerifyAuditResponse {
  ok: boolean;
  first_broken_row: UUID | null;
  checked: number;
  message: string;
}

function auditParams(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.entity) params.set("entity", filters.entity);
  if (filters.entity_id) params.set("entity_id", filters.entity_id);
  if (filters.actor_id) params.set("actor_id", filters.actor_id);
  if (filters.action) params.set("action", filters.action);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.size) params.set("size", String(filters.size));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function listAudit(filters: AuditFilters = {}): Promise<AuditListResponse> {
  return request<AuditListResponse>(`/audit${auditParams(filters)}`);
}

export interface VerifyAuditFilters {
  entity?: string;
  entity_id?: string;
}

export function verifyAudit(
  filters: VerifyAuditFilters = {},
): Promise<VerifyAuditResponse> {
  const params = new URLSearchParams();
  if (filters.entity) params.set("entity", filters.entity);
  if (filters.entity_id) params.set("entity_id", filters.entity_id);
  const qs = params.toString();
  return request<VerifyAuditResponse>(`/audit/verify${qs ? `?${qs}` : ""}`);
}

// --- admin users (S1-E1) ---------------------------------------------------

export interface UserRow {
  id: UUID;
  email: string;
  name: string;
  groups: string[];
  last_login: ISODateTime | null;
  created_at: ISODateTime;
}

export interface UserListResponse {
  items: UserRow[];
  page: number;
  size: number;
  total: number;
  allowed_groups: string[];
}

export interface InviteUserBody {
  email: string;
  name: string;
  groups: string[];
}

export interface PatchGroupsBody {
  add: string[];
  remove: string[];
}

export interface RoleHistoryRow {
  id: UUID;
  ts: ISODateTime;
  actor_id: UUID | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface RoleHistoryResponse {
  items: RoleHistoryRow[];
}

export interface ListUsersQuery {
  search?: string;
  group?: string;
  page?: number;
  size?: number;
}

export function listUsers(query: ListUsersQuery = {}): Promise<UserListResponse> {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.group) params.set("group", query.group);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<UserListResponse>(`/admin/users${qs ? `?${qs}` : ""}`);
}

export function inviteUser(body: InviteUserBody): Promise<UserRow> {
  return request<UserRow>(`/admin/users`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchUserGroups(
  userId: UUID,
  body: PatchGroupsBody,
): Promise<UserRow> {
  return request<UserRow>(`/admin/users/${userId}/groups`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getRoleHistory(userId: UUID): Promise<RoleHistoryResponse> {
  return request<RoleHistoryResponse>(`/admin/users/${userId}/role_history`);
}
