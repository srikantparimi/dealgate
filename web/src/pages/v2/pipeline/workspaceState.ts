// S23-PL2 F2/F5/F6 · the Pipeline's view state. Every filter lives in the URL
// query string, so a link or the back button restores the view; a saved view
// stores the same shape. The transitions here are the page's only way to
// change filters.
import {
  DEFAULT_WORKSPACE_QUERY,
  WORKSPACE_PAGE_SIZES,
  workspaceParams,
  type AttentionFilter,
  type BusinessUnitFilter,
  type DateField,
  type DatePreset,
  type MetricDrill,
  type MissingFilter,
  type SavedWorkspaceView,
  type WorkspaceLayout,
  type WorkspacePageSize,
  type WorkspaceQuery,
  type WorkspaceSort,
  type WorkspaceStatus,
  type WorkspaceTab,
} from "../../../api/pipelineWorkspace";

export interface WorkspaceUrlState {
  query: WorkspaceQuery;
  /** The status in force before the first stage was selected (F5); restored when the last stage is cleared. */
  statusBefore: WorkspaceStatus | null;
}

const TABS: WorkspaceTab[] = ["deals", "clients"];
const STATUSES: WorkspaceStatus[] = ["open", "all", "won", "lost", "hold"];
const BUS: BusinessUnitFilter[] = ["ST21", "IT Avalon", "Retro Rabbit", "unmapped"];
const ATTENTION: AttentionFilter[] = ["overdue", "past_close", "no_owner", "inactive", "pending_approval", "any"];
const MISSING: MissingFilter[] = ["owner", "close", "activity", "next_action", "nda", "msa", "agreements"];
const DATE_FIELDS: DateField[] = ["close", "created", "activity"];
const DATE_PRESETS: DatePreset[] = [
  "any", "passed", "next7", "next30", "next90", "last7", "last30", "last90", "month", "quarter", "custom",
];
const SORTS: WorkspaceSort[] = ["value", "close", "activity", "name"];
const LAYOUTS: WorkspaceLayout[] = ["list", "board"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function pick<T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T {
  return raw !== null && (allowed as readonly string[]).includes(raw) ? (raw as T) : fallback;
}

function pickOrNull<T extends string>(raw: string | null, allowed: readonly T[]): T | null {
  return raw !== null && (allowed as readonly string[]).includes(raw) ? (raw as T) : null;
}

/** Read the view from the URL. Unknown values fall back to the defaults instead of failing. */
export function readWorkspaceUrl(sp: URLSearchParams): WorkspaceUrlState {
  const d = DEFAULT_WORKSPACE_QUERY;
  const size = Number(sp.get("page_size"));
  const page = Number(sp.get("page"));
  const dateFrom = sp.get("date_from");
  const dateTo = sp.get("date_to");
  const query: WorkspaceQuery = {
    tab: pick(sp.get("tab"), TABS, d.tab),
    status: pick(sp.get("status"), STATUSES, d.status),
    stage: [...new Set(sp.getAll("stage").map(Number).filter((n) => Number.isInteger(n) && n >= 1 && n <= 9))].sort(
      (a, b) => a - b,
    ),
    owner: [...new Set(sp.getAll("owner").filter(Boolean))],
    account_owner: [...new Set(sp.getAll("account_owner").filter(Boolean))],
    bu: [...new Set(sp.getAll("bu").filter((b): b is BusinessUnitFilter => (BUS as string[]).includes(b)))],
    q: (sp.get("q") ?? "").slice(0, 120),
    sow: sp.get("sow") || null,
    attention: pickOrNull(sp.get("attention"), ATTENTION),
    missing: pickOrNull(sp.get("missing"), MISSING),
    group: sp.get("group") || null,
    watching: sp.get("watching") === "true",
    mine: sp.get("mine") === "true",
    date_field: pick(sp.get("date_field"), DATE_FIELDS, d.date_field),
    date_preset: pick(sp.get("date_preset"), DATE_PRESETS, d.date_preset),
    date_from: dateFrom && ISO_DATE.test(dateFrom) ? dateFrom : null,
    date_to: dateTo && ISO_DATE.test(dateTo) ? dateTo : null,
    include_unmatched_clients: sp.get("include_unmatched_clients") === "true",
    sort: pick(sp.get("sort"), SORTS, d.sort),
    layout: pick(sp.get("layout"), LAYOUTS, d.layout),
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size: (WORKSPACE_PAGE_SIZES as readonly number[]).includes(size) ? (size as WorkspacePageSize) : d.page_size,
    client: null,
  };
  const before = sp.get("status_before");
  return {
    query,
    statusBefore: query.stage.length ? pickOrNull(before, STATUSES) : null,
  };
}

/** The URL for a view: the API's own parameters, plus the remembered status while stages are selected. */
export function writeWorkspaceUrl(state: WorkspaceUrlState): URLSearchParams {
  const p = workspaceParams(state.query);
  if (state.query.stage.length && state.statusBefore) p.set("status_before", state.statusBefore);
  return p;
}

/** The filter fields: everything except tab, layout, sort and paging. */
export const FILTER_KEYS = [
  "status", "stage", "owner", "account_owner", "bu", "q", "sow", "attention", "missing", "group", "watching",
  "mine", "date_field", "date_preset", "date_from", "date_to", "include_unmatched_clients",
] as const satisfies readonly (keyof WorkspaceQuery)[];

/** Change filters. Any filter change goes back to page 1. */
export function withFilters(state: WorkspaceUrlState, patch: Partial<WorkspaceQuery>): WorkspaceUrlState {
  const query = { ...state.query, ...patch, page: 1 };
  return { query, statusBefore: query.stage.length ? state.statusBefore : null };
}

/** Status select: a status change clears the stage selection (prototype L188). */
export function setStatus(state: WorkspaceUrlState, status: WorkspaceStatus): WorkspaceUrlState {
  return { query: { ...state.query, status, stage: [], page: 1 }, statusBefore: null };
}

/**
 * F5: selecting the first stage remembers the status and switches to All statuses;
 * clearing the last stage restores the remembered status (Open when none).
 */
export function setStages(state: WorkspaceUrlState, stages: number[]): WorkspaceUrlState {
  const next = [...new Set(stages)].sort((a, b) => a - b);
  const had = state.query.stage.length > 0;
  if (!had && next.length) {
    return { query: { ...state.query, stage: next, status: "all", page: 1 }, statusBefore: state.query.status };
  }
  if (had && !next.length) {
    return { query: { ...state.query, stage: [], status: state.statusBefore ?? "open", page: 1 }, statusBefore: null };
  }
  return { query: { ...state.query, stage: next, page: 1 }, statusBefore: state.statusBefore };
}

export function toggleStage(state: WorkspaceUrlState, stageId: number): WorkspaceUrlState {
  const has = state.query.stage.includes(stageId);
  return setStages(state, has ? state.query.stage.filter((s) => s !== stageId) : [...state.query.stage, stageId]);
}

/**
 * F4: a metric card adds its drill to the current filters. The stage selection is kept,
 * so the list has exactly the card's number (the prototype cleared it; logged deviation).
 * A drill that sets the status also becomes the status to restore when the last stage is
 * cleared, so removing a stage never undoes the status the card applied.
 */
export function applyDrill(state: WorkspaceUrlState, drill: MetricDrill): WorkspaceUrlState {
  const query = { ...state.query, ...drill, page: 1 } as WorkspaceQuery;
  if (!query.stage.length) return { query, statusBefore: null };
  return { query, statusBefore: drill.status ?? state.statusBefore };
}

/** Reset all: every filter to its default; tab, layout, sort and page size stay. */
export function resetFilters(state: WorkspaceUrlState): WorkspaceUrlState {
  const d = DEFAULT_WORKSPACE_QUERY;
  return {
    query: {
      ...d,
      tab: state.query.tab,
      layout: state.query.layout,
      sort: state.query.sort,
      page_size: state.query.page_size,
    },
    statusBefore: null,
  };
}

export type FocusKey = "all" | "closing" | "mine" | "attention" | "watching";

export const FOCUS_VIEWS: { key: FocusKey; label: string }[] = [
  { key: "all", label: "All open opportunities" },
  { key: "closing", label: "Closing this month" },
  { key: "mine", label: "My opportunities" },
  { key: "attention", label: "Needs attention" },
  { key: "watching", label: "Watching" },
];

const FOCUS_PRESETS: Record<FocusKey, Partial<WorkspaceQuery>> = {
  all: {},
  closing: { date_field: "close", date_preset: "month" },
  mine: { mine: true },
  attention: { attention: "any" },
  watching: { watching: true },
};

/** F6: a focus view resets every filter, then applies its preset. */
export function applyFocus(state: WorkspaceUrlState, key: FocusKey): WorkspaceUrlState {
  const reset = resetFilters(state);
  return { query: { ...reset.query, ...FOCUS_PRESETS[key] }, statusBefore: null };
}

function sameFilters(a: WorkspaceQuery, b: WorkspaceQuery): boolean {
  return FILTER_KEYS.every((k) => JSON.stringify(a[k]) === JSON.stringify(b[k]));
}

/** The focus view the current filters are exactly equal to, if any (for its highlight). */
export function activeFocus(query: WorkspaceQuery): FocusKey | null {
  for (const { key } of FOCUS_VIEWS) {
    if (sameFilters(query, { ...DEFAULT_WORKSPACE_QUERY, ...FOCUS_PRESETS[key] })) return key;
  }
  return null;
}

/** What a saved view stores: the filters, tab and layout (not sort or paging), as the prototype does. */
export function viewFromState(state: WorkspaceUrlState): Omit<SavedWorkspaceView, "id" | "name"> {
  const filters: Partial<WorkspaceQuery> & { status_before?: WorkspaceStatus } = {};
  for (const k of FILTER_KEYS) (filters as Record<string, unknown>)[k] = state.query[k];
  if (state.query.stage.length && state.statusBefore) filters.status_before = state.statusBefore;
  return { tab: state.query.tab, layout: state.query.layout, filters };
}

/** Open a saved view: its filters, tab and layout; the current sort and page size stay. */
export function stateFromView(view: SavedWorkspaceView, current: WorkspaceUrlState): WorkspaceUrlState {
  const reset = resetFilters(current);
  const stored = view.filters as Partial<WorkspaceQuery> & { status_before?: WorkspaceStatus };
  const filters: Partial<WorkspaceQuery> = {};
  for (const k of FILTER_KEYS) {
    if (k in stored) (filters as Record<string, unknown>)[k] = stored[k];
  }
  const query: WorkspaceQuery = { ...reset.query, ...filters, tab: view.tab, layout: view.layout, page: 1 };
  return {
    query,
    statusBefore: query.stage.length && stored.status_before ? stored.status_before : null,
  };
}
