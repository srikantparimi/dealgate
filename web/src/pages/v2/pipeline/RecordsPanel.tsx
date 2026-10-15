// S23-PL2 · the Pipeline records (right column): tabs with counts, the
// "Views & groups" button (below `md`) and the layout toggle, the page's filter
// bar slot, the bulk bar, then the records panel — basis line, include-unmatched
// and sort, the unmapped-region note, the list / board / cards, and paging.
// The page (Pipeline.tsx) owns every piece of state; this panel only asks for
// changes through `onStateChange` and the callbacks.
import { clsx } from "clsx";
import { useEffect, useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  ClientRow,
  DealRow,
  Workspace,
  WorkspaceLayout,
  WorkspacePageSize,
  WorkspaceQuery,
  WorkspaceSort,
  WorkspaceTab,
} from "../../../api/pipelineWorkspace";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { Button } from "../../../ui-v2/primitives/button";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { BulkBar } from "./BulkBar";
import { ClientCards } from "./ClientCards";
import type { ClientRef } from "./ClientPreview";
import { ClientsTable } from "./ClientsTable";
import { DealsBoard, laneOrder } from "./DealsBoard";
import { DealsTable } from "./DealsTable";
import { plural, shortMoney } from "./format";
import { BoardSummary, Pagination, pageCount } from "./Pagination";
import { Glyph } from "./tags";
import { withFilters, type WorkspaceUrlState } from "./workspaceState";

export interface RecordsPanelProps {
  workspace: Workspace | null;
  loading: boolean;
  error: string | null;
  state: WorkspaceUrlState;
  /**
   * tab, layout, sort, page, page_size, include_unmatched_clients. `replace` marks a correction
   * the user did not ask for (a page past the end): it replaces the history entry, so Back
   * does not return to the page that had to be corrected.
   */
  onStateChange: (next: WorkspaceUrlState, opts?: { replace?: boolean }) => void;
  /** Board "Show all N in list →": the page selects that stage and switches to the list. */
  onShowStageInList: (stageId: number) => void;
  selected: ReadonlySet<string>;
  onSelectedChange: (next: Set<string>) => void;
  onOpenDeal: (deal: DealRow) => void;
  /** From the Clients list the client carries its row's facts (see ClientRef). */
  onOpenClient: (client: ClientRef) => void;
  /** Receives the deal with `watching` as the user saw it before the click: false → watch, true → stop watching. */
  onToggleWatch: (deal: DealRow) => Promise<void>;
  onWatchSelected: () => Promise<void>;
  onAddSelectedToGroup: () => void;
  /** Below `md` the sidebar is gone; "Views & groups" beside the tabs opens the views panel. */
  onOpenViewsPanel: () => void;
  /** Empty state "Reset filters →" (same as Reset all). */
  onResetFilters: () => void;
  /** Optional: the page's filter toolbar and chips, drawn between the tabs row and the bulk bar (spec §2 order). */
  filterBar?: ReactNode;
  /** Optional: ask again after a failed load ("Try again"). */
  onRetry?: () => void;
}

const SORTS: { value: WorkspaceSort; label: string }[] = [
  { value: "value", label: "Value · highest first" },
  { value: "close", label: "Close date · soonest" },
  { value: "activity", label: "Activity · oldest first" },
  { value: "name", label: "Name · A–Z" },
];

function isDealRow(row: DealRow | ClientRow): row is DealRow {
  return "title" in row;
}

/** Whether the data on hand answers the view asked for (the previous answer stays while the next loads). */
function dataFits(ws: Workspace, q: WorkspaceQuery): boolean {
  const boardData = ws.rows_by_stage !== null && ws.rows_by_stage !== undefined;
  if (q.tab === "deals" && q.layout === "board") return boardData;
  if (boardData) return false;
  const first = ws.rows[0];
  if (!first) return true;
  return q.tab === "deals" ? isDealRow(first) : !isDealRow(first);
}

function withQuery(state: WorkspaceUrlState, patch: Partial<WorkspaceQuery>): WorkspaceUrlState {
  return { ...state, query: { ...state.query, ...patch } };
}

export function RecordsPanel(props: RecordsPanelProps) {
  const { workspace, loading, error, state, onStateChange, selected } = props;
  const q = state.query;
  const tab = q.tab;
  const sortId = useId();
  const unmatchedId = useId();

  // The star shows the user's click at once; the next answer from the API replaces it.
  const [watchOverride, setWatchOverride] = useState<Record<string, boolean>>({});
  const [watchBusy, setWatchBusy] = useState<Record<string, boolean>>({});
  useEffect(() => setWatchOverride({}), [workspace]);
  const isWatching = (deal: DealRow) => watchOverride[deal.id] ?? deal.watching;
  const isWatchBusy = (deal: DealRow) => Boolean(watchBusy[deal.id]);
  const toggleWatch = async (deal: DealRow) => {
    const current = isWatching(deal);
    setWatchOverride((o) => ({ ...o, [deal.id]: !current }));
    setWatchBusy((b) => ({ ...b, [deal.id]: true }));
    try {
      await props.onToggleWatch({ ...deal, watching: current });
    } catch {
      setWatchOverride((o) => ({ ...o, [deal.id]: current }));
    } finally {
      setWatchBusy((b) => {
        const next = { ...b };
        delete next[deal.id];
        return next;
      });
    }
  };

  const fits = workspace !== null && dataFits(workspace, q);
  const totalRows = fits ? workspace.page.total_rows : 0;
  const rowCount = fits ? workspace.rows.length : 0;
  const isBoard = tab === "deals" && q.layout === "board";

  // A page past the end (an old link, or rows that went away) moves to the last page, in
  // place of the empty page in the history.
  const lastPage = pageCount(totalRows, q.page_size);
  const pastEnd = fits && !isBoard && rowCount === 0 && totalRows > 0 && q.page > lastPage;
  useEffect(() => {
    if (pastEnd) onStateChange(withQuery(state, { page: lastPage }), { replace: true });
    // Only when the answer says the page is past the end.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pastEnd, lastPage]);

  const setTab = (next: WorkspaceTab) => {
    if (next !== tab) onStateChange(withQuery(state, { tab: next, page: 1 }));
  };
  const setLayout = (next: WorkspaceLayout) => {
    if (next !== q.layout) onStateChange(withQuery(state, { layout: next, page: 1 }));
  };
  const setSort = (sort: WorkspaceSort) => onStateChange(withQuery(state, { sort, page: 1 }));
  const setPage = (page: number) => onStateChange(withQuery(state, { page }));
  const setPageSize = (size: WorkspacePageSize) => onStateChange(withQuery(state, { page_size: size, page: 1 }));
  const setIncludeUnmatched = (on: boolean) => onStateChange(withFilters(state, { include_unmatched_clients: on }));

  const noun = tab === "deals" ? "opportunities" : "clients";

  let body: ReactNode;
  if (error) {
    body = (
      <ErrorState
        className="m-4"
        title="The records could not load."
        description={error}
        retryLabel="Try again"
        onRetry={props.onRetry}
      />
    );
  } else if (!fits || (loading && rowCount === 0 && !isBoard)) {
    body = (
      <p role="status" className="px-4 py-8 text-center text-body text-text-secondary">
        {`Loading ${noun}…`}
      </p>
    );
  } else if (isBoard) {
    body = (
      <DealsBoard
        lanes={workspace.rows_by_stage ?? {}}
        stages={workspace.stages}
        today={workspace.today}
        isWatching={isWatching}
        isWatchBusy={isWatchBusy}
        onToggleWatch={(d) => void toggleWatch(d)}
        onOpenDeal={props.onOpenDeal}
        onShowStageInList={props.onShowStageInList}
      />
    );
  } else if (rowCount === 0 && totalRows === 0 && !(tab === "clients" && q.layout === "board")) {
    body = (
      <EmptyState
        className="m-4"
        title="No records match this view."
        description="Remove a filter, change status, or reset the view."
        action={
          <button
            type="button"
            onClick={props.onResetFilters}
            className="rounded-control text-body font-semibold text-primary hover:underline focus-visible:outline-focus"
          >
            Reset filters
            <Glyph>→</Glyph>
          </button>
        }
      />
    );
  } else if (tab === "deals") {
    body = (
      <DealsTable
        rows={workspace.rows as DealRow[]}
        today={workspace.today}
        selected={selected}
        onSelectedChange={props.onSelectedChange}
        isWatching={isWatching}
        isWatchBusy={isWatchBusy}
        onToggleWatch={(d) => void toggleWatch(d)}
        onOpenDeal={props.onOpenDeal}
        onOpenClient={props.onOpenClient}
      />
    );
  } else if (q.layout === "board") {
    body = <ClientCards rows={workspace.rows as ClientRow[]} onOpenClient={props.onOpenClient} />;
  } else {
    body = <ClientsTable rows={workspace.rows as ClientRow[]} today={workspace.today} onOpenClient={props.onOpenClient} />;
  }

  const counts = workspace?.tab_counts;
  return (
    <section aria-label="Pipeline records" aria-busy={loading} className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Records" className="flex w-full items-end gap-6 border-b border-border md:w-auto">
          <TabButton pressed={tab === "deals"} onClick={() => setTab("deals")} label="Opportunities" count={counts?.deals} />
          <TabButton pressed={tab === "clients"} onClick={() => setTab("clients")} label="Clients" count={counts?.clients} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" className="md:hidden" onClick={props.onOpenViewsPanel}>
            Views &amp; groups
          </Button>
          <div role="group" aria-label="Layout" className="inline-flex rounded-control border border-border bg-surface p-1">
            <LayoutButton pressed={q.layout === "list"} onClick={() => setLayout("list")} glyph="☷" label="List" />
            <LayoutButton
              pressed={q.layout === "board"}
              onClick={() => setLayout("board")}
              glyph="▦"
              label={tab === "clients" ? "Cards" : "Board"}
            />
          </div>
        </div>
      </div>

      {props.filterBar}

      {selected.size > 0 ? (
        <BulkBar
          count={selected.size}
          onWatchSelected={props.onWatchSelected}
          onAddToGroup={props.onAddSelectedToGroup}
          onClear={() => props.onSelectedChange(new Set())}
        />
      ) : null}

      <div className="min-w-0 overflow-hidden rounded-panel border border-border bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <p className="text-secondary text-text-secondary">{fits && !error ? basisLine(workspace, tab) : null}</p>
          <div className="flex flex-wrap items-center gap-3">
            {tab === "clients" ? (
              <span className="flex items-center gap-2">
                <Checkbox
                  id={unmatchedId}
                  checked={q.include_unmatched_clients}
                  onCheckedChange={(v) => setIncludeUnmatched(v === true)}
                />
                <label htmlFor={unmatchedId} className="text-secondary text-text-secondary">
                  Include clients without matching deals
                </label>
              </span>
            ) : null}
            <label htmlFor={sortId} className="sr-only">
              Sort records
            </label>
            <select
              id={sortId}
              value={q.sort}
              onChange={(e) => setSort(e.target.value as WorkspaceSort)}
              className="h-8 rounded-control border border-input-border bg-surface px-2 text-table text-text focus-visible:outline-focus"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {fits && !error && workspace.unmapped_regions > 0 ? <UnmappedNote count={workspace.unmapped_regions} /> : null}

        {body}

        {fits && !error && isBoard ? (
          <BoardSummary totalRows={totalRows} lanes={laneOrder(workspace.rows_by_stage ?? {}).length} />
        ) : fits && !error ? (
          <Pagination
            tab={tab}
            totalRows={totalRows}
            page={q.page}
            pageSize={q.page_size}
            onPage={setPage}
            onPageSize={setPageSize}
          />
        ) : null}
      </div>
    </section>
  );
}

function basisLine(ws: Workspace, tab: WorkspaceTab): string {
  const n = ws.page.total_rows;
  if (tab === "deals") {
    return `${n} ${plural(n, "deal", "deals")} · ${shortMoney(ws.page.total_value_usd)} · USD, unweighted · same population as the cards above`;
  }
  const d = ws.tab_counts.deals;
  return `${n} ${plural(n, "client", "clients")} · ${d} matching ${plural(d, "deal", "deals")}`;
}

function UnmappedNote({ count }: { count: number }) {
  return (
    <p className="border-b border-border bg-warning-surface px-4 py-2 text-secondary text-warning">
      {`${count} ${plural(count, "deal has", "deals have")} a HubSpot region with no business unit yet. Map it in `}
      <Link to="/settings/business-units" className="font-semibold underline focus-visible:outline-focus">
        Settings → Business units
      </Link>
      .
    </p>
  );
}

function TabButton({
  pressed,
  onClick,
  label,
  count,
}: {
  pressed: boolean;
  onClick: () => void;
  label: string;
  count: number | undefined;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={clsx(
        "-mb-px inline-flex items-center gap-2 border-b-2 px-1 pb-2 text-body transition-motion focus-visible:outline-focus",
        pressed ? "border-primary font-semibold text-text" : "border-transparent text-text-secondary hover:text-text",
      )}
    >
      {label}{" "}
      {count !== undefined ? (
        <span className="rounded-chip bg-surface-sunken px-1.5 font-mono text-secondary text-text-secondary tnum">
          {count}
        </span>
      ) : null}
    </button>
  );
}

function LayoutButton({
  pressed,
  onClick,
  glyph,
  label,
}: {
  pressed: boolean;
  onClick: () => void;
  glyph: string;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={clsx(
        "inline-flex h-8 items-center gap-1 rounded-control px-3 text-secondary transition-motion focus-visible:outline-focus",
        pressed ? "bg-primary-subtle font-semibold text-primaryText" : "text-text-secondary hover:text-text",
      )}
    >
      <Glyph before>{glyph}</Glyph>
      {label}
    </button>
  );
}
