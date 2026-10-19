// S24-AG1 F1 · the NDA & MSA page's view state. Every filter, the tab, the page
// and the open client panel live in the URL query string, so a link (the
// Command Center tile's /agreements?status=attention, the Pipeline's
// /agreements?client_id=…) or the back button restores the view. The page
// changes its state only through the transitions below.
//
// Cards ignore the filters (the server computes them over every client), so a
// card RESETS the filters and then applies its own drill; it never adds the
// drill to the current filters as the Pipeline's cards do (docs/bugs #10).
import {
  AGREEMENTS_PAGE_SIZES,
  DEFAULT_AGREEMENTS_QUERY,
  type AgreementKind,
  type AgreementsPageSize,
  type AgreementsSort,
  type Batch,
  type BusinessUnitName,
  type Card,
  type ClientRow,
  type RelationshipBasis,
  type RelationshipFilter,
  type StageFilter,
  type StatusFilter,
  type WorkspaceQuery,
} from "../../../api/agreements";

// --- what the server sends beyond the typed client (additive fields) ------------------------

/**
 * A client row as the server sends it. agreement_status.client_row adds these
 * fields to the contract's ClientRow; web/src/api/agreements.ts does not type
 * them yet, so the page reads them as optional.
 */
export type AgreementsClientRow = ClientRow & {
  /** A deal on Hold exists (Hold counts as open and past stage 1). */
  on_hold?: boolean;
  /** "4 · Proposal", "On hold", "4 · Proposal (and on hold)", "No active deal", "Stage not recognised". */
  stage_text?: string;
  /** Why business_units is empty, e.g. "Region not mapped to a business unit: Mars". */
  business_unit_note?: string | null;
};

/** A batch as the server sends it: plus how many clients (not rows) it attached. */
export type AgreementsBatch = Batch & { attached_clients?: number };

// --- the view state ------------------------------------------------------------------------

export type AgreementsTab = "clients" | "documents" | "activity";
export const AGREEMENTS_TABS: readonly AgreementsTab[] = ["clients", "documents", "activity"];

export interface AgreementsUrlState {
  tab: AgreementsTab;
  relationship: RelationshipFilter;
  status: StatusFilter;
  stage: StageFilter;
  bu: BusinessUnitName[];
  /** The search of the open tab (client name, document fields or activity text). */
  q: string;
  sort: AgreementsSort;
  /** The page of the open tab's list. */
  page: number;
  page_size: AgreementsPageSize;
  /** The client whose panel is open. */
  clientId: string | null;
  /** Legacy one-shot links (?kind=MSA&upload=1 from the client and deal pages): consumed, then dropped. */
  kind: AgreementKind | null;
  upload: boolean;
}

export const SEARCH_MAX = 120;

export interface Option<T extends string> {
  value: T;
  label: string;
}

export const RELATIONSHIP_OPTIONS: Option<RelationshipFilter>[] = [
  { value: "all", label: "All clients" },
  { value: "existing", label: "Existing clients" },
  { value: "net_new", label: "Net-new clients" },
];

export const STATUS_OPTIONS: Option<StatusFilter>[] = [
  { value: "any", label: "Any agreement status" },
  { value: "attention", label: "Needs attention" },
  { value: "missing_nda", label: "Missing NDA" },
  { value: "missing_msa", label: "Missing MSA" },
  { value: "has_standard", label: "Has a standard copy" },
  { value: "has_client", label: "Has a client copy" },
  { value: "marked_covered", label: "Marked covered" },
  { value: "possible_duplicate", label: "Possible duplicate names" },
];

export const STAGE_OPTIONS: Option<StageFilter>[] = [
  { value: "any", label: "Any deal stage" },
  { value: "past_stage_1", label: "Past stage 1 (stages 2 to 6)" },
  { value: "stage_1_only", label: "Stage 1 only" },
  { value: "no_active_deal", label: "No active deal" },
];

/** A business unit is never shown without its region. */
export const BU_OPTIONS: Option<BusinessUnitName>[] = [
  { value: "ST21", label: "ST21 · US" },
  { value: "IT Avalon", label: "IT Avalon · US" },
  { value: "Retro Rabbit", label: "Retro Rabbit · South Africa" },
];

export const SORT_OPTIONS: Option<AgreementsSort>[] = [
  { value: "attention", label: "Needs attention first" },
  { value: "name", label: "Name A to Z" },
  { value: "stage", label: "Furthest stage" },
];

const STAGE_CHIPS: Record<Exclude<StageFilter, "any">, string> = {
  past_stage_1: "Past stage 1",
  stage_1_only: "Stage 1 only",
  no_active_deal: "No active deal",
};

export const SEARCH_PLACEHOLDER: Record<AgreementsTab, string> = {
  clients: "Search clients",
  documents: "Search by client, type, file name or uploader",
  activity: "Search activity",
};

const values = <T extends string>(options: Option<T>[]): readonly T[] => options.map((o) => o.value);
const RELATIONSHIPS = values(RELATIONSHIP_OPTIONS);
const STATUSES = values(STATUS_OPTIONS);
const STAGES = values(STAGE_OPTIONS);
const BUS = values(BU_OPTIONS);
const SORTS = values(SORT_OPTIONS);

function pick<T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T {
  return raw !== null && (allowed as readonly string[]).includes(raw) ? (raw as T) : fallback;
}

/** Read the view from the URL. Unknown values fall back to the defaults instead of failing. */
export function readAgreementsUrl(sp: URLSearchParams): AgreementsUrlState {
  const d = DEFAULT_AGREEMENTS_QUERY;
  const page = Number(sp.get("page"));
  const size = Number(sp.get("page_size"));
  const kind = sp.get("kind");
  const askedBu = sp.getAll("bu");
  return {
    tab: pick(sp.get("tab"), AGREEMENTS_TABS, "clients"),
    relationship: pick(sp.get("relationship"), RELATIONSHIPS, d.relationship),
    status: pick(sp.get("status"), STATUSES, d.status),
    stage: pick(sp.get("stage"), STAGES, d.stage),
    bu: BUS.filter((b) => askedBu.includes(b)),
    q: (sp.get("q") ?? "").trim().slice(0, SEARCH_MAX),
    sort: pick(sp.get("sort"), SORTS, d.sort),
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size: (AGREEMENTS_PAGE_SIZES as readonly number[]).includes(size) ? (size as AgreementsPageSize) : d.page_size,
    // `client` is the S17 AgreementsPanel link's name for the same thing.
    clientId: sp.get("client_id") || sp.get("client") || null,
    kind: kind === "NDA" || kind === "MSA" ? kind : null,
    upload: sp.get("upload") === "1",
  };
}

/** The URL for a view. Defaults are left out; the legacy one-shot parameters are never written back. */
export function writeAgreementsUrl(s: AgreementsUrlState): URLSearchParams {
  const d = DEFAULT_AGREEMENTS_QUERY;
  const p = new URLSearchParams();
  if (s.tab !== "clients") p.set("tab", s.tab);
  if (s.relationship !== d.relationship) p.set("relationship", s.relationship);
  if (s.status !== d.status) p.set("status", s.status);
  if (s.stage !== d.stage) p.set("stage", s.stage);
  s.bu.forEach((b) => p.append("bu", b));
  const q = s.q.trim().slice(0, SEARCH_MAX);
  if (q) p.set("q", q);
  if (s.sort !== d.sort) p.set("sort", s.sort);
  if (s.page !== 1) p.set("page", String(s.page));
  if (s.page_size !== d.page_size) p.set("page_size", String(s.page_size));
  if (s.clientId) p.set("client_id", s.clientId);
  return p;
}

// --- transitions -----------------------------------------------------------------------------

/** Change filters (or the search). Any change goes back to page 1. */
export function withFilters(
  state: AgreementsUrlState,
  patch: Partial<Pick<AgreementsUrlState, "relationship" | "status" | "stage" | "bu" | "q" | "sort">>,
): AgreementsUrlState {
  return { ...state, ...patch, page: 1 };
}

/** Switch tab: the search and the page start again (the prototype); the client filters stay. */
export function setTab(state: AgreementsUrlState, tab: AgreementsTab): AgreementsUrlState {
  return { ...state, tab, q: "", page: 1 };
}

/** Reset filters: every filter and the search to their defaults; tab, sort and page size stay. */
export function resetFilters(state: AgreementsUrlState): AgreementsUrlState {
  const d = DEFAULT_AGREEMENTS_QUERY;
  return {
    ...state,
    relationship: d.relationship,
    status: d.status,
    stage: d.stage,
    bu: [],
    q: "",
    page: 1,
    kind: null,
    upload: false,
  };
}

/** The filter parameters a card's drill may set. Anything else in a drill is ignored. */
const DRILL_KEYS = ["relationship", "status", "stage", "bu", "q"] as const;

/**
 * A card click: reset every filter, open the Clients tab, then apply the card's
 * drill, validated through the same URL reader (the drill is untyped strings
 * from the server). The list then has exactly the card's number of clients.
 */
export function applyCardDrill(state: AgreementsUrlState, drill: Card["drill"] | null | undefined): AgreementsUrlState {
  const base: AgreementsUrlState = { ...resetFilters(state), tab: "clients" };
  const sp = writeAgreementsUrl(base);
  for (const key of DRILL_KEYS) {
    const value = drill?.[key];
    if (value === undefined || value === null) continue;
    sp.delete(key);
    (Array.isArray(value) ? value : [value]).forEach((v) => sp.append(key, String(v)));
  }
  return { ...readAgreementsUrl(sp), clientId: state.clientId };
}

// --- what the requests ask for ------------------------------------------------------------------

/**
 * The workspace query. The search and the page belong to the open tab, so on
 * Documents and Activity the workspace (cards, standard panels, the Clients
 * count) is asked for without them and stays the same request.
 */
export function workspaceQueryOf(s: AgreementsUrlState): WorkspaceQuery {
  const clients = s.tab === "clients";
  return {
    relationship: s.relationship,
    status: s.status,
    stage: s.stage,
    bu: s.bu,
    q: clients ? s.q : "",
    sort: s.sort,
    page: clients ? s.page : 1,
    page_size: s.page_size,
  };
}

export interface ListQuery {
  q: string;
  page: number;
  page_size: AgreementsPageSize;
}

/** The Documents or Activity list query (the open tab's search and page). */
export function listQueryOf(s: AgreementsUrlState): ListQuery {
  return { q: s.q.trim(), page: s.page, page_size: s.page_size };
}

// --- chips ---------------------------------------------------------------------------------------

export interface AgreementChip {
  key: string;
  text: string;
  /** The view without this filter. */
  next: AgreementsUrlState;
}

/** Every active filter as a removable chip, in the prototype's order. */
export function buildChips(state: AgreementsUrlState): AgreementChip[] {
  const chips: AgreementChip[] = [];
  if (state.relationship !== "all") {
    chips.push({
      key: "relationship",
      text: RELATIONSHIP_OPTIONS.find((o) => o.value === state.relationship)?.label ?? state.relationship,
      next: withFilters(state, { relationship: "all" }),
    });
  }
  if (state.status !== "any") {
    chips.push({
      key: "status",
      text: STATUS_OPTIONS.find((o) => o.value === state.status)?.label ?? state.status,
      next: withFilters(state, { status: "any" }),
    });
  }
  if (state.stage !== "any") {
    chips.push({ key: "stage", text: STAGE_CHIPS[state.stage], next: withFilters(state, { stage: "any" }) });
  }
  for (const bu of state.bu) {
    chips.push({
      key: `bu-${bu}`,
      text: BU_OPTIONS.find((o) => o.value === bu)?.label ?? bu,
      next: withFilters(state, { bu: state.bu.filter((b) => b !== bu) }),
    });
  }
  if (state.q.trim()) {
    chips.push({ key: "q", text: `Search: ${state.q.trim()}`, next: withFilters(state, { q: "" }) });
  }
  return chips;
}

// --- small facts about a row -----------------------------------------------------------------------

/** The kind a row's "↑ Upload client copy" starts on: the first one missing (NDA when both are). */
export function firstMissingKind(row: Pick<ClientRow, "nda" | "msa">): AgreementKind {
  if (row.nda.state === "missing") return "NDA";
  if (row.msa.state === "missing") return "MSA";
  return "NDA";
}

const BASIS_FALLBACK: Record<RelationshipBasis, string> = {
  closed_won: "Closed Won deal",
  sow_engagement: "SOW or engagement",
  closed_won_and_sow: "Closed Won deal and SOW",
  manual: "Set by hand",
  none: "No earlier work found",
};

/** The relationship basis in words: the server's text, or the basis name when an older server sends none. */
export function basisText(row: Pick<AgreementsClientRow, "basis_text" | "relationship" | "relationship_basis">): string {
  if (row.basis_text?.trim()) return row.basis_text;
  if (row.relationship_basis === "manual") {
    return row.relationship === "existing" ? "Marked existing" : "Marked net new";
  }
  return BASIS_FALLBACK[row.relationship_basis] ?? "";
}

/**
 * The furthest open stage as the row shows it, or null for "No active deal".
 * The words come from the server (its stage mirror), never from a list here.
 */
export function stageLabel(row: Pick<AgreementsClientRow, "stage_text" | "furthest_open_stage" | "on_hold">): string | null {
  const text = row.stage_text?.trim();
  if (text) return text === "No active deal" ? null : text;
  if (row.furthest_open_stage > 0) return `Stage ${row.furthest_open_stage}${row.on_hold ? " (and on hold)" : ""}`;
  return row.on_hold ? "On hold" : null;
}

/** Past stage 1 (stages 2 to 6, or 1 with a deal on Hold) reads in the accent; stage 1 is quiet; Hold alone or an unknown stage warns. */
export function stageTone(
  row: Pick<AgreementsClientRow, "furthest_open_stage" | "on_hold">,
): "progress" | "neutral" | "warning" {
  if (row.furthest_open_stage >= 2 || (row.furthest_open_stage >= 1 && row.on_hold)) return "progress";
  if (row.furthest_open_stage === 1) return "neutral";
  return "warning";
}
