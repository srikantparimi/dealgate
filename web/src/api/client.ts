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
  client_id: UUID | null;
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

// --- agreements (S2-E3) ----------------------------------------------------

export type AgreementState =
  | "missing"
  | "requested"
  | "drafting"
  | "under_review"
  | "sent"
  | "partially_signed"
  | "executed"
  | "expired"
  | "terminated"
  | "superseded";

export type AgreementKind = "NDA" | "MSA";

export interface Signatory {
  name: string;
  email: string;
  role?: string;
}

export interface AgreementRow {
  id: UUID;
  legal_entity_id: UUID;
  kind: AgreementKind;
  state: AgreementState;
  owner_email: string | null;
  next_action: string | null;
  due_date: ISODate | null;
  effective_from: ISODate | null;
  expiry: ISODate | null;
  notice_days: number | null;
  evidence_s3_key: string | null;
  signatories: Signatory[] | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AgreementListResponse {
  items: AgreementRow[];
  allowed_states: AgreementState[];
}

export interface ListAgreementsQuery {
  legal_entity_id?: UUID;
  state?: AgreementState;
  expiring_within_days?: number;
}

export interface CreateAgreementBody {
  legal_entity_id: UUID;
  type: AgreementKind;
  state?: AgreementState;
  owner_email?: string | null;
  next_action?: string | null;
  due_date?: ISODate | null;
}

export interface PatchAgreementBody {
  state?: AgreementState;
  next_action?: string | null;
  due_date?: ISODate | null;
  effective_from?: ISODate | null;
  expiry?: ISODate | null;
  notice_days?: number | null;
  evidence_s3_key?: string | null;
  signatories?: Signatory[] | null;
}

export interface UploadUrlRequest {
  filename: string;
  content_type: string;
}

export interface UploadUrlResponse {
  url: string;
  s3_key: string;
  method: "PUT";
  expires_in: number;
  required_headers?: Record<string, string> | null;
}

export interface DownloadUrlResponse {
  url: string;
  expires_in: number;
}

function agreementParams(query: ListAgreementsQuery): string {
  const params = new URLSearchParams();
  if (query.legal_entity_id) params.set("legal_entity_id", query.legal_entity_id);
  if (query.state) params.set("state", query.state);
  if (query.expiring_within_days !== undefined) {
    params.set("expiring_within_days", String(query.expiring_within_days));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function listAgreements(
  query: ListAgreementsQuery = {},
): Promise<AgreementListResponse> {
  return request<AgreementListResponse>(`/agreements${agreementParams(query)}`);
}

export function createAgreement(body: CreateAgreementBody): Promise<AgreementRow> {
  return request<AgreementRow>(`/agreements`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchAgreement(
  id: UUID,
  body: PatchAgreementBody,
): Promise<AgreementRow> {
  return request<AgreementRow>(`/agreements/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getUploadUrl(
  id: UUID,
  body: UploadUrlRequest,
): Promise<UploadUrlResponse> {
  return request<UploadUrlResponse>(`/agreements/${id}/evidence-upload-url`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getDownloadUrl(id: UUID): Promise<DownloadUrlResponse> {
  return request<DownloadUrlResponse>(`/agreements/${id}/evidence-download-url`);
}

// --- clients (S2 E3) -------------------------------------------------------

export interface ClientListRow {
  id: UUID;
  name: string;
  hubspot_company_id: string | null;
  coverage_state: string;
  opportunity_count: number;
  owner_ids: UUID[];
}

export interface ClientListResponse {
  items: ClientListRow[];
  page: number;
  size: number;
  total: number;
}

export interface ClientLegalEntity {
  id: UUID;
  name: string;
  country: string | null;
}

export interface ClientAgreement {
  id: UUID;
  legal_entity_id: UUID;
  kind: string;
  effective_date: ISODate | null;
  expiry_date: ISODate | null;
}

export interface ClientOpportunity {
  id: UUID;
  hubspot_deal_id: string;
  governance_status: string;
  sales_stage: string | null;
  engagement_type: string | null;
  owner_id: UUID | null;
  next_client_action: string | null;
  next_client_date: ISODate | null;
}

export interface ClientRecentActivity {
  id: UUID;
  ts: ISODateTime;
  actor_id: UUID | null;
  action: string;
  entity: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface ClientDetail {
  id: UUID;
  name: string;
  hubspot_company_id: string | null;
  timezone: string | null;
  coverage_state: string;
  legal_entities: ClientLegalEntity[];
  agreements: ClientAgreement[];
  opportunities: ClientOpportunity[];
  recent_activity: ClientRecentActivity[];
}

export interface ListClientsQuery {
  owner?: "me" | UUID;
  search?: string;
  page?: number;
  size?: number;
}

export function listClients(query: ListClientsQuery = {}): Promise<ClientListResponse> {
  const params = new URLSearchParams();
  if (query.owner) params.set("owner", query.owner);
  if (query.search) params.set("search", query.search);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<ClientListResponse>(`/clients${qs ? `?${qs}` : ""}`);
}

export function getClient(id: UUID): Promise<ClientDetail> {
  return request<ClientDetail>(`/clients/${id}`);
}

// --- tasks (S2-E3) ---------------------------------------------------------

export interface TaskInboxRow {
  id: UUID;
  owner_id: UUID | null;
  subject: string;
  status: string;
  category: string | null;
  due_date: ISODate | null;
  wake_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  completed_by: UUID | null;
  escalation_level: number;
}

export interface TaskListResponse {
  items: TaskInboxRow[];
  page: number;
  size: number;
  total: number;
}

export interface ListTasksQuery {
  owner?: "me" | UUID;
  status?: string;
  category?: string;
  include_snoozed?: boolean;
  page?: number;
  size?: number;
}

export interface PatchTaskBody {
  status?: string;
  wake_at?: ISODateTime | null;
}

export interface ReassignTaskBody {
  new_owner_id: UUID;
}

export function listTasks(query: ListTasksQuery = {}): Promise<TaskListResponse> {
  const params = new URLSearchParams();
  if (query.owner) params.set("owner", query.owner);
  if (query.status) params.set("status", query.status);
  if (query.category) params.set("category", query.category);
  if (query.include_snoozed) params.set("include_snoozed", "true");
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<TaskListResponse>(`/tasks${qs ? `?${qs}` : ""}`);
}

export function patchTask(id: UUID, body: PatchTaskBody): Promise<TaskInboxRow> {
  return request<TaskInboxRow>(`/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function reassignTask(id: UUID, body: ReassignTaskBody): Promise<TaskInboxRow> {
  return request<TaskInboxRow>(`/tasks/${id}/reassign`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- notifications (S2-E3) -------------------------------------------------

export interface NotificationRow {
  id: UUID;
  category: string;
  channel: string;
  subject: string;
  body_md: string;
  related_entity: string | null;
  related_entity_id: string | null;
  status: string;
  created_at: ISODateTime;
  read_at: ISODateTime | null;
}

export interface InboxResponse {
  items: NotificationRow[];
  unread_count: number;
}

export interface NotificationSettingRow {
  category: string;
  channel: string;
  enabled: boolean;
}

export interface NotificationSettingsResponse {
  items: NotificationSettingRow[];
  categories: string[];
  channels: string[];
}

export function listInboxNotifications(limit = 50): Promise<InboxResponse> {
  return request<InboxResponse>(`/notifications/inbox?limit=${limit}`);
}

export function markNotificationRead(id: UUID): Promise<NotificationRow> {
  return request<NotificationRow>(`/notifications/${id}/read`, { method: "POST" });
}

export function getNotificationSettings(): Promise<NotificationSettingsResponse> {
  return request<NotificationSettingsResponse>(`/notifications/settings`);
}

export function patchNotificationSetting(
  body: NotificationSettingRow,
): Promise<NotificationSettingRow> {
  return request<NotificationSettingRow>(`/notifications/settings`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- rate cards + policy (S2-E4) ------------------------------------------

/**
 * Money is serialized as string over the wire so we never lose Decimal
 * precision in the browser (JS `number` cannot represent every 2dp Decimal).
 * The publish form parses/validates and the display code renders as-is.
 */
export type MoneyString = string;
export type FloorString = string; // 4dp Decimal (e.g. "0.3500")

export type RateCardLocation = "US" | "India";

export interface RateCardRow {
  id: UUID | null;
  role: string;
  seniority: string;
  location: RateCardLocation;
  cost_low: MoneyString;
  cost_base: MoneyString;
  cost_high: MoneyString;
}

export interface RateCardVersionSummary {
  id: UUID;
  effective_from: ISODate;
  published_at: ISODateTime;
  published_by: UUID | null;
  notes: string | null;
  row_count: number;
  is_active: boolean;
}

export interface RateCardVersionDetail extends RateCardVersionSummary {
  rows: RateCardRow[];
}

export interface RateCardListResponse {
  items: RateCardVersionSummary[];
  active_id: UUID | null;
}

export interface PublishRateCardBody {
  effective_from: ISODate;
  notes?: string | null;
  rows: Omit<RateCardRow, "id">[];
  confirm?: boolean;
}

export interface PublishRateCardResponse {
  version: RateCardVersionDetail;
  warnings: string[];
}

export function listRateCards(): Promise<RateCardListResponse> {
  return request<RateCardListResponse>(`/admin/rate-cards`);
}

export function getRateCard(id: UUID): Promise<RateCardVersionDetail> {
  return request<RateCardVersionDetail>(`/admin/rate-cards/${id}`);
}

export function publishRateCard(
  body: PublishRateCardBody,
): Promise<PublishRateCardResponse> {
  return request<PublishRateCardResponse>(`/admin/rate-cards`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type FxConvention = "fixed_at_sow_date" | "monthly_average";

export interface PolicyVersionRow {
  id: UUID;
  effective_from: ISODate;
  us_floor: FloorString;
  india_floor: FloorString;
  fx_convention: FxConvention;
  published_at: ISODateTime;
  published_by: UUID | null;
  notes: string | null;
  is_active: boolean;
}

export interface ActivePolicy {
  id: UUID | null;
  effective_from: ISODate | null;
  us_floor: FloorString;
  india_floor: FloorString;
  fx_convention: FxConvention;
  is_default: boolean;
}

export interface PolicyListResponse {
  items: PolicyVersionRow[];
  active: ActivePolicy;
  allowed_fx_conventions: FxConvention[];
}

export interface PublishPolicyBody {
  effective_from: ISODate;
  us_floor: FloorString;
  india_floor: FloorString;
  fx_convention: FxConvention;
  notes?: string | null;
}

export function listPolicies(): Promise<PolicyListResponse> {
  return request<PolicyListResponse>(`/admin/policy`);
}

export function publishPolicy(body: PublishPolicyBody): Promise<PolicyVersionRow> {
  return request<PolicyVersionRow>(`/admin/policy`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- GM sandbox (S2-E4, M1 sign-off screen) --------------------------------

/** The six engagement templates in build-guide §7. */
export type EngagementType =
  | "staff_aug"
  | "single_resource"
  | "fixed_price"
  | "assessment"
  | "tm"
  | "managed_service";

/**
 * Money strings — never plain numbers. The API sends/receives Decimals as
 * strings so the browser can never mangle them via float arithmetic
 * (CLAUDE.md rule 2, blueprint §2).
 */
export type DecimalStr = string;

export interface SandboxRequest {
  engagement_type: EngagementType;
  inputs: Record<string, unknown>;
  policy_version_id?: UUID | null;
  rate_card_version_id?: UUID | null;
}

export interface SandboxPolicy {
  us_floor: DecimalStr;
  india_floor: DecimalStr;
  us_pass: boolean;
  india_pass: boolean;
  requires_ceo: boolean;
  failing: string[];
  source: "active" | "defaults";
}

export interface SandboxResponse {
  engagement_type: EngagementType;
  revenue_us: DecimalStr;
  cost_us: DecimalStr;
  gm_us: DecimalStr | null;
  revenue_india: DecimalStr;
  cost_india: DecimalStr;
  gm_india: DecimalStr | null;
  gm_blended: DecimalStr | null;
  geography: "US" | "India" | "Mixed";
  complete: boolean;
  missing: string[];
  policy: SandboxPolicy;
  min_price_us: DecimalStr | null;
  min_price_india: DecimalStr | null;
  policy_version_id: UUID | null;
  rate_card_version_id: UUID | null;
  computed_at: ISODateTime;
}

export interface SandboxField {
  name: string;
  label: string;
  kind: string;
  required: boolean;
  help: string;
}

export interface SandboxSchema {
  engagement_type: EngagementType;
  fields: SandboxField[];
}

export function computeGm(body: SandboxRequest): Promise<SandboxResponse> {
  return request<SandboxResponse>(`/gm/sandbox`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getGmSchema(type: EngagementType): Promise<SandboxSchema> {
  return request<SandboxSchema>(`/gm/sandbox/schema/${type}`);
}

/**
 * Ask the API for the .xlsx of a sandbox scenario. Returns the raw Blob so
 * the page can drive a download without re-encoding the bytes.
 */
export async function exportGmXlsx(body: SandboxRequest): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/gm/sandbox/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    const errBody = text ? safeJson(text) : null;
    const message =
      errBody && typeof errBody === "object" && "detail" in errBody
        ? String((errBody as { detail: unknown }).detail)
        : `API error ${res.status}`;
    throw new ApiError(res.status, errBody, message);
  }
  return await res.blob();
}
