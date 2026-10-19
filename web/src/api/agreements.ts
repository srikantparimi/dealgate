// S24-AG1 · NDA & MSA (docs/reference/openapi-agreements.yaml). Every state,
// count and list comes from the server's one shared agreement_status service,
// so a card and the list it opens always agree. The browser never computes a
// state; it only renders what the API says.
import {
  ApiError,
  authHeaders,
  BASE_URL,
  errorMessage,
  request,
  requestBlob,
  type ISODate,
  type ISODateTime,
  type UUID,
} from "./client";

export type AgreementKind = "NDA" | "MSA";
export const AGREEMENT_KINDS: readonly AgreementKind[] = ["NDA", "MSA"];
export type Relationship = "existing" | "net_new";
export type RelationshipBasis = "closed_won" | "sow_engagement" | "closed_won_and_sow" | "manual" | "none";
export type DocState = "client" | "standard" | "covered" | "missing" | "due_later" | "not_needed" | "existing_none";
export type Requirement = "required" | "later" | "none";
export type BusinessUnitName = "ST21" | "IT Avalon" | "Retro Rabbit";
export type ClientFlag = "possible_duplicate" | "test_data" | "unknown_company" | "no_hubspot_link";
export type CardKey = "clients" | "existing" | "net_new" | "needs_attention" | "standard_attached" | "client_copies";
export type MarkReason =
  | "signed_outside_dealgate"
  | "covered_by_earlier_work"
  | "confirmed_with_client"
  | "per_hubspot"
  | "other";
export type BatchStatus = "running" | "done" | "failed" | "undoing" | "undone";
export type ActivityAction =
  | "standard_uploaded"
  | "client_uploaded"
  | "client_replaced"
  | "standard_attached"
  | "detached"
  | "marked"
  | "mark_removed"
  | "relationship_changed"
  | "batch_run"
  | "batch_undone"
  | "hubspot_applied"
  | "downloaded"
  | "exported";

export type RelationshipFilter = "all" | "existing" | "net_new";
export type StatusFilter =
  | "any"
  | "attention"
  | "missing_nda"
  | "missing_msa"
  | "has_standard"
  | "has_client"
  | "marked_covered"
  | "possible_duplicate";
export type StageFilter = "any" | "past_stage_1" | "stage_1_only" | "no_active_deal";
export type AgreementsSort = "attention" | "name" | "stage";
export type AgreementsPageSize = 25 | 50 | 100;
export const AGREEMENTS_PAGE_SIZES: readonly AgreementsPageSize[] = [25, 50, 100];

export interface BusinessUnit {
  name: BusinessUnitName;
  region: "US" | "South Africa";
}

export interface Card {
  key: CardKey;
  label: string;
  value: number;
  note: string;
  /** Query parameters for the workspace that return exactly `value` clients. */
  drill: Partial<Record<string, string | string[]>>;
}

export interface DocBrief {
  state: DocState;
  source_label?: string | null;
}

export interface ClientRow {
  client_id: UUID;
  name: string;
  relationship: Relationship;
  relationship_basis: RelationshipBasis;
  requirement: Requirement;
  nda: DocBrief;
  msa: DocBrief;
  needs_attention: boolean;
  /** 0 means no open deal. Hold counts as open at its stage. */
  furthest_open_stage: number;
  business_units: BusinessUnit[];
  deal_count: number;
  flags: ClientFlag[];
  /** Additive: true before the cutover, when the relationship is computed live. */
  provisional?: boolean;
  /** Additive: the basis in words, as the page shows it. */
  basis_text?: string;
  /** Additive: the client has an open deal on Hold (Hold has no recorded stage; it counts as past stage 1). */
  on_hold?: boolean;
  /** Additive: "4 · Proposal", "On hold", "4 · Proposal (and on hold)", "Stage not recognised" or "No active deal". */
  stage_text?: string;
  /** Additive: why business_units is empty, e.g. "Region not mapped to a business unit: X". */
  business_unit_note?: string | null;
}

export interface Mark {
  reason: MarkReason;
  note?: string | null;
  marked_on: ISODate;
  marked_by: string;
  source: "dealgate" | "hubspot";
  hubspot_value?: string | null;
  /** Additive: the reason in words. */
  reason_label?: string;
}

export interface HistoryEntry {
  at: ISODateTime;
  by: string;
  what: string;
}

export interface DocCard {
  kind: AgreementKind;
  state: DocState;
  agreement_id?: UUID | null;
  file_name?: string | null;
  file_size?: number | null;
  source?: "client" | "standard" | null;
  standard_version?: number | null;
  batch_id?: string | null;
  version_no?: number | null;
  uploaded_by?: string | null;
  uploaded_at?: ISODateTime | null;
  note?: string | null;
  mark?: Mark | null;
  hubspot_hint?: string | null;
  history: HistoryEntry[];
  /** Additive: the current standard version of this kind, when one exists (for "Attach standard copy"). */
  standard_available_version?: number | null;
}

export interface ClientAgreements {
  client_id: UUID;
  name: string;
  relationship: Relationship;
  relationship_basis: RelationshipBasis;
  relationship_set_by?: string | null;
  relationship_set_at?: ISODateTime | null;
  requirement: Requirement;
  needs_attention: boolean;
  possible_duplicates?: string[];
  deals: {
    open: number;
    won: number;
    lost: number;
    furthest_open_stage: number;
    /** Additive. */
    on_hold?: boolean;
    stage_text?: string;
  };
  nda: DocCard;
  msa: DocCard;
  can_write: boolean;
  /** Additive: the page's other client facts. */
  stage_text?: string;
  business_units?: BusinessUnit[];
  flags?: ClientFlag[];
  provisional?: boolean;
  basis_text?: string;
  /** Additive: why business_units is empty, as on the Clients row. */
  business_unit_note?: string | null;
}

export interface StandardVersion {
  kind: AgreementKind;
  version: number;
  file_name: string;
  file_size: number;
  sha256?: string;
  uploaded_by: string;
  uploaded_at: ISODateTime;
  attached_clients: number;
}

export interface StandardDocuments {
  NDA: StandardVersion | null;
  MSA: StandardVersion | null;
}

export interface Batch {
  id: string;
  status: BatchStatus;
  kinds: AgreementKind[];
  created_by: string;
  created_at: ISODateTime;
  target_count: number;
  done_count: number;
  attached_count: number;
  skipped_count: number;
  error?: string | null;
  undone_at?: ISODateTime | null;
  undone_by?: string | null;
  /** Additive: how many standard attachments an undo removed, or would remove. */
  undone_count?: number;
  undo_would_remove?: number;
  /** Additive: clients that received at least one copy (attached_count counts rows; both kinds count two). */
  attached_clients?: number;
  /** Additive: for a failed batch, which job stopped: the attach run or its undo. */
  failed_phase?: "run" | "undo" | null;
}

export interface AgreementsWorkspace {
  cutover: { set: boolean; date?: ISODate | null; latest_batch?: Batch | null };
  cards: Card[];
  standard: StandardDocuments;
  total: number;
  items: ClientRow[];
  /** Additive: the caller's write rights, so locked controls can say why. */
  can_write?: boolean;
  is_admin?: boolean;
  /** Additive: tab counts for Documents and Activity. */
  document_count?: number;
  /** Null when the count was not loaded. */
  activity_count?: number | null;
}

export interface DocumentRow {
  client_id: UUID;
  client_name: string;
  kind: AgreementKind;
  file_name: string;
  source: "client" | "standard";
  standard_version?: number | null;
  batch_id?: string | null;
  uploaded_by: string;
  uploaded_at: ISODateTime;
  /** Additive: the agreement row, for history and replace. */
  agreement_id?: UUID;
  version_no?: number;
}

export interface ActivityRow {
  at: ISODateTime;
  by: string;
  action: ActivityAction;
  text: string;
  client_id?: UUID | null;
}

export interface DownloadLink {
  url: string;
  expires_in_seconds: 300;
  file_name: string;
}

export interface BatchRequest {
  kinds: AgreementKind[];
  dry_run?: boolean;
  include_net_new_past_stage_1?: boolean;
  include_client_ids?: UUID[];
  exclude_client_ids?: UUID[];
  idempotency_key?: string;
  confirm?: string;
}

export interface BatchTarget {
  client_id: UUID;
  name: string;
  relationship: Relationship;
  included: boolean;
  reason: "" | "stage_1_only" | "test_data";
}

export interface BatchPreview {
  kinds: AgreementKind[];
  will_receive: number;
  net_new_included: number;
  already_hold: number;
  net_new_untouched: number;
  targets: BatchTarget[];
}

export interface HubspotValues {
  stored: boolean;
  items: {
    value: string;
    clients: number;
    action: "covered" | "ignore";
    /** Additive: visible clients with this hint that hold nothing for the MSA (the apply would mark them). */
    would_mark?: number;
  }[];
  /** Additive: who saved the mapping last, and when; whether the caller may change it. */
  saved_by?: string | null;
  saved_at?: string | null;
  can_edit?: boolean;
}

export interface WorkspaceQuery {
  relationship: RelationshipFilter;
  status: StatusFilter;
  stage: StageFilter;
  bu: BusinessUnitName[];
  q: string;
  sort: AgreementsSort;
  page: number;
  page_size: AgreementsPageSize;
}

export const DEFAULT_AGREEMENTS_QUERY: WorkspaceQuery = {
  relationship: "all",
  status: "any",
  stage: "any",
  bu: [],
  q: "",
  sort: "attention",
  page: 1,
  page_size: 25,
};

/** The query string for the workspace or the export. Defaults are left out. */
export function agreementsParams(query: Partial<WorkspaceQuery>, opts: { forExport?: boolean } = {}): URLSearchParams {
  const q = { ...DEFAULT_AGREEMENTS_QUERY, ...query };
  const d = DEFAULT_AGREEMENTS_QUERY;
  const p = new URLSearchParams();
  if (q.relationship !== d.relationship) p.set("relationship", q.relationship);
  if (q.status !== d.status) p.set("status", q.status);
  if (q.stage !== d.stage) p.set("stage", q.stage);
  q.bu.forEach((b) => p.append("bu", b));
  if (q.q.trim()) p.set("q", q.q.trim());
  if (q.sort !== d.sort) p.set("sort", q.sort);
  if (!opts.forExport) {
    if (q.page !== d.page) p.set("page", String(q.page));
    if (q.page_size !== d.page_size) p.set("page_size", String(q.page_size));
  }
  return p;
}

const enc = encodeURIComponent;

export function getAgreementsWorkspace(query: Partial<WorkspaceQuery>, signal?: AbortSignal) {
  return request<AgreementsWorkspace>(`/agreements/workspace?${agreementsParams(query)}`, { signal });
}

/** The entire filtered client view as CSV (every row), saved through the browser. */
export async function downloadAgreementsCsv(query: Partial<WorkspaceQuery>): Promise<string> {
  const { blob, filename } = await requestBlob(`/agreements/export?${agreementsParams(query, { forExport: true })}`);
  const name = filename ?? "DealGate_Agreements.csv";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return name;
}

export interface PageQuery {
  q?: string;
  page?: number;
  page_size?: AgreementsPageSize;
}

function pageParams(query: object): string {
  const p = new URLSearchParams();
  Object.entries(query as Record<string, string | number | undefined | null>).forEach(([key, value]) => {
    if (value === undefined || value === "" || value === null) return;
    if (key === "page" && value === 1) return;
    if (key === "page_size" && value === 25) return;
    p.set(key, String(value));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function getAgreementDocuments(
  query: PageQuery & { kind?: AgreementKind; source?: "client" | "standard" },
  signal?: AbortSignal,
) {
  return request<{ total: number; items: DocumentRow[] }>(`/agreements/documents${pageParams(query)}`, { signal });
}

export function getAgreementActivity(query: PageQuery, signal?: AbortSignal) {
  return request<{ total: number; items: ActivityRow[] }>(`/agreements/activity${pageParams(query)}`, { signal });
}

export function getStandardDocuments() {
  return request<StandardDocuments>(`/agreements/standard`);
}

export function getStandardDownloadLink(kind: AgreementKind) {
  return request<DownloadLink>(`/agreements/standard/${kind}/download`);
}

export function getClientAgreements(clientId: UUID, signal?: AbortSignal) {
  return request<ClientAgreements>(`/clients/${enc(clientId)}/agreements`, { signal });
}

export function getClientDownloadLink(clientId: UUID, kind: AgreementKind) {
  return request<DownloadLink>(`/clients/${enc(clientId)}/agreements/${kind}/download`);
}

export function attachStandardToClient(clientId: UUID, kind: AgreementKind) {
  return request<DocCard>(`/clients/${enc(clientId)}/agreements/${kind}/attach-standard`, { method: "POST" });
}

export function markCovered(
  clientId: UUID,
  kind: AgreementKind,
  body: { reason: Exclude<MarkReason, "per_hubspot">; marked_on: ISODate; note?: string },
) {
  return request<DocCard>(`/clients/${enc(clientId)}/agreements/${kind}/mark`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function removeMark(clientId: UUID, kind: AgreementKind) {
  return request<DocCard>(`/clients/${enc(clientId)}/agreements/${kind}/mark`, { method: "DELETE" });
}

/** Detach a kind. A client copy starts a deletion job (202); a standard attachment is removed at once (200). */
export function detachAgreement(clientId: UUID, kind: AgreementKind) {
  return request<{ job_id?: UUID | null; status?: string } | DocCard | null>(
    `/clients/${enc(clientId)}/agreements/${kind}`,
    { method: "DELETE" },
  );
}

export function setRelationship(clientId: UUID, body: { relationship: Relationship; note?: string }) {
  return request<ClientAgreements>(`/clients/${enc(clientId)}/relationship`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function previewBatch(body: BatchRequest) {
  return request<BatchPreview>(`/agreements/batches`, {
    method: "POST",
    body: JSON.stringify({ ...body, dry_run: true }),
  });
}

export function startBatch(body: BatchRequest & { idempotency_key: string; confirm: string }) {
  return request<Batch>(`/agreements/batches`, { method: "POST", body: JSON.stringify({ ...body, dry_run: false }) });
}

export function listBatches() {
  return request<{ items: Batch[] }>(`/agreements/batches`);
}

export function getBatch(label: string, signal?: AbortSignal) {
  return request<Batch>(`/agreements/batches/${enc(label)}`, { signal });
}

export function undoBatch(label: string) {
  return request<Batch>(`/agreements/batches/${enc(label)}/undo`, { method: "POST" });
}

export function getHubspotValues() {
  return request<HubspotValues>(`/agreements/hubspot-values`);
}

export function saveHubspotMapping(items: { value: string; action: "covered" | "ignore" }[]) {
  return request<HubspotValues>(`/agreements/hubspot-mapping`, { method: "PUT", body: JSON.stringify({ items }) });
}

export function applyHubspotMapping(dryRun: boolean) {
  return request<{ dry_run: boolean; would_mark: number; marked: number }>(
    `/agreements/hubspot-mapping/apply?dry_run=${dryRun ? "true" : "false"}`,
    { method: "POST" },
  );
}

/** Upload progress in bytes; `total` is the request body size the browser reports. */
export type UploadProgress = (loaded: number, total: number) => void;

/**
 * Multipart upload with real byte progress. fetch() cannot report upload
 * progress, so this uses XMLHttpRequest with the same auth headers and the
 * same error handling as request().
 */
export async function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress?: UploadProgress,
  signal?: AbortSignal,
): Promise<T> {
  const headers = await authHeaders();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (signal?.aborted) {
      reject(new DOMException("The upload was cancelled.", "AbortError"));
      return;
    }
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.onabort = () => reject(new DOMException("The upload was cancelled.", "AbortError"));
    xhr.open("POST", `${BASE_URL}${path}`);
    Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));
    if (onProgress) {
      xhr.upload.onprogress = (event) => onProgress(event.loaded, event.lengthComputable ? event.total : 0);
    }
    xhr.onerror = () => reject(new ApiError(0, null, "The upload could not reach the server. Check your connection."));
    xhr.onload = () => {
      let body: unknown = null;
      let json = true;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        json = false;
        body = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      // A gateway's HTML error page (a 502 or 504 from the load balancer or CDN) is never shown as the message.
      else if (!json) reject(new ApiError(xhr.status, null, `API error ${xhr.status}`));
      else reject(new ApiError(xhr.status, body, errorMessage(body, xhr.status)));
    };
    xhr.send(form);
  });
}

export function uploadStandard(kind: AgreementKind, file: File, onProgress?: UploadProgress, signal?: AbortSignal) {
  const form = new FormData();
  form.append("file", file);
  return uploadWithProgress<StandardVersion>(`/agreements/standard/${kind}`, form, onProgress, signal);
}

export function uploadClientCopy(
  clientId: UUID,
  kind: AgreementKind,
  file: File,
  note: string,
  onProgress?: UploadProgress,
  signal?: AbortSignal,
) {
  const form = new FormData();
  form.append("file", file);
  if (note.trim()) form.append("note", note.trim());
  return uploadWithProgress<DocCard>(`/clients/${enc(clientId)}/agreements/${kind}/client-copy`, form, onProgress, signal);
}
