// S23-PL2 F7 · every active filter as a visible, removable chip, then
// "Reset all" and "Save view ＋". A chip's "×" removes that filter only,
// through the page's transitions (a stage chip follows the restore rule, F5).
import type {
  StageCount,
  TrackingGroupSummary,
  WorkspaceOptions,
  WorkspaceStatus,
} from "../../../api/pipelineWorkspace";
import { DATE_FIELD_LABELS } from "./DateDialog";
import { calendarDate } from "./format";
import { setStages, withFilters, type WorkspaceUrlState } from "./workspaceState";

const STATUS_CHIPS: Record<WorkspaceStatus, string> = {
  open: "Status: Open (includes on hold)",
  all: "All statuses",
  won: "Closed won",
  lost: "Closed lost",
  hold: "On hold only",
};

const DATE_CHIPS: Record<string, string> = {
  passed: "before today",
  next7: "next 7 days",
  next30: "next 30 days",
  next90: "next 90 days",
  last7: "last 7 days",
  last30: "last 30 days",
  last90: "last 90 days",
  month: "this month",
  quarter: "this quarter",
};

const ATTENTION_CHIPS: Record<string, string> = {
  overdue: "overdue next action",
  past_close: "close date passed",
  no_owner: "no deal owner",
  inactive: "14d+ inactive",
  pending_approval: "pending approval",
  any: "any flag",
};

const MISSING_CHIPS: Record<string, string> = {
  owner: "deal owner",
  close: "close date",
  activity: "activity date",
  next_action: "next action",
  nda: "NDA",
  msa: "MSA",
  agreements: "NDA or MSA",
};

export interface Chip {
  key: string;
  text: string;
  /** The view without this filter; null for the status chip "All statuses" (nothing to remove). */
  next: WorkspaceUrlState | null;
}

export interface ChipContext {
  options: WorkspaceOptions | null;
  stages: StageCount[] | null;
  groups: TrackingGroupSummary[] | null;
  today: string | null;
}

function ownerName(id: string, list: { id: string; name: string }[] | undefined): string {
  return list?.find((o) => o.id === id)?.name ?? "Unavailable owner";
}

/** The chips of a view, in the prototype's order. */
export function buildChips(state: WorkspaceUrlState, ctx: ChipContext): Chip[] {
  const q = state.query;
  const chips: Chip[] = [
    {
      key: "status",
      text: STATUS_CHIPS[q.status],
      next: q.status === "all" ? null : withFilters(state, { status: "all" }),
    },
  ];
  for (const id of q.stage) {
    chips.push({
      key: `stage-${id}`,
      text: ctx.stages?.find((s) => s.stage_id === id)?.full_label ?? `Stage ${id}`,
      next: setStages(state, q.stage.filter((s) => s !== id)),
    });
  }
  for (const id of q.owner) {
    const text =
      id === "none"
        ? "Deal owner: No deal owner"
        : id === "former"
          ? "Deal owner: Former HubSpot user"
          : `Deal owner: ${ownerName(id, ctx.options?.deal_owners)}`;
    chips.push({ key: `owner-${id}`, text, next: withFilters(state, { owner: q.owner.filter((o) => o !== id) }) });
  }
  if (q.mine) chips.push({ key: "mine", text: "My opportunities", next: withFilters(state, { mine: false }) });
  for (const id of q.account_owner) {
    const text = id === "none" ? "Account owner: Not assigned" : `Account owner: ${ownerName(id, ctx.options?.account_owners)}`;
    chips.push({
      key: `account-${id}`,
      text,
      next: withFilters(state, { account_owner: q.account_owner.filter((o) => o !== id) }),
    });
  }
  for (const bu of q.bu) {
    const regions = ctx.options?.business_units.find((b) => b.business_unit === bu)?.regions ?? [];
    const text = bu === "unmapped" ? "BU: Unmapped region" : regions.length ? `BU: ${bu} (${regions.join(", ")})` : `BU: ${bu}`;
    chips.push({ key: `bu-${bu}`, text, next: withFilters(state, { bu: q.bu.filter((b) => b !== bu) }) });
  }
  if (q.q.trim()) chips.push({ key: "q", text: `Search: ${q.q.trim()}`, next: withFilters(state, { q: "" }) });
  if (q.date_preset !== "any") {
    const today = ctx.today ?? undefined;
    const period =
      q.date_preset === "custom"
        ? `${q.date_from ? calendarDate(q.date_from, today) : "…"} to ${q.date_to ? calendarDate(q.date_to, today) : "…"}`
        : DATE_CHIPS[q.date_preset];
    chips.push({
      key: "date",
      text: `${DATE_FIELD_LABELS[q.date_field]}: ${period}`,
      next: withFilters(state, { date_preset: "any", date_from: null, date_to: null }),
    });
  }
  if (q.sow) {
    const label = q.sow === "pending" ? "pending approval" : (ctx.options?.sow_states.find((s) => s.value === q.sow)?.label ?? q.sow);
    chips.push({ key: "sow", text: `SOW: ${label}`, next: withFilters(state, { sow: null }) });
  }
  if (q.attention) {
    chips.push({
      key: "attention",
      text: `Attention: ${ATTENTION_CHIPS[q.attention]}`,
      next: withFilters(state, { attention: null }),
    });
  }
  if (q.missing) {
    chips.push({ key: "missing", text: `Missing: ${MISSING_CHIPS[q.missing]}`, next: withFilters(state, { missing: null }) });
  }
  if (q.group) {
    const name = ctx.groups ? (ctx.groups.find((g) => g.id === q.group)?.name ?? "Unavailable group") : "…";
    chips.push({ key: "group", text: `Group: ${name}`, next: withFilters(state, { group: null }) });
  }
  if (q.watching) chips.push({ key: "watching", text: "Watching", next: withFilters(state, { watching: false }) });
  if (q.include_unmatched_clients) {
    chips.push({
      key: "unmatched",
      text: "Including clients without matching deals",
      next: withFilters(state, { include_unmatched_clients: false }),
    });
  }
  return chips;
}

export interface FilterChipsProps extends ChipContext {
  state: WorkspaceUrlState;
  onChange: (next: WorkspaceUrlState) => void;
  onReset: () => void;
  onSaveView: () => void;
}

// A long search chip wraps instead of widening the page (no horizontal scroll at 375 px).
const CHIP_CLASS =
  "inline-flex min-h-7 max-w-full items-center gap-1 rounded-chip border border-transparent bg-primary-subtle px-2 py-0.5 text-left text-secondary text-primary-text [overflow-wrap:anywhere]";

export function FilterChips({ state, onChange, onReset, onSaveView, ...ctx }: FilterChipsProps) {
  const chips = buildChips(state, ctx);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip) =>
        chip.next ? (
          <button
            key={chip.key}
            type="button"
            aria-label={`Remove ${chip.text}`}
            onClick={() => onChange(chip.next as WorkspaceUrlState)}
            className={`${CHIP_CLASS} hover:border-primary focus-visible:outline-focus`}
          >
            {chip.text}
            <span aria-hidden>×</span>
          </button>
        ) : (
          <span key={chip.key} className={CHIP_CLASS}>
            {chip.text}
          </span>
        ),
      )}
      <button
        type="button"
        onClick={onReset}
        className="h-7 rounded-control px-2 text-secondary text-text-secondary hover:text-text focus-visible:outline-focus"
      >
        Reset all
      </button>
      <button
        type="button"
        onClick={onSaveView}
        className="ml-auto h-7 rounded-control px-2 text-secondary font-medium text-primary-text hover:bg-primary-subtle focus-visible:outline-focus"
      >
        Save view ＋
      </button>
    </div>
  );
}
