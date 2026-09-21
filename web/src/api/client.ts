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
  // S3 E6 / S4 E7: compact GM model + latest approval package summaries.
  gm_model?: Record<string, unknown> | null;
  latest_package?: {
    id: UUID;
    status:
      | "pending_delivery_hr"
      | "pending_finance_legal"
      | "pending_ceo_exception"
      | "ready_to_sign"
      | "released"
      | "voided"
      | "rejected";
    package_hash: string;
    submitted_at: ISODateTime | null;
    submitted_by: UUID;
  } | null;
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
    throw new ApiError(res.status, body, errorMessage(body, res.status));
  }
  return body as T;
}

/**
 * Pull a human message out of an error body.
 *
 * FastAPI's `detail` is a string for a plain HTTPException but an object for
 * a structured one — and the API's global handlers return
 * `{detail: {message, correlation_id, error_type}}`. `String(detail)` on
 * those renders the literal text "[object Object]", so the object shapes are
 * unwrapped here.
 *
 * The final fallback, `API error <status>`, only appears when the response
 * carried no JSON at all — a proxy error page, or an unhandled exception
 * before the handlers were in place. That is the message this whole change
 * set exists to stop people seeing.
 */
export function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object") {
      const d = detail as Record<string, unknown>;
      const message = d.message ?? d.msg;
      if (typeof message === "string" && message.trim()) {
        return typeof d.correlation_id === "string"
          ? `${message} (ref ${d.correlation_id.slice(0, 8)})`
          : message;
      }
    }
  }
  if (typeof body === "string" && body.trim()) return body;
  return `API error ${status}`;
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

export interface OwnerRef {
  id: UUID;
  name: string;
}

export interface ClientListRow {
  id: UUID;
  name: string;
  hubspot_company_id: string | null;
  coverage_state: string;
  opportunity_count: number;
  owner_ids: UUID[];
  /** S13a §2.2: owner_id resolved to a display name for the Pipeline UI. */
  owners: OwnerRef[];
  /** S13a §2.3: distinct opportunity sources (hubspot, sow_upload, bulk_import, manual). */
  sources: string[];
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

// --- Opportunity Adviser (S3 E11) -----------------------------------------

/**
 * The intake form the Adviser accepts. `client_name` + `problem` are the
 * two required fields; everything else is optional but sharpens the draft.
 * The API records the payload verbatim so a reviewer sees what the
 * Marketing/Sales/Presales user actually typed.
 */
export interface AdviserIntakeBody {
  client_name: string;
  problem: string;
  website?: string | null;
  functions?: string[] | null;
  users_count?: number | null;
  systems?: string[] | null;
  geography?: string | null;
  timeline?: string | null;
  budget?: string | null;
}

/** One priced team member. Decimals serialize as strings so we never lose
 * precision on the wire (blueprint §2). */
export interface AdviserTeamMember {
  role: string;
  seniority: string;
  location: "US" | "India";
  hours: DecimalStr;
  allocation_pct: DecimalStr;
  cost_low: DecimalStr;
  cost_base: DecimalStr;
  cost_high: DecimalStr;
  is_sentinel: boolean;
}

export interface AdviserDeliveryOption {
  key: "us_only" | "india_only" | "mixed";
  label: string;
  cost_low: DecimalStr;
  cost_base: DecimalStr;
  cost_high: DecimalStr;
  min_price: DecimalStr;
  floor_applied: DecimalStr;
  eligible: boolean;
}

export interface AdviserEstimate {
  kind: "estimate";
  id: UUID;
  submitted_at: ISODateTime;
  submitted_by: UUID | null;
  label: string;
  scope: string;
  confidence: "low" | "medium" | "high" | string;
  reasons: string[];
  team: AdviserTeamMember[];
  cost_low: DecimalStr;
  cost_base: DecimalStr;
  cost_high: DecimalStr;
  options: AdviserDeliveryOption[];
  sources: Array<Record<string, unknown>>;
  model: string;
  prompt_version: string;
  inputs: Record<string, unknown>;
  rate_card_version_id: UUID | null;
  has_sentinel_costs: boolean;
  reviewer_id: UUID | null;
  reviewed_at: ISODateTime | null;
  /** Public research outcome: "ok" | "unavailable" | null for pre-S7-wave2 rows. */
  research_status?: string | null;
}

export interface AdviserQuestions {
  kind: "questions";
  questions: string[];
  note: string;
  label: string;
  model: string;
  prompt_version: string;
  sources: Array<Record<string, unknown>>;
  research_status?: string | null;
}

export type AdviserResult = AdviserEstimate | AdviserQuestions;

export interface AdviserListResponse {
  items: AdviserEstimate[];
  page: number;
  size: number;
  total: number;
}

export interface ListAdviserQuery {
  owner?: "me" | "all" | UUID;
  page?: number;
  size?: number;
}

export function createAdviserEstimate(
  body: AdviserIntakeBody,
): Promise<AdviserResult> {
  return request<AdviserResult>(`/adviser/estimates`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getAdviserEstimate(id: UUID): Promise<AdviserEstimate> {
  return request<AdviserEstimate>(`/adviser/estimates/${id}`);
}

export function listAdviserEstimates(
  query: ListAdviserQuery = {},
): Promise<AdviserListResponse> {
  const params = new URLSearchParams();
  if (query.owner) params.set("owner", query.owner);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<AdviserListResponse>(`/adviser/estimates${qs ? `?${qs}` : ""}`);
}

// --- SOW upload + extract + confirm (S3-E5) --------------------------------

/**
 * The 14 fields the Bedrock extract produces. Kept in lock-step with
 * `api/app/integrations/bedrock_sow_extract.EXTRACTED_FIELDS`.
 */
export type SowFieldName =
  | "scope_summary"
  | "price"
  | "currency"
  | "billing_basis"
  | "term_start"
  | "term_end"
  | "notice_date"
  | "deliverables"
  | "milestones"
  | "acceptance_criteria"
  | "assumptions"
  | "exclusions"
  | "signatories"
  | "engagement_type_suggested";

export const SOW_FIELDS: SowFieldName[] = [
  "scope_summary",
  "price",
  "currency",
  "billing_basis",
  "term_start",
  "term_end",
  "notice_date",
  "deliverables",
  "milestones",
  "acceptance_criteria",
  "assumptions",
  "exclusions",
  "signatories",
  "engagement_type_suggested",
];

export type SowFieldStatus = "unconfirmed" | "confirmed" | "disputed";
export type SowExtractStatus =
  | "pending"
  | "complete"
  | "failed"
  | "manual_required";

export interface SowExtractedField {
  value: unknown;
  page_ref: number;
  status: SowFieldStatus;
}

export type SowExtractedFields = Partial<Record<SowFieldName, SowExtractedField>>;

export interface SowVersion {
  id: UUID;
  sow_id: UUID;
  opportunity_id: UUID;
  uploaded_by: UUID | null;
  uploaded_at: ISODateTime;
  file_s3_key: string;
  file_hash: string;
  extracted_fields: SowExtractedFields | null;
  extract_status: SowExtractStatus;
  extract_model: string | null;
  extract_prompt_version: string | null;
  confirmed_by: UUID | null;
  confirmed_at: ISODateTime | null;
  engagement_type_suggested: string | null;
  engagement_type_confirmed: string | null;
  download_url: string | null;
}

export interface SowUploadUrlRequest {
  filename: string;
  content_type: string;
}

export interface SowUploadUrlResponse {
  url: string;
  s3_key: string;
  method: "PUT";
  expires_in: number;
  required_headers?: Record<string, string> | null;
  max_bytes: number;
}

export interface CreateSowVersionBody {
  file_s3_key: string;
  file_hash: string;
  file_size?: number;
}

export function getSowUploadUrl(
  opportunityId: UUID,
  body: SowUploadUrlRequest,
): Promise<SowUploadUrlResponse> {
  return request<SowUploadUrlResponse>(`/sow/${opportunityId}/upload-url`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createSowVersion(
  opportunityId: UUID,
  body: CreateSowVersionBody,
): Promise<SowVersion> {
  return request<SowVersion>(`/sow/${opportunityId}/versions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getCurrentSowVersion(
  opportunityId: UUID,
): Promise<SowVersion | null> {
  return request<SowVersion | null>(`/sow/opportunity/${opportunityId}/current`);
}

export function getSowVersion(sowVersionId: UUID): Promise<SowVersion> {
  return request<SowVersion>(`/sow/versions/${sowVersionId}`);
}

export function confirmSowField(
  sowVersionId: UUID,
  fieldName: SowFieldName,
  value: unknown,
): Promise<SowVersion> {
  return request<SowVersion>(
    `/sow/versions/${sowVersionId}/fields/${fieldName}`,
    {
      method: "PATCH",
      body: JSON.stringify({ value }),
    },
  );
}

export function submitSowVersion(sowVersionId: UUID): Promise<SowVersion> {
  return request<SowVersion>(`/sow/versions/${sowVersionId}/submit`, {
    method: "POST",
  });
}

// --- Signatories picker ---------------------------------------------------

/**
 * One authorised internal signatory — a user in a governance group whose
 * name shows up in the "Internal (People & access)" side of the picker.
 * Mirrors :class:`app.routers.signatories.InternalSignatoryRow`.
 */
export interface InternalSignatoryRow {
  id: UUID;
  name: string;
  email: string;
  groups: string[];
}

/**
 * One client-side signatory. Mirrors
 * :class:`app.routers.signatories.ClientContactRow`. Idempotent on
 * ``(client_id, email)`` — the POST route returns the existing row rather
 * than raising 409 when the email is already on file.
 */
export interface ClientContactRow {
  id: UUID;
  client_id: UUID;
  name: string;
  email: string;
  title: string | null;
}

export interface ClientContactCreate {
  name: string;
  email: string;
  title?: string | null;
}

/**
 * The normalized shape one picked signatory takes on the SOW's
 * ``extracted_fields.signatories`` list. ``source`` says which panel
 * the row came from; ``user_id`` / ``contact_id`` point back at the
 * governance record so the audit trail names a real person, not a
 * free-text string.
 */
export interface PickedSignatory {
  source: "internal" | "client";
  user_id?: UUID | null;
  contact_id?: UUID | null;
  name: string;
  email: string;
  title?: string | null;
  role?: string | null;
}

export function listInternalSignatories(): Promise<InternalSignatoryRow[]> {
  return request<InternalSignatoryRow[]>(`/signatories/internal`);
}

export function listClientContacts(
  clientId: UUID,
): Promise<ClientContactRow[]> {
  return request<ClientContactRow[]>(`/clients/${clientId}/contacts`);
}

export function createClientContact(
  clientId: UUID,
  body: ClientContactCreate,
): Promise<ClientContactRow> {
  return request<ClientContactRow>(`/clients/${clientId}/contacts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- SOW upload pipeline (S10-01) ------------------------------------------

/**
 * The status alphabet the router surfaces. Mirrors
 * ``api/app/services/sow_upload_job_service.py``. ``duplicate`` is not
 * a job status; it lives on :attr:`UploadSowResponse.duplicate`
 * because the router short-circuits before touching a job.
 */
export type SowUploadJobStatus =
  | "queued"
  | "extracting"
  | "classifying"
  | "matching_client"
  | "deriving_gm"
  | "needs_pick"
  | "done"
  | "failed";

export type SowUploadResolution =
  | "matched"
  | "needs_pick"
  | "created"
  | null;

export interface SowUploadCandidate {
  client_id: UUID;
  name: string;
  score?: number;
  confidence?: string;
  reason?: string;
}

export interface SowUploadNeedsPickCreateNew {
  legal_name: string | null;
  domain: string | null;
  address_lines: string[] | null;
}

export interface SowUploadNeedsPickPayload {
  signals?: {
    legal_name?: string | null;
    domain?: string | null;
    aliases?: string[];
    address_lines?: string[];
  };
  candidates?: SowUploadCandidate[];
  create_new?: SowUploadNeedsPickCreateNew;
  extract?: Record<string, unknown> | null;
}

export interface SowUploadJobResponse {
  id: UUID;
  status: SowUploadJobStatus;
  resolution: SowUploadResolution;
  error: string | null;
  opportunity_id: UUID | null;
  sow_version_id: UUID | null;
  file_hash: string;
  s3_key: string | null;
  needs_pick: SowUploadNeedsPickPayload | null;
}

export interface UploadSowResponse {
  job_id: UUID;
  status: SowUploadJobStatus;
  resolution: SowUploadResolution;
  opportunity_id: UUID | null;
  sow_version_id: UUID | null;
  duplicate: boolean;
  needs_pick: SowUploadNeedsPickPayload | null;
  /**
   * Other in-progress SOWs for the same client.
   *
   * Parallel contracts are normal, so this is never a rejection — it is the
   * information the screen needs to ask whether this is a new contract or
   * the one you already started. Silently creating a second opportunity for
   * the same engagement is how duplicates appear in the pipeline.
   */
  other_open_sows?: {
    opportunity_id: UUID;
    sow_version_id: UUID;
    version_no: number;
    title: string | null;
    uploaded_at: string | null;
    governance_status: string | null;
    is_signed: boolean;
  }[];
}

export interface SowUploadRejected422 {
  detected_type: string;
  message: string;
}

/**
 * Multipart upload of a SOW file. Returns 200 on success (including
 * ``duplicate=true`` when the same bytes were seen before), or throws
 * an :class:`ApiError` with status 422 whose ``detail`` conforms to
 * :interface:`SowUploadRejected422` when the doc-type gate rejects
 * the file (résumé, invoice, …).
 */
export async function uploadSow(input: {
  file: File;
  clientHint?: string;
}): Promise<UploadSowResponse> {
  const form = new FormData();
  form.append("file", input.file);
  if (input.clientHint) form.append("client_hint", input.clientHint);
  const res = await fetch(`${BASE_URL}/sows/upload`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, body, errorMessage(body, res.status));
  }
  return body as UploadSowResponse;
}

/** Poll one job. Cheap read — safe to call every 1500ms with an AbortController. */
export function getSowJob(jobId: UUID): Promise<SowUploadJobResponse> {
  return request<SowUploadJobResponse>(`/sows/jobs/${jobId}`);
}

/**
 * Resume a paused job with the reviewer's picker choice.
 *
 * Exactly one of ``client_id`` or ``create_new`` must be present. The
 * API returns 422 if both or neither are supplied; the client-side
 * union mirrors that invariant.
 */
export type SowJobPickBody =
  | { client_id: UUID; create_new?: never }
  | {
      client_id?: never;
      create_new: {
        legal_name: string;
        domain?: string | null;
        address_lines?: string[] | null;
      };
    };

export function pickSowJobClient(
  jobId: UUID,
  body: SowJobPickBody,
): Promise<SowUploadJobResponse> {
  return request<SowUploadJobResponse>(`/sows/jobs/${jobId}/pick`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- SOW confirmation package (S9 Wave 1/2) --------------------------------

/**
 * Per-field provenance envelope (CLAUDE.md rule 10). Every value the
 * confirmation page renders carries one so the human can see what the
 * system decided and why. `manual` badges must be highlighted in the UI
 * per the sow-first spec.
 */
export type SowProvenance =
  | "extracted"
  | "looked_up"
  | "calculated"
  | "defaulted"
  | "manual";

export type SowFieldConfirmStatus =
  | "unconfirmed"
  | "confirmed"
  | "disputed";

export interface SowProvenanceEntry {
  value: unknown;
  provenance: SowProvenance;
  page_ref?: number | null;
  source_id?: string | null;
  confidence?: number | null;
  warning?: string | null;
  status?: SowFieldConfirmStatus;
}

/**
 * Top-2 engagement type candidates from the classifier. When
 * `auto_confirm` is true the UI shows a chip with a small "change"
 * affordance; otherwise it renders a two-candidate chooser.
 */
export interface SowConfirmationEngagementCandidate {
  type: EngagementType;
  confidence: number;
}

export interface SowConfirmationEngagement {
  primary: SowConfirmationEngagementCandidate;
  secondary: SowConfirmationEngagementCandidate | null;
  rule_matched: string | null;
  auto_confirm: boolean;
}

export interface SowConfirmationStaffingLine {
  role: string;
  seniority: string;
  location: "US" | "India" | string;
  allocation_pct: DecimalStr;
  hours_billable: DecimalStr;
  hourly_bill_rate: DecimalStr;
  hourly_cost?: DecimalStr | null;
  provenance: SowProvenance;
  source_id: string | null;
  warning: string | null;
  start_date: ISODate | null;
  end_date: ISODate | null;
}

export interface SowConfirmationStaffing {
  lines: SowConfirmationStaffingLine[];
  notes: string[];
  warnings: string[];
  sources: string[];
}

export interface SowConfirmationGmModel {
  id: UUID;
  engagement_type: EngagementType | string;
  revenue_us: DecimalStr | null;
  revenue_india: DecimalStr | null;
  resource_line_count: number;
}

/**
 * The floor block mirrors the sandbox / delivery-model shape but adds
 * pre-computed component values so the browser never has to do math
 * (spec §21, CLAUDE.md rule 2).
 */
export interface SowConfirmationFloors {
  revenue_total?: DecimalStr | null;
  us_floor?: DecimalStr;
  india_floor?: DecimalStr;
  us_pass: boolean;
  india_pass: boolean;
  requires_ceo: boolean;
  failing: string[];
  gm_us?: DecimalStr | null;
  gm_india?: DecimalStr | null;
  gm_blended?: DecimalStr | null;
  reason?: string;
  error?: string;
}

export type SowConfirmationApproverFunction =
  | "delivery"
  | "hr"
  | "finance"
  | "legal";

export interface SowConfirmationApprover {
  user_id: UUID | null;
  source: string;
  business_unit: string | null;
}

export interface SowConfirmationProjectedTask {
  kind: string;
  due: ISODate | string | null;
  owner_role: string;
}

export interface SowConfirmationNeedsYou {
  field: string;
  reason: string;
}

export interface SowConfirmationCeoGate {
  will_trigger: boolean;
  brief?: Record<string, unknown> | null;
}

export interface SowConfirmationSowVersion {
  id: UUID;
  extracted_fields: Record<string, SowProvenanceEntry | unknown> | null;
  extract_status: SowExtractStatus;
  engagement_type_suggested: string | null;
}

/**
 * Client, title and file for the "Source & type" section.
 *
 * These are records, not extracted fields: the client is resolved master
 * data and the file is a stored object. The UI previously looked them up in
 * `extracted_fields` under keys the extractor never emits, so all three rows
 * rendered "unknown".
 */
export interface SowConfirmationSource {
  client_id: UUID | null;
  client_name: string | null;
  /** What the extractor read from the parties clause, before resolution. */
  client_legal_name_extracted: string | null;
  legal_entity_name: string | null;
  sow_title: string | null;
  file_s3_key: string | null;
  file_name: string | null;
  /** "page" for a PDF, "block" for a Word file (docs/adr/0002). */
  ref_unit: string | null;
  document_kind: string | null;
}

export interface SowConfirmationPayload {
  source: SowConfirmationSource;
  sow_version: SowConfirmationSowVersion;
  engagement: SowConfirmationEngagement;
  staffing: SowConfirmationStaffing;
  gm_model: SowConfirmationGmModel | null;
  floors: SowConfirmationFloors;
  approvers: Record<SowConfirmationApproverFunction, SowConfirmationApprover>;
  projected_tasks: SowConfirmationProjectedTask[];
  needs_you: SowConfirmationNeedsYou[];
  ceo_gate: SowConfirmationCeoGate;
}

/**
 * Fetch the derived confirmation payload for one opportunity. Idempotent —
 * the server reuses the auto-GM row for the SOW version if one exists.
 */
export function getSowConfirmation(
  opportunityId: UUID,
): Promise<SowConfirmationPayload> {
  return request<SowConfirmationPayload>(
    `/sow/${opportunityId}/confirmation`,
  );
}

/**
 * Commit the confirmation — transitions the opportunity to
 * ``SOWDraft.confirmed`` and returns the frozen payload. Idempotent.
 */
export function submitSowConfirmation(
  opportunityId: UUID,
): Promise<SowConfirmationPayload> {
  return request<SowConfirmationPayload>(
    `/sow/${opportunityId}/confirmation/submit`,
    { method: "POST" },
  );
}

// --- Delivery Model Builder (S3 E6) ---------------------------------------

/** Same location alphabet as the rate card + GM sandbox. */
export type DeliveryLocation = "US" | "India";

/**
 * Cost line categories mirror the pure library — the Builder never sends
 * anything else so the API's 422 path is only reachable when the browser is
 * out of sync with the server (e.g. an old cached bundle).
 */
export type DeliveryCostCategory =
  | "tools"
  | "travel"
  | "subcontractor"
  | "other";

/**
 * S9 — provenance kind for every derived field on the SOW-first pipeline
 * (docs/directives/sow-first.md, CLAUDE.md rule 10). `manual` means a
 * human overrode the derivation; every other kind names where the value
 * came from.
 */
export type ProvenanceKind =
  | "extracted"
  | "looked_up"
  | "calculated"
  | "defaulted"
  | "manual";

/**
 * S9 — provenance metadata attached to a derived resource line. Optional
 * so existing callers keep working; new SOW-confirmation output attaches
 * this to every row.
 */
export interface DeliveryLineProvenance {
  provenance: ProvenanceKind;
  /** Human-readable label for the source (e.g. "SOW p.4 §Resources"). */
  source_label?: string | null;
  /** Foreign key to the source record (e.g. past-SOW id, capability
   *  catalog row) so the UI can render a link chip. */
  source_id?: string | null;
  /** Page ref for extracted values. */
  page_ref?: number | null;
  /** Extractor confidence in [0, 1]. */
  confidence?: number | null;
  /** Non-blocking amber warning (e.g. "estimated from past SOW"). */
  warning?: string | null;
  /** Where the bill rate came from: client card / SOW override / fallback. */
  bill_rate_source?: "client_card" | "sow_override" | "fallback" | null;
}

/**
 * A row in the resource grid. All money / percent fields are strings so the
 * browser never coerces a Decimal to a float (blueprint §2, CLAUDE.md rule 2).
 * ``person_name = null`` is the story's "to hire" flag — HR lead-time
 * warnings key off this.
 */
export interface DeliveryResourceLineInput {
  role: string;
  seniority: string;
  location: DeliveryLocation;
  person_name: string | null;
  allocation_pct: DecimalStr;
  start_date: ISODate;
  end_date: ISODate;
  hours_billable: DecimalStr;
  hourly_bill_rate: DecimalStr;
  hourly_cost: DecimalStr | null;
  validated_by: UUID | null;
  /** S7 wave 2 — WBS phase name join key at save time. Null keeps the
   * row in the Builder's "Ungrouped" bucket. */
  phase_name?: string | null;
  /** S9 — SOW-first provenance stamp (may be absent on legacy rows). */
  provenance_meta?: DeliveryLineProvenance | null;
}

export interface DeliveryCostLineInput {
  category: DeliveryCostCategory;
  amount: DecimalStr;
  location: DeliveryLocation;
  note?: string | null;
  phase_name?: string | null;
  provenance_meta?: DeliveryLineProvenance | null;
}

export interface DeliveryResourceLineRow extends DeliveryResourceLineInput {
  id: UUID;
  phase_id?: UUID | null;
}

export interface DeliveryCostLineRow extends DeliveryCostLineInput {
  id: UUID;
  note: string | null;
  phase_id?: UUID | null;
}

/** S7 wave 2 — one WBS phase in the save payload. */
export interface DeliveryPhaseInput {
  name: string;
  order: number;
  sow_deliverable_ref?: string | null;
  description?: string | null;
}

/** S7 wave 2 — one WBS phase as returned by the API. */
export interface DeliveryPhaseRow {
  id: UUID;
  name: string;
  order: number;
  sow_deliverable_ref: string | null;
  description: string | null;
}

/** S7 wave 2 — per-phase revenue + cost roll-up for the right-panel widget. */
export interface DeliveryPhaseSummary {
  phase_id: UUID | null;
  name: string;
  revenue: DecimalStr;
  cost?: DecimalStr;
}

/** Warning surfaced in the resource grid gutter. */
export interface DeliveryWarning {
  index: number;
  severity: "amber" | "red";
  code: "capacity_conflict" | "hr_lead_time";
  message: string;
}

/**
 * A computed slice — same shape as the sandbox's ``SandboxResponse`` policy
 * block so the panel can reuse the sandbox's rendering code.
 */
export interface DeliveryPolicyResult {
  us_floor: DecimalStr;
  india_floor: DecimalStr;
  us_pass: boolean;
  india_pass: boolean;
  requires_ceo: boolean;
  failing: string[];
}

export interface DeliveryComputedResult {
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
  min_price_us: DecimalStr | null;
  min_price_india: DecimalStr | null;
  policy: DeliveryPolicyResult;
  computed_at: ISODateTime;
}

export interface DeliveryPreviewResponse {
  engagement_type: EngagementType;
  computed: DeliveryComputedResult;
  warnings: {
    capacity: DeliveryWarning[];
    hr: DeliveryWarning[];
  };
}

export interface DeliveryGmModel {
  id: UUID;
  opportunity_id: UUID | null;
  sow_version_id: UUID | null;
  engagement_type: EngagementType;
  delivery_pattern: string | null;
  contingency_pct: DecimalStr | null;
  warranty_days: number | null;
  revenue_us: DecimalStr | null;
  revenue_india: DecimalStr | null;
  created_by: UUID | null;
  created_at: ISODateTime | null;
  /** S7 wave 2 — WBS phases + per-phase roll-up. */
  phases?: DeliveryPhaseRow[];
  phase_summary?: DeliveryPhaseSummary[];
  resource_lines: DeliveryResourceLineRow[];
  cost_lines: DeliveryCostLineRow[];
  completeness_issues: string[];
  computed?: DeliveryComputedResult;
  /** S9 — id of the newest SOW version, if the auto-staffing pipeline
   * has a fresher extraction than `sow_version_id`. When set and
   * distinct from `sow_version_id`, the workspace shows the "Rebuild
   * from SOW" affordance. */
  latest_sow_version_id?: UUID | null;
}

export interface DeliveryModelVersionSummary {
  id: UUID;
  engagement_type: EngagementType;
  delivery_pattern: string | null;
  revenue_us: DecimalStr | null;
  revenue_india: DecimalStr | null;
  resource_line_count: number;
  cost_line_count: number;
  created_by: UUID | null;
  created_at: ISODateTime | null;
}

export interface DeliveryLatestResponse {
  gm_model: DeliveryGmModel | null;
  warnings?: {
    capacity: DeliveryWarning[];
    hr: DeliveryWarning[];
  };
}

export interface DeliveryPreviewRequestInputs {
  resource_lines: DeliveryResourceLineInput[];
  cost_lines: DeliveryCostLineInput[];
  // Templates other than staff_aug carry these top-level fields; the API
  // forwards whichever keys are present, so the Builder just spreads them
  // in when the current template needs them.
  total_price?: DecimalStr;
  revenue_us?: DecimalStr;
  revenue_india?: DecimalStr;
  deliverable?: string;
  monthly_fee_us?: DecimalStr;
  monthly_fee_india?: DecimalStr;
  term_months?: DecimalStr;
  revenue_cap?: DecimalStr;
  replacement_obligation?: boolean;
  delivery_pattern?: string | null;
  contingency_pct?: DecimalStr | null;
  warranty_days?: number | null;
  sow_version_id?: UUID | null;
}

export interface DeliveryPreviewRequest {
  engagement_type: EngagementType;
  inputs: DeliveryPreviewRequestInputs;
}

export interface DeliverySaveRequest {
  engagement_type: EngagementType;
  sow_version_id?: UUID | null;
  delivery_pattern?: string | null;
  contingency_pct?: DecimalStr | null;
  warranty_days?: number | null;
  /** S7 wave 2 — WBS phases. Empty list keeps the model phase-less
   * (rows land in the "Ungrouped" bucket). */
  phases?: DeliveryPhaseInput[];
  resource_lines: DeliveryResourceLineInput[];
  cost_lines: DeliveryCostLineInput[];
  // Template scalars persisted implicitly via the snapshot revenue_us /
  // revenue_india columns; still passed here for compute.
  total_price?: DecimalStr;
  revenue_us?: DecimalStr;
  revenue_india?: DecimalStr;
  deliverable?: string;
  monthly_fee_us?: DecimalStr;
  monthly_fee_india?: DecimalStr;
  term_months?: DecimalStr;
  revenue_cap?: DecimalStr;
  replacement_obligation?: boolean;
}

export interface DeliverySaveResponse {
  gm_model: DeliveryGmModel;
  warnings?: {
    capacity: DeliveryWarning[];
    hr: DeliveryWarning[];
  };
}

export function previewDeliveryModel(
  body: DeliveryPreviewRequest,
): Promise<DeliveryPreviewResponse> {
  return request<DeliveryPreviewResponse>(`/delivery-model/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** One row parsed out of an uploaded staffing sheet. */
export interface StaffingSheetLine {
  role: string;
  seniority: string;
  location: string;
  allocation_pct: string;
  hours_billable: string;
  hourly_bill_rate: string;
  start_date?: string;
  end_date?: string;
}

export interface StaffingImportResponse {
  resource_lines: StaffingSheetLine[];
  row_count: number;
  source: string;
}

/** A single bad cell, so the UI can list every problem at once. */
export interface StaffingSheetRowError {
  row: number;
  field?: string;
  message: string;
}

/** A SOW started but not yet submitted for approval. */
export interface DraftSowRow {
  opportunity_id: UUID;
  sow_version_id: UUID | null;
  client_id: UUID | null;
  client_name: string | null;
  title: string | null;
  governance_status: string;
  uploaded_at: string | null;
  extract_status: string | null;
  has_gm: boolean;
  /** Where to pick this SOW up — the staffing gate, or the confirm screen. */
  resume_href: string;
}

/**
 * SOWs in progress.
 *
 * Nothing in the product listed these. The approvals board shows approval
 * packages, so a SOW that had not reached one was invisible in every lane,
 * and a refresh looked exactly like data loss.
 */
export function listDraftSows(mine = true): Promise<{ drafts: DraftSowRow[] }> {
  return request<{ drafts: DraftSowRow[] }>(`/sows/drafts?mine=${mine}`);
}

/** A resource as the API returns it — utilization is a percentage here. */
export interface SowResourceRow {
  role: string;
  seniority: string;
  location: string;
  person_name: string | null;
  utilization_pct: string;
  hours_billable: string;
  hourly_bill_rate: string;
  hourly_cost: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface SowResourcesState {
  opportunity_id: UUID;
  gm_model_id: UUID | null;
  engagement_type: string | null;
  is_signed: boolean;
  /** Always true — signature adds a cost to changing, not a prohibition. */
  editable: boolean;
  /** After signature, a change is dated and the approvers are told. */
  requires_notice_on_change: boolean;
  resources: SowResourceRow[];
  margin: {
    gm_model_id: UUID | null;
    gm_us?: string | null;
    gm_india?: string | null;
    gm_blended?: string | null;
    us_pass?: boolean;
    india_pass?: boolean;
    requires_ceo?: boolean;
  };
}

export interface SowResourceUpdateResult {
  gm_model_id: UUID;
  previous_gm_model_id: UUID | null;
  requires_notice: boolean;
  effective_from: string | null;
  notified: string[];
  margin_before: SowResourcesState["margin"];
  margin_after: SowResourcesState["margin"];
}

export function getSowStaffing(
  opportunityId: UUID,
): Promise<SowResourcesState> {
  return request<SowResourcesState>(`/sows/${opportunityId}/staffing`);
}

/**
 * The one staffing write path. Both the Staffing tab and the Confirm page's
 * Staffing section call this — there is no second store. Always writes a new
 * immutable GM version. After signature `effective_from` and `reason` are
 * required and the approvers are notified with both margins.
 */
export function putSowStaffing(
  opportunityId: UUID,
  body: {
    engagement_type: string;
    resource_lines: DeliveryResourceLineInput[];
    cost_lines: DeliveryCostLineInput[];
    total_price?: string;
    effective_from?: string;
    reason?: string;
  },
): Promise<SowResourceUpdateResult> {
  return request<SowResourceUpdateResult>(`/sows/${opportunityId}/staffing`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** @deprecated Use `getSowStaffing`. Kept for callers not yet migrated. */
export const getSowResources = getSowStaffing;
/** @deprecated Use `putSowStaffing`. Kept for callers not yet migrated. */
export const putSowResources = putSowStaffing;

/** One row in a SOW's version history. */
export interface SowVersionRow {
  id: UUID;
  version_no: number;
  uploaded_at: string | null;
  extract_status: string;
  execution_state: string;
  is_current: boolean;
  superseded_by: UUID | null;
  discarded_at: string | null;
  discard_reason: string | null;
  file_name: string | null;
  ever_submitted: boolean;
  /** Computed server-side so the delete/discard rule lives in one place. */
  can_delete: boolean;
  can_discard: boolean;
}

export interface SowVersionList {
  sow_id: UUID | null;
  versions: SowVersionRow[];
}

export function listSowVersions(opportunityId: UUID): Promise<SowVersionList> {
  return request<SowVersionList>(`/sows/${opportunityId}/versions`);
}

/**
 * Upload a corrected SOW as the next version.
 *
 * Attaches to the existing SOW — no new opportunity, no client picker. The
 * caller has said which SOW this revises, so none of that has to be inferred
 * from the document. The previous version is superseded, not edited.
 */
export async function createSowRevision(
  opportunityId: UUID,
  file: File,
): Promise<{ sow_version_id: UUID; version_no: number; supersedes: UUID | null }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/sows/${opportunityId}/versions`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, body, errorMessage(body, res.status));
  return body as { sow_version_id: UUID; version_no: number; supersedes: UUID | null };
}

/** Hard delete. Only valid before the version has been submitted. */
export function deleteSowVersion(
  sowVersionId: UUID,
  reason?: string,
): Promise<{ deleted: boolean }> {
  const q = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return request<{ deleted: boolean }>(`/sows/versions/${sowVersionId}${q}`, {
    method: "DELETE",
  });
}

/** Soft discard, for a version that has already been through approval. */
export function discardSowVersion(
  sowVersionId: UUID,
  reason: string,
): Promise<{ sow_version_id: UUID; discarded_at: string | null }> {
  return request(`/sows/versions/${sowVersionId}/discard`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** URL of the blank staffing sheet. Opened directly so the browser downloads it. */
export function staffingTemplateUrl(): string {
  return `${BASE_URL}/sows/staffing-template.xlsx`;
}

/**
 * Upload a filled staffing sheet.
 *
 * Parses and returns — nothing is saved. The rows land in the grid so the
 * reviewer sees the resulting gross margin before committing; a spreadsheet
 * should not quietly become an approved cost basis.
 */
export async function importStaffingSheet(
  opportunityId: UUID,
  file: File,
): Promise<StaffingImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/sows/${opportunityId}/staffing/import`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, body, errorMessage(body, res.status));
  }
  return body as StaffingImportResponse;
}

export function saveDeliveryModelVersion(
  opportunityId: UUID,
  body: DeliverySaveRequest,
): Promise<DeliverySaveResponse> {
  return request<DeliverySaveResponse>(
    `/delivery-model/${opportunityId}/versions`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function getLatestDeliveryModel(
  opportunityId: UUID,
): Promise<DeliveryLatestResponse> {
  return request<DeliveryLatestResponse>(`/delivery-model/${opportunityId}`);
}

export function listDeliveryModelVersions(
  opportunityId: UUID,
): Promise<{ items: DeliveryModelVersionSummary[] }> {
  return request<{ items: DeliveryModelVersionSummary[] }>(
    `/delivery-model/${opportunityId}/versions`,
  );
}

export async function exportDeliveryModelXlsx(gmModelId: UUID): Promise<Blob> {
  const res = await fetch(
    `${BASE_URL}/delivery-model/versions/${gmModelId}/xlsx`,
    {
      method: "GET",
      headers: { ...(await authHeaders()) },
    },
  );
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

// --- S7 wave 2: phase reorder + templates --------------------------------

export interface DeliveryTemplateSummary {
  id: UUID;
  name: string;
  engagement_type: EngagementType;
  created_by: UUID | null;
  created_at: ISODateTime | null;
  updated_at: ISODateTime | null;
  active: boolean;
  phase_count: number;
  resource_line_count: number;
  cost_line_count: number;
}

export function reorderDeliveryPhases(
  opportunityId: UUID,
  orderedPhaseIds: UUID[],
): Promise<{ phases: DeliveryPhaseRow[] }> {
  return request<{ phases: DeliveryPhaseRow[] }>(
    `/delivery-model/${opportunityId}/phases/reorder`,
    {
      method: "PATCH",
      body: JSON.stringify({ ordered_phase_ids: orderedPhaseIds }),
    },
  );
}

export function saveDeliveryTemplate(
  body: { gm_model_id: UUID; name: string },
): Promise<{ template: DeliveryTemplateSummary }> {
  return request<{ template: DeliveryTemplateSummary }>(
    `/delivery-model/templates`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function listDeliveryTemplates(
  engagementType?: EngagementType,
): Promise<{ items: DeliveryTemplateSummary[] }> {
  const q = engagementType ? `?engagement_type=${encodeURIComponent(engagementType)}` : "";
  return request<{ items: DeliveryTemplateSummary[] }>(
    `/delivery-model/templates${q}`,
  );
}

export function deleteDeliveryTemplate(templateId: UUID): Promise<void> {
  return request<void>(`/delivery-model/templates/${templateId}`, {
    method: "DELETE",
  });
}

export function seedDeliveryModelFromTemplate(
  opportunityId: UUID,
  templateId: UUID,
): Promise<{ gm_model: DeliveryGmModel }> {
  return request<{ gm_model: DeliveryGmModel }>(
    `/delivery-model/${opportunityId}/from-template/${templateId}`,
    { method: "POST" },
  );
}

// --- Legacy import (S6 user-added scope) ---------------------------------

/**
 * The batch envelope for a single bulk-upload session. Status transitions
 * `uploading` → `reviewing` → `approved`. `errors` is populated when an
 * Excel import fails validation so the UI can render a red-highlighted
 * error report.
 */
export interface LegacyBatch {
  id: UUID;
  uploaded_by: UUID;
  status: "uploading" | "reviewing" | "approved" | string;
  sow_count: number;
  resource_line_count: number;
  errors: Array<Record<string, unknown>> | null;
  approved_by: UUID | null;
}

export interface LegacyUploadUrlResponse {
  url: string;
  s3_key: string;
  method: "PUT";
  expires_in: number;
  required_headers: Record<string, string> | null;
}

export interface LegacySowAttachRow {
  s3_key: string;
  filename: string;
  sow_ref: string;
  client_name?: string | null;
}

export interface LegacyAttachSowsResponse {
  batch: LegacyBatch;
  versions: UUID[];
}

export interface LegacyExcelImportResponse {
  imported: number;
  sow_refs: string[];
  errors: Array<Record<string, unknown>>;
}

export interface LegacyProjectGm {
  sow_ref: string;
  revenue_us: DecimalStr;
  revenue_india: DecimalStr;
  cost_us: DecimalStr;
  cost_india: DecimalStr;
  gm_us: DecimalStr | null;
  gm_india: DecimalStr | null;
  below_floor: boolean;
  failing: string[];
  complete: boolean;
}

export interface LegacyReconciliationResponse {
  batch_id: UUID;
  status: string;
  matched: Array<{
    sow_id: UUID;
    sow_ref: string;
    filename: string | null;
    gm_model_id: UUID;
    line_count: number;
    gm_us: DecimalStr | null;
    gm_india: DecimalStr | null;
    below_floor: boolean;
    failing: string[];
    complete: boolean;
  }>;
  unmatched_sows: Array<{ sow_id: UUID; sow_ref: string; filename: string | null }>;
  orphaned_resource_lines: Array<{
    gm_model_id: UUID;
    engagement_type: string;
    line_count: number;
  }>;
  project_gm: LegacyProjectGm[];
  below_floor: string[];
}

export function getLegacyUploadUrl(body: {
  filename: string;
  content_type: string;
}): Promise<LegacyUploadUrlResponse> {
  return request<LegacyUploadUrlResponse>(`/legacy/upload-url`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createLegacyBatch(): Promise<LegacyBatch> {
  return request<LegacyBatch>(`/legacy/batches`, { method: "POST" });
}

export function attachLegacySows(
  batchId: UUID,
  files: LegacySowAttachRow[],
): Promise<LegacyAttachSowsResponse> {
  return request<LegacyAttachSowsResponse>(`/legacy/batches/${batchId}/sows`, {
    method: "POST",
    body: JSON.stringify({ files }),
  });
}

/**
 * Uploads the resource-line Excel to the batch. Returns 422 with a per-row
 * error report when validation fails (all-or-nothing per file).
 */
export async function importLegacyExcel(
  batchId: UUID,
  file: File,
): Promise<LegacyExcelImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/legacy/batches/${batchId}/excel`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
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
  return body as LegacyExcelImportResponse;
}

export function getLegacyReconciliation(
  batchId: UUID,
): Promise<LegacyReconciliationResponse> {
  return request<LegacyReconciliationResponse>(
    `/legacy/batches/${batchId}/reconciliation`,
  );
}

export function approveLegacyBatch(
  batchId: UUID,
): Promise<LegacyReconciliationResponse> {
  return request<LegacyReconciliationResponse>(
    `/legacy/batches/${batchId}/approve`,
    { method: "POST" },
  );
}

// --- CEO exception (S4 E7) -------------------------------------------------

/**
 * The CEO brief per the story. Every money field lives as a Decimal-string
 * (`DecimalStr`) so the browser never coerces to float (rule 2). Fields
 * marked nullable stay null until the numbers land or the human writes them.
 */
export interface CeoBriefClient {
  name: string;
  context: string;
}

export interface CeoBriefGmComponent {
  value: DecimalStr | null;
  floor: DecimalStr | null;
  passes: boolean;
}

export interface CeoBriefJson {
  client: CeoBriefClient;
  scope: string;
  team_summary: string;
  revenue: { us: DecimalStr | null; india: DecimalStr | null; blended: DecimalStr | null };
  cost: { us: DecimalStr | null; india: DecimalStr | null; blended: DecimalStr | null };
  gm: {
    us: CeoBriefGmComponent;
    india: CeoBriefGmComponent;
    blended: { value: DecimalStr | null };
  };
  price_uplift: { us: DecimalStr | null; india: DecimalStr | null };
  gross_profit_shortfall_usd: DecimalStr | null;
  alternatives: string[];
  finance_recommendation: string;
  delivery_recommendation: string;
  rationale: null;
  sources: Array<Record<string, unknown>>;
  model: string;
  prompt_version: string;
}

export type CeoDecision = "approve" | "reject" | "return_for_changes";

export interface CeoException {
  id: UUID;
  package_id: UUID;
  brief_json: CeoBriefJson;
  rationale_text: string | null;
  rationale_tidied_text: string | null;
  rationale_set_by: UUID | null;
  rationale_set_at: ISODateTime | null;
  conditions_text: string | null;
  valid_until: ISODate | null;
  decision: CeoDecision | null;
  decided_by: UUID | null;
  decided_at: ISODateTime | null;
  drafted_at: ISODateTime | null;
}

export interface CeoExceptionListResponse {
  items: CeoException[];
}

export interface CeoRationaleBody {
  rationale_text: string;
  tidy?: boolean;
}

export interface CeoDecisionBody {
  decision: CeoDecision;
  conditions_text?: string | null;
  valid_until?: ISODate | null;
}

export interface CeoDelegateBody {
  delegate_id: UUID;
  effective_from: ISODate;
  expiry: ISODate;
}

export interface CeoDelegateRow {
  id: UUID;
  delegate_id: UUID;
  effective_from: ISODate;
  expiry: ISODate;
  granted_by: UUID;
  granted_at: ISODateTime | null;
}

export function listCeoExceptions(
  status: "pending" | "all" = "pending",
): Promise<CeoExceptionListResponse> {
  return request<CeoExceptionListResponse>(
    `/ceo-exceptions?status=${status}`,
  );
}

export function getCeoException(id: UUID): Promise<CeoException> {
  return request<CeoException>(`/ceo-exceptions/${id}`);
}

export function patchCeoRationale(
  id: UUID,
  body: CeoRationaleBody,
): Promise<CeoException> {
  return request<CeoException>(`/ceo-exceptions/${id}/rationale`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function postCeoDecision(
  id: UUID,
  body: CeoDecisionBody,
): Promise<CeoException> {
  return request<CeoException>(`/ceo-exceptions/${id}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function grantCeoDelegate(
  body: CeoDelegateBody,
): Promise<CeoDelegateRow> {
  return request<CeoDelegateRow>(`/admin/ceo-delegates`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Approval packages (S4 E7) --------------------------------------------

export type ApprovalPackageStatus =
  | "pending_delivery_hr"
  | "pending_finance_legal"
  | "pending_ceo_exception"
  | "ready_to_sign"
  | "released"
  | "voided"
  | "rejected";

export type ApprovalFunction = "delivery" | "hr" | "finance" | "legal";
export type ApprovalDecision = "approve" | "reject" | "request_changes";

export interface ApprovalRow {
  id: UUID;
  package_id: UUID;
  function: ApprovalFunction;
  approver_id: UUID;
  decision: ApprovalDecision;
  reason: string | null;
  decided_at: ISODateTime | null;
}

export interface ApprovalPackageFloors {
  us_pass: boolean;
  india_pass: boolean;
  requires_ceo: boolean;
  failing: string[];
  error?: string;
}

export interface ApprovalPackage {
  id: UUID;
  opportunity_id: UUID;
  sow_version_id: UUID;
  gm_model_id: UUID;
  package_hash: string;
  status: ApprovalPackageStatus;
  submitted_by: UUID;
  submitted_at: ISODateTime | null;
  released_at: ISODateTime | null;
  voided_at: ISODateTime | null;
  voided_reason: string | null;
  policy_version_id: UUID | null;
  approvals: ApprovalRow[];
  floors?: ApprovalPackageFloors;
}

export interface ApprovalPackageListResponse {
  items: ApprovalPackage[];
  page: number;
  size: number;
  total: number;
}

export interface ApprovalPackageSummary {
  id: UUID;
  status: ApprovalPackageStatus;
  package_hash: string;
  submitted_at: ISODateTime | null;
  submitted_by: UUID;
}

export interface ListApprovalPackagesQuery {
  status?: ApprovalPackageStatus;
  opportunity_id?: UUID;
  page?: number;
  size?: number;
}

export function submitApprovalPackage(
  opportunityId: UUID,
): Promise<ApprovalPackage> {
  return request<ApprovalPackage>(`/approvals/packages/${opportunityId}`, {
    method: "POST",
  });
}

export function getApprovalPackage(packageId: UUID): Promise<ApprovalPackage> {
  return request<ApprovalPackage>(`/approvals/packages/${packageId}`);
}

export function decideApprovalPackage(
  packageId: UUID,
  fn: ApprovalFunction,
  body: { decision: ApprovalDecision; reason?: string | null },
): Promise<ApprovalPackage> {
  return request<ApprovalPackage>(
    `/approvals/packages/${packageId}/decisions/${fn}`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function voidApprovalPackage(
  packageId: UUID,
  reason: string,
): Promise<ApprovalPackage> {
  return request<ApprovalPackage>(`/approvals/packages/${packageId}/void`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function listApprovalPackages(
  query: ListApprovalPackagesQuery = {},
): Promise<ApprovalPackageListResponse> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.opportunity_id) params.set("opportunity_id", query.opportunity_id);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<ApprovalPackageListResponse>(
    `/approvals/packages${qs ? `?${qs}` : ""}`,
  );
}

// --- Renewals (S5 E9) ------------------------------------------------------

export type RenewalStatus = "open" | "closed" | "extended" | "churn";

export interface RenewalRow {
  id: UUID;
  opportunity_id: UUID;
  term_end: ISODate;
  trigger_date: ISODate;
  status: RenewalStatus;
  outcome_summary: string | null;
  replacement_sow_version_id: UUID | null;
  opened_at: ISODateTime | null;
  updated_at: ISODateTime | null;
  days_until_end: number;
  hubspot_deal_id: string | null;
  owner_id: UUID | null;
  client_id: UUID | null;
}

export interface RenewalListResponse {
  items: RenewalRow[];
  page: number;
  size: number;
  total: number;
}

export interface ListRenewalsQuery {
  status?: RenewalStatus;
  owner?: "me" | UUID;
  page?: number;
  size?: number;
}

export interface PatchRenewalBody {
  outcome_summary?: string | null;
  status?: "closed" | "extended";
  replacement_sow_version_id?: UUID | null;
}

export function listRenewals(
  query: ListRenewalsQuery = {},
): Promise<RenewalListResponse> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.owner) params.set("owner", query.owner);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<RenewalListResponse>(`/renewals${qs ? `?${qs}` : ""}`);
}

export function getRenewal(id: UUID): Promise<RenewalRow> {
  return request<RenewalRow>(`/renewals/${id}`);
}

export function patchRenewal(
  id: UUID,
  body: PatchRenewalBody,
): Promise<RenewalRow> {
  return request<RenewalRow>(`/renewals/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- Role dashboards (S5 E10) ----------------------------------------------

/**
 * Every dashboard response ships pre-computed by the server (blueprint §2,
 * CLAUDE.md rule 2). Money fields are Decimal strings — do not coerce to
 * ``number`` before rendering. The typed clients below match one-to-one
 * with :mod:`app.services.dashboards`.
 */
export interface CeoBelowFloorDeal {
  opportunity_id: UUID;
  hubspot_deal_id: string;
  governance_status: string;
  revenue: DecimalStr | null;
  gm_us: DecimalStr | null;
  gm_india: DecimalStr | null;
}

export interface CeoExceptionPending {
  id: UUID;
  package_id: UUID;
  drafted_at: ISODateTime | null;
  has_rationale: boolean;
}

export interface CeoAgedBlocker {
  task_id: UUID;
  subject: string;
  due_date: ISODate | null;
  escalation_level: number;
  category: string | null;
}

export interface CeoDashboard {
  pipeline_value: DecimalStr;
  approved_vs_forecast_gp: {
    approved_gp: DecimalStr;
    forecast_gp: DecimalStr;
  };
  below_floor_deals: CeoBelowFloorDeal[];
  ceo_exceptions_pending: CeoExceptionPending[];
  revenue_expiring_in_90_days: Array<Record<string, unknown>>;
  aged_blockers_by_owner: Record<string, CeoAgedBlocker[]>;
  notes?: Record<string, string>;
}

export interface FinanceGmBySowRow {
  opportunity_id: UUID;
  hubspot_deal_id: string;
  gm_model_id: UUID;
  engagement_type: string;
  revenue: DecimalStr | null;
  cost: DecimalStr | null;
  gm_us: DecimalStr | null;
  gm_india: DecimalStr | null;
  gm_blended: DecimalStr | null;
  complete: boolean;
  approved: boolean;
}

export interface FinanceGeographyTotals {
  revenue: DecimalStr | null;
  cost: DecimalStr | null;
  gm: DecimalStr | null;
}

export interface FinanceMissingCostRow {
  opportunity_id: UUID;
  hubspot_deal_id: string;
  gm_model_id: UUID;
}

export interface FinanceExposureRow {
  ceo_exception_id: UUID;
  package_id: UUID;
  gross_profit_shortfall_usd: DecimalStr | null;
}

export interface FinanceDashboard {
  gm_by_sow: FinanceGmBySowRow[];
  gm_by_geography: {
    US: FinanceGeographyTotals;
    India: FinanceGeographyTotals;
  };
  approved_vs_forecast_vs_actual: {
    approved_gp: DecimalStr | null;
    forecast_gp: DecimalStr | null;
    actual_gp: DecimalStr | null;
  };
  missing_cost_inputs: FinanceMissingCostRow[];
  exceptions_and_exposure: FinanceExposureRow[];
  notes?: Record<string, string>;
}

export interface DeliveryEstimateAwaitingReview {
  id: UUID;
  submitted_at: ISODateTime | null;
  submitted_by: UUID | null;
}

export interface DeliveryStaffingGap {
  resource_line_id: UUID;
  gm_model_id: UUID;
  role: string;
  seniority: string;
  location: "US" | "India";
  start_date: ISODate;
  days_until_start: number;
  lead_time_days: number;
  warning: string;
}

export interface DeliveryUpcomingStart {
  resource_line_id: UUID;
  gm_model_id: UUID;
  role: string;
  seniority: string;
  location: "US" | "India";
  start_date: ISODate;
  person_name: string | null;
}

export interface DeliveryDashboard {
  estimates_awaiting_review: DeliveryEstimateAwaitingReview[];
  staffing_gaps: DeliveryStaffingGap[];
  upcoming_starts: DeliveryUpcomingStart[];
  effort_variance: Array<Record<string, unknown>>;
  notes?: Record<string, string>;
}

export interface SalesMyDeal {
  id: UUID;
  hubspot_deal_id: string;
  governance_status: string;
  sales_stage: string | null;
  engagement_type: string | null;
  client_id: UUID | null;
  next_client_action: string | null;
  next_client_date: ISODate | null;
}

export interface SalesMissingContract {
  client_id: UUID;
  client_name: string | null;
  coverage_state: string;
}

export interface SalesAdviserEstimate {
  id: UUID;
  submitted_at: ISODateTime | null;
  label: string;
  reviewed: boolean;
}

export interface SalesApprovalStatus {
  id: UUID;
  opportunity_id: UUID;
  status: ApprovalPackageStatus;
  submitted_at: ISODateTime | null;
}

export interface SalesDashboard {
  my_deals: SalesMyDeal[];
  next_client_actions: SalesMyDeal[];
  missing_contracts: SalesMissingContract[];
  adviser_estimates: SalesAdviserEstimate[];
  approval_statuses: SalesApprovalStatus[];
}

export interface HrDemandBySkillRow {
  role: string;
  seniority: string;
  location: "US" | "India";
  confirmed_fte: DecimalStr | null;
  weighted_fte: DecimalStr | null;
}

export interface HrDashboard {
  demand_by_skill: HrDemandBySkillRow[];
}

export interface LegalPackageAwaiting {
  id: UUID;
  opportunity_id: UUID;
  submitted_at: ISODateTime | null;
}

export interface LegalNoticeDate {
  agreement_id: UUID;
  kind: string;
  state: string;
  due_date: ISODate | null;
  next_action: string | null;
  owner_email: string | null;
}

export interface LegalDashboard {
  nda_msa_coverage_summary: Record<string, number>;
  packages_awaiting_legal: LegalPackageAwaiting[];
  notice_dates_approaching: LegalNoticeDate[];
}

export interface ClientSowRow {
  opportunity_id: UUID;
  hubspot_deal_id: string;
  gm_model_id: UUID;
  engagement_type: string;
  start_date: ISODate | null;
  end_date: ISODate | null;
  revenue_us: DecimalStr | null;
  revenue_india: DecimalStr | null;
  cost_us: DecimalStr | null;
  cost_india: DecimalStr | null;
  approved_gm: DecimalStr | null;
  forecast_gm: DecimalStr | null;
  actual_gm: DecimalStr | null;
  exception_flag: boolean;
}

export interface ClientSowTotals {
  revenue_us: DecimalStr | null;
  revenue_india: DecimalStr | null;
  revenue: DecimalStr | null;
  cost_us: DecimalStr | null;
  cost_india: DecimalStr | null;
  cost: DecimalStr | null;
  gross_profit: DecimalStr | null;
  client_gm: DecimalStr | null;
  formula: string;
}

export interface ClientSowGmDashboard {
  client_id: UUID;
  client_name: string | null;
  rows: ClientSowRow[];
  totals: ClientSowTotals;
}

export function getCeoDashboard(): Promise<CeoDashboard> {
  return request<CeoDashboard>(`/dashboards/ceo`);
}

export function getFinanceDashboard(): Promise<FinanceDashboard> {
  return request<FinanceDashboard>(`/dashboards/finance`);
}

export function getDeliveryDashboard(): Promise<DeliveryDashboard> {
  return request<DeliveryDashboard>(`/dashboards/delivery`);
}

export function getSalesDashboard(): Promise<SalesDashboard> {
  return request<SalesDashboard>(`/dashboards/sales`);
}

export function getHrDashboard(): Promise<HrDashboard> {
  return request<HrDashboard>(`/dashboards/hr`);
}

export function getLegalDashboard(): Promise<LegalDashboard> {
  return request<LegalDashboard>(`/dashboards/legal`);
}

export function getClientSowGmDashboard(
  clientId: UUID,
): Promise<ClientSowGmDashboard> {
  return request<ClientSowGmDashboard>(`/dashboards/client/${clientId}`);
}

// --- Signed SOW verify + distribution (S5 E8) ------------------------------

/**
 * The four "material terms" the signed SOW diff engine locks against.
 * Kept in lock-step with ``app.services.signed_sow._MATERIAL_FIELDS``.
 */
export type SignedSowFieldName =
  | "price"
  | "term_start"
  | "term_end"
  | "scope_summary";

/** One row in the side-by-side diff viewer. */
export interface SignedSowDiffField {
  field: SignedSowFieldName;
  approved: string | null;
  extracted: string | null;
  match: boolean;
  // Only populated on the scope row.
  similarity?: number;
  threshold?: number;
}

export interface SignedSowDiff {
  fields: SignedSowDiffField[];
  match: boolean;
  reason?: string;
}

export type SignedSowVerifyStatus = "pending" | "verified" | "blocked";

export interface SignedSowUpload {
  id: UUID;
  package_id: UUID;
  file_s3_key: string;
  file_hash: string;
  uploaded_by: UUID;
  uploaded_at: ISODateTime | null;
  verify_status: SignedSowVerifyStatus;
  diff_json: SignedSowDiff | null;
  verified_at: ISODateTime | null;
  released_at: ISODateTime | null;
}

export interface SignedSowUploadUrlRequest {
  filename: string;
  content_type: string;
}

export interface SignedSowUploadUrlResponse {
  url: string;
  s3_key: string;
  method: "PUT";
  expires_in: number;
  required_headers?: Record<string, string> | null;
  max_bytes: number;
}

export interface CreateSignedSowUploadBody {
  file_s3_key: string;
  file_hash: string;
}

export function getSignedSowUploadUrl(
  packageId: UUID,
  body: SignedSowUploadUrlRequest,
): Promise<SignedSowUploadUrlResponse> {
  return request<SignedSowUploadUrlResponse>(
    `/signed-sow/${packageId}/upload-url`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function createSignedSowUpload(
  packageId: UUID,
  body: CreateSignedSowUploadBody,
): Promise<SignedSowUpload> {
  return request<SignedSowUpload>(`/signed-sow/${packageId}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSignedSowUpload(
  packageId: UUID,
): Promise<SignedSowUpload | null> {
  return request<SignedSowUpload | null>(`/signed-sow/${packageId}`);
}

export function verifySignedSow(packageId: UUID): Promise<SignedSowUpload> {
  return request<SignedSowUpload>(`/signed-sow/${packageId}/verify`, {
    method: "POST",
  });
}

export function releaseSignedSow(packageId: UUID): Promise<SignedSowUpload> {
  return request<SignedSowUpload>(`/signed-sow/${packageId}/release`, {
    method: "POST",
  });
}

// --- Weekly forecast (S6 E9) ----------------------------------------------

/**
 * One entry in the ``forecast_lines_json`` snapshot. Money-like fields are
 * Decimal strings (blueprint §2). ``remaining_hours`` is what the Delivery
 * lead posts each week; the rest is the read-only echo the API keeps so
 * the trend replay can show geography without joining ``resource_line``.
 */
export interface ForecastLineSnapshot {
  resource_line_id: UUID;
  role: string;
  seniority: string;
  location: "US" | "India";
  remaining_hours: DecimalStr;
  hourly_cost: DecimalStr | null;
  allocation_pct: DecimalStr;
}

export interface ForecastPeriod {
  id: UUID;
  gm_model_id: UUID;
  week_ending: ISODate;
  forecast_lines_json: ForecastLineSnapshot[];
  forecast_revenue: DecimalStr;
  forecast_cost_us: DecimalStr;
  forecast_cost_india: DecimalStr;
  forecast_gm_us: DecimalStr | null;
  forecast_gm_india: DecimalStr | null;
  updated_by: UUID | null;
  updated_at: ISODateTime | null;
}

export interface ForecastHistoryResponse {
  items: ForecastPeriod[];
}

/** One row of the update payload. Kept as string on the wire so the
 * browser never coerces a Decimal into a float. */
export interface ForecastLineInput {
  resource_line_id: UUID;
  remaining_hours: DecimalStr;
}

export function postForecast(
  gmModelId: UUID,
  lines: ForecastLineInput[],
): Promise<ForecastPeriod> {
  return request<ForecastPeriod>(`/forecast/${gmModelId}`, {
    method: "POST",
    body: JSON.stringify({ lines }),
  });
}

export function getLatestForecast(
  gmModelId: UUID,
): Promise<ForecastPeriod | null> {
  return request<ForecastPeriod | null>(`/forecast/${gmModelId}/latest`);
}

export function getForecastHistory(
  gmModelId: UUID,
  limit = 52,
): Promise<ForecastHistoryResponse> {
  return request<ForecastHistoryResponse>(
    `/forecast/${gmModelId}/history?limit=${limit}`,
  );
}

// --- Actuals CSV import (S6 E9) ------------------------------------------

/**
 * A single actuals-import batch. Status lifecycle:
 * ``uploading`` -> ``validated`` -> ``committed`` on success, or
 * ``failed`` with row-level ``errors`` when validation rejects the file
 * (all-or-nothing per blueprint §2).
 */
export interface ActualBatch {
  id: UUID;
  uploaded_by: UUID;
  status: "uploading" | "validated" | "committed" | "failed" | string;
  row_count: number;
  errors: Array<Record<string, unknown>> | null;
}

export interface ActualBatchListResponse {
  items: ActualBatch[];
  page: number;
  size: number;
  total: number;
}

export interface ActualGmResponse {
  gm_model_id: UUID;
  period_month: ISODate;
  revenue: DecimalStr;
  cost_us: DecimalStr;
  cost_india: DecimalStr;
  gm_us: DecimalStr | null;
  gm_india: DecimalStr | null;
}

/**
 * Uploads a CSV of actuals to the batch endpoint. Returns 422 with a
 * per-row error report when validation fails (whole-file reject).
 */
export async function importActualsCsv(file: File): Promise<ActualBatch> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/actuals/import`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "detail" in body
        ? typeof (body as { detail: unknown }).detail === "string"
          ? String((body as { detail: unknown }).detail)
          : `API error ${res.status}`
        : `API error ${res.status}`;
    throw new ApiError(res.status, body, message);
  }
  return body as ActualBatch;
}

export function listActualBatches(
  query: { page?: number; size?: number } = {},
): Promise<ActualBatchListResponse> {
  const params = new URLSearchParams();
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<ActualBatchListResponse>(
    `/actuals/batches${qs ? `?${qs}` : ""}`,
  );
}

export function getActualBatch(id: UUID): Promise<ActualBatch> {
  return request<ActualBatch>(`/actuals/batches/${id}`);
}

export function getActualGm(
  gmModelId: UUID,
  periodMonth: string,
): Promise<ActualGmResponse> {
  const qs = new URLSearchParams({ period_month: periodMonth }).toString();
  return request<ActualGmResponse>(
    `/actuals/gm-model/${gmModelId}?${qs}`,
  );
}

// --- Bulk SOW import (S10-02) ---------------------------------------------

/**
 * One batch envelope + queue of imported files. The pipeline that
 * drives each file is the *same* code path a single upload uses
 * (`services/sow_upload_pipeline.apply_pipeline`) — bulk is a second
 * entry, not a parallel implementation.
 *
 * Legacy imports always land with `governance_status =
 * 'legacy_not_evidenced'` on their `sow_version`; the UI surfaces this
 * with a "Legacy" chip on every record surface.
 */
export type BulkImportBatchStatus = "processing" | "completed" | "failed";

export type BulkImportFileStatus =
  | "queued"
  | "extracting"
  | "classifying"
  | "matching_client"
  | "deriving_gm"
  | "needs_review"
  | "imported"
  | "rejected"
  | "duplicate";

export interface BulkImportBatchSummary {
  id: UUID;
  run_by: UUID;
  status: BulkImportBatchStatus | string;
  file_count: number;
  queued_count: number;
  imported_count: number;
  rejected_count: number;
  duplicate_count: number;
  needs_review_count: number;
  note: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface BulkImportFileRow {
  id: UUID;
  batch_id: UUID;
  filename: string;
  size_bytes: number;
  sha256: string;
  detected_type: string | null;
  status: BulkImportFileStatus | string;
  matched_client_id: UUID | null;
  matched_confidence: string | null;
  opportunity_id: UUID | null;
  sow_version_id: UUID | null;
  duplicate_of: UUID | null;
  warnings: unknown[];
  errors: unknown[];
  needs_you: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface BulkImportFilesResponse {
  items: BulkImportFileRow[];
}

export interface BulkImportStartResponse {
  batch_id: UUID;
  file_count: number;
}

export async function startBulkImport(
  files: File[],
): Promise<BulkImportStartResponse> {
  if (files.length === 0) {
    throw new ApiError(400, null, "at least one file is required");
  }
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const res = await fetch(`${BASE_URL}/admin/bulk-imports/sows`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
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
  return body as BulkImportStartResponse;
}

export function getBulkImportBatch(
  batchId: UUID,
): Promise<BulkImportBatchSummary> {
  return request<BulkImportBatchSummary>(
    `/admin/bulk-imports/${batchId}`,
  );
}

export function getBulkImportFiles(
  batchId: UUID,
): Promise<BulkImportFilesResponse> {
  return request<BulkImportFilesResponse>(
    `/admin/bulk-imports/${batchId}/files`,
  );
}

export async function downloadBulkImportLog(batchId: UUID): Promise<Blob> {
  const res = await fetch(
    `${BASE_URL}/admin/bulk-imports/${batchId}/log.csv`,
    { method: "GET", headers: { ...(await authHeaders()) } },
  );
  if (!res.ok) {
    const text = await res.text();
    const body = text ? safeJson(text) : null;
    const message =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `API error ${res.status}`;
    throw new ApiError(res.status, body, message);
  }
  return await res.blob();
}

export async function rerunBulkImport(
  batchId: UUID,
  files: File[] = [],
): Promise<BulkImportBatchSummary> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const res = await fetch(
    `${BASE_URL}/admin/bulk-imports/${batchId}/rerun`,
    {
      method: "POST",
      headers: { ...(await authHeaders()) },
      body: form,
    },
  );
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `API error ${res.status}`;
    throw new ApiError(res.status, body, message);
  }
  return body as BulkImportBatchSummary;
}

// --- Admin replay (S6) -----------------------------------------------------

/**
 * DLQ views + replay actions. The API gates every endpoint behind
 * ``SystemAdmin`` so the nav-link gate on the frontend is UX only.
 */
export interface AdminReplayHubspotRow {
  id: UUID;
  opportunity_id: UUID;
  hubspot_deal_id: string;
  target_state: Record<string, unknown>;
  status: string;
  attempts: number;
  next_attempt_at: ISODateTime | null;
  last_error: string | null;
  created_at: ISODateTime;
  sent_at: ISODateTime | null;
}

export interface AdminReplayNotificationRow {
  id: UUID;
  user_id: UUID;
  category: string;
  channel: string;
  subject: string;
  status: string;
  attempts: number;
  next_attempt_at: ISODateTime | null;
  last_error: string | null;
  created_at: ISODateTime;
  sent_at: ISODateTime | null;
}

export interface AdminReplayIntegrationEventRow {
  id: UUID;
  source: string;
  source_event_id: string;
  received_at: ISODateTime;
  processed_at: ISODateTime | null;
  payload: Record<string, unknown>;
}

export interface AdminReplayListResponse<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
}

export interface AdminReplayResponse {
  id: UUID;
  status: string;
}

export interface AdminReplayPageQuery {
  page?: number;
  size?: number;
}

function pageParams(query: AdminReplayPageQuery): string {
  const params = new URLSearchParams();
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function listAdminReplayHubspotWriteback(
  query: AdminReplayPageQuery = {},
): Promise<AdminReplayListResponse<AdminReplayHubspotRow>> {
  return request<AdminReplayListResponse<AdminReplayHubspotRow>>(
    `/admin/replay/hubspot-writeback${pageParams(query)}`,
  );
}

export function replayAdminHubspotWriteback(
  jobId: UUID,
): Promise<AdminReplayResponse> {
  return request<AdminReplayResponse>(
    `/admin/replay/hubspot-writeback/${jobId}`,
    { method: "POST" },
  );
}

export function listAdminReplayNotifications(
  query: AdminReplayPageQuery = {},
): Promise<AdminReplayListResponse<AdminReplayNotificationRow>> {
  return request<AdminReplayListResponse<AdminReplayNotificationRow>>(
    `/admin/replay/notifications${pageParams(query)}`,
  );
}

export function replayAdminNotification(
  notificationId: UUID,
): Promise<AdminReplayResponse> {
  return request<AdminReplayResponse>(
    `/admin/replay/notifications/${notificationId}`,
    { method: "POST" },
  );
}

export function listAdminReplayIntegrationEvents(
  query: AdminReplayPageQuery = {},
): Promise<AdminReplayListResponse<AdminReplayIntegrationEventRow>> {
  return request<AdminReplayListResponse<AdminReplayIntegrationEventRow>>(
    `/admin/replay/integration-events${pageParams(query)}`,
  );
}

export function replayAdminIntegrationEvent(
  eventId: UUID,
): Promise<AdminReplayResponse> {
  return request<AdminReplayResponse>(
    `/admin/replay/integration-events/${eventId}`,
    { method: "POST" },
  );
}

// --- Capability catalog (S7 wave 2) ---------------------------------------

/**
 * One curated capability entry. The API never returns the raw embedding —
 * ``has_embedding`` is a boolean flag so the UI can surface "pending
 * embed" without paging a 1536-float blob into the browser.
 */
export interface CapabilityRow {
  id: UUID;
  name: string;
  description: string;
  tags: string[];
  has_embedding: boolean;
  curated_by: UUID | null;
  created_at: ISODateTime | null;
  updated_at: ISODateTime | null;
}

export interface CapabilityListResponse {
  items: CapabilityRow[];
  page: number;
  size: number;
  total: number;
}

export interface ListCapabilitiesQuery {
  search?: string;
  tag?: string;
  page?: number;
  size?: number;
}

export interface CreateCapabilityBody {
  name: string;
  description: string;
  tags?: string[];
}

export interface PatchCapabilityBody {
  name?: string;
  description?: string;
  tags?: string[];
}

export function listCapabilities(
  query: ListCapabilitiesQuery = {},
): Promise<CapabilityListResponse> {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.tag) params.set("tag", query.tag);
  if (query.page) params.set("page", String(query.page));
  if (query.size) params.set("size", String(query.size));
  const qs = params.toString();
  return request<CapabilityListResponse>(
    `/admin/capability-catalog${qs ? `?${qs}` : ""}`,
  );
}

export function createCapability(
  body: CreateCapabilityBody,
): Promise<CapabilityRow> {
  return request<CapabilityRow>(`/admin/capability-catalog`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchCapability(
  id: UUID,
  body: PatchCapabilityBody,
): Promise<CapabilityRow> {
  return request<CapabilityRow>(`/admin/capability-catalog/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteCapability(id: UUID): Promise<void> {
  return request<void>(`/admin/capability-catalog/${id}`, { method: "DELETE" });
}

// --- Deletion + archive (S13a-FE) -----------------------------------------

/**
 * The five terminal states the server returns for the delete/archive
 * assessment + write endpoints. Mirrors
 * ``api/app/services/deletion.py::DeletionAssessment``.
 *
 * - ``draft``           — hard-deletable, no approvals, no signature, no HubSpot.
 * - ``approved``        — an approval package or signed SOW exists; archive only.
 * - ``hubspot_linked``  — linked to a live HubSpot deal; archive only (a hard
 *                        delete would resurrect on the next HubSpot sync).
 * - ``archived``        — write response only; the record was just archived.
 * - ``deleted``         — write response only; the record was just hard-deleted.
 */
export type DeletionState =
  | "draft"
  | "approved"
  | "hubspot_linked"
  | "archived"
  | "deleted";

/**
 * Cascade + governance envelope. The confirmation dialog renders every
 * entry of ``counts`` verbatim so the user sees exactly what a hard
 * delete removes (directive §"cascade counts").
 */
export interface DeletionAssessmentResponse {
  state: DeletionState;
  reason: string;
  counts: Record<string, number>;
}

export function assessClientDeletion(
  clientId: UUID,
): Promise<DeletionAssessmentResponse> {
  return request<DeletionAssessmentResponse>(
    `/clients/${clientId}/deletion-assessment`,
  );
}

export function deleteClient(
  clientId: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return request<DeletionAssessmentResponse>(`/clients/${clientId}${qs}`, {
    method: "DELETE",
  });
}

export function archiveClient(
  clientId: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  return request<DeletionAssessmentResponse>(`/clients/${clientId}/archive`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export function assessOpportunityDeletion(
  opportunityId: UUID,
): Promise<DeletionAssessmentResponse> {
  return request<DeletionAssessmentResponse>(
    `/opportunities/${opportunityId}/deletion-assessment`,
  );
}

export function deleteOpportunity(
  opportunityId: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return request<DeletionAssessmentResponse>(
    `/opportunities/${opportunityId}${qs}`,
    { method: "DELETE" },
  );
}

export function archiveOpportunity(
  opportunityId: UUID,
  reason?: string,
): Promise<DeletionAssessmentResponse> {
  return request<DeletionAssessmentResponse>(
    `/opportunities/${opportunityId}/archive`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
}

/**
 * Bulk-import batch cleanup. Per-record state rules still apply on the
 * server: a promoted, later-approved SOW blocks its own row and is
 * reported back in ``counts.skipped_approved``.
 */
export function deleteBulkImportBatch(
  batchId: UUID,
): Promise<DeletionAssessmentResponse> {
  return request<DeletionAssessmentResponse>(
    `/admin/bulk-imports/${batchId}`,
    { method: "DELETE" },
  );
}
