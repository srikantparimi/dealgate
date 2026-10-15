/**
 * S23-PL2 · the Pipeline page (directive F1–F20), built on one request:
 * GET /pipeline/workspace (B1). Structure, behaviour and copy follow the
 * approved prototype; the app's own kit and tokens draw it, so the app's light
 * and dark themes apply (F1).
 *
 * The URL query string holds every filter (F2): the page reads its state from
 * the URL and changes it only through the transitions in workspaceState.ts, so
 * a link or the back button restores the view and a saved view stores the same
 * shape. This file owns the page state; the records (list, board, cards,
 * previews) are drawn by the components in ./pipeline/RecordsPanel and the
 * previews, through the props they declare.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAppConfig } from "../../api/appConfig";
import { getMe, type MeResponse } from "../../api/client";
import {
  downloadWorkspaceCsv,
  listWorkspaceGroups,
  listWorkspaceViews,
  unwatchDeal,
  watchDeal,
  type ClientRow,
  type DealRow,
  type SavedWorkspaceView,
  type TrackingGroupSummary,
  type Workspace,
} from "../../api/pipelineWorkspace";
import { useToast } from "../../ui-v2/primitives/toaster";
import { BusinessUnitDialog } from "./pipeline/BusinessUnitDialog";
import { ClientPreview, type ClientRef } from "./pipeline/ClientPreview";
import { CollectionsSidebar, DeleteViewDialog, ViewsPanel } from "./pipeline/CollectionsSidebar";
import { DateDialog } from "./pipeline/DateDialog";
import { DealPreview } from "./pipeline/DealPreview";
import { FilterChips } from "./pipeline/FilterChips";
import { FilterToolbar } from "./pipeline/FilterToolbar";
import { FreshnessLine } from "./pipeline/FreshnessLine";
import { GroupDialog } from "./pipeline/GroupDialog";
import { MetricCards } from "./pipeline/MetricCards";
import { MoreFiltersDialog } from "./pipeline/MoreFiltersDialog";
import { OwnerFilterDialog } from "./pipeline/OwnerFilterDialog";
import { PipelineFooter } from "./pipeline/PipelineFooter";
import { PipelineHeader, canExport } from "./pipeline/PipelineHeader";
import { RecordsPanel } from "./pipeline/RecordsPanel";
import { SaveViewDialog } from "./pipeline/SaveViewDialog";
import { StageNavigator } from "./pipeline/StageNavigator";
import { SyncHealthPanel } from "./pipeline/SyncHealthPanel";
import { useWorkspace } from "./pipeline/useWorkspace";
import {
  FILTER_KEYS,
  activeFocus,
  applyDrill,
  applyFocus,
  readWorkspaceUrl,
  resetFilters,
  setStages,
  setStatus,
  stateFromView,
  toggleStage,
  withFilters,
  writeWorkspaceUrl,
  type FocusKey,
  type WorkspaceUrlState,
} from "./pipeline/workspaceState";

type ShellDialog =
  | { kind: "sync" }
  | { kind: "owner" }
  | { kind: "bu" }
  | { kind: "date" }
  | { kind: "more" }
  | { kind: "saveView" }
  | { kind: "group"; mode: "create" | "add" }
  | { kind: "views" }
  | { kind: "deleteView"; view: SavedWorkspaceView };

type Preview = { kind: "deal"; deal: DealRow } | { kind: "client"; client: ClientRef } | null;

/** Watch requests in flight at once for "Watch selected". */
const WATCH_BATCH = 8;
const SEARCH_MAX = 120;

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/** The deal as the latest answer has it (list rows or board lanes), so an open preview shows fresh data. */
function findDeal(ws: Workspace | null, id: string): DealRow | null {
  if (!ws) return null;
  const rows = ws.rows as Array<DealRow | ClientRow>;
  const inRows = rows.find((row): row is DealRow => "title" in row && row.id === id);
  if (inRows) return inRows;
  for (const lane of Object.values(ws.rows_by_stage ?? {})) {
    const found = lane.deals.find((deal) => deal.id === id);
    if (found) return found;
  }
  return null;
}

export function PipelinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlKey = searchParams.toString();
  const state = useMemo(() => readWorkspaceUrl(new URLSearchParams(urlKey)), [urlKey]);
  const ws = useWorkspace(state.query);
  const { data, refetch } = ws;
  const { toast } = useToast();
  const { hubspotPortalId } = useAppConfig();

  const commit = useCallback(
    (next: WorkspaceUrlState, opts: { replace?: boolean } = {}) => {
      setSearchParams(writeWorkspaceUrl(next), { replace: opts.replace ?? false });
    },
    [setSearchParams],
  );

  // --- who is looking (roles for export and the sync action; next-action assignee)
  const [me, setMe] = useState<MeResponse | null>(null);
  useEffect(() => {
    let live = true;
    getMe()
      .then((who) => {
        if (live) setMe(who);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  const isAdmin = Boolean(me?.groups.includes("SystemAdmin"));

  // --- saved views and tracking groups (the caller's own)
  const [views, setViews] = useState<SavedWorkspaceView[] | null>(null);
  const [groups, setGroups] = useState<TrackingGroupSummary[] | null>(null);
  const [viewsError, setViewsError] = useState<string | null>(null);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const reloadViews = useCallback(() => {
    listWorkspaceViews()
      .then((list) => {
        setViews(list);
        setViewsError(null);
      })
      .catch((err: unknown) => setViewsError(`Your saved views could not load. ${errorText(err, "")}`.trim()));
  }, []);
  const reloadGroups = useCallback(() => {
    listWorkspaceGroups()
      .then((list) => {
        setGroups(list);
        setGroupsError(null);
      })
      .catch((err: unknown) => setGroupsError(`Your tracking groups could not load. ${errorText(err, "")}`.trim()));
  }, []);
  useEffect(() => {
    reloadViews();
    reloadGroups();
  }, [reloadViews, reloadGroups]);

  // --- bulk selection: cleared when a filter, the tab or the layout changes; kept across pages and sorts
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const scopeKey = JSON.stringify([state.query.tab, state.query.layout, ...FILTER_KEYS.map((key) => state.query[key])]);
  useEffect(() => {
    setSelected((current) => (current.size ? new Set() : current));
  }, [scopeKey]);

  // --- dialogs: one at a time; focus returns to the control that opened the first one (F17)
  const [dialog, setDialog] = useState<ShellDialog | null>(null);
  const dialogOpen = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const openDialog = useCallback((next: ShellDialog) => {
    if (!dialogOpen.current) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    dialogOpen.current = true;
    setDialog(next);
  }, []);
  const closeDialog = useCallback(() => {
    dialogOpen.current = false;
    setDialog(null);
  }, []);
  const onDrawerChange = useCallback(
    (open: boolean) => {
      if (!open) closeDialog();
    },
    [closeDialog],
  );
  const returnFocus = useCallback((event: Event) => {
    event.preventDefault();
    // Moving from one dialog to the next keeps focus in the next one.
    if (!dialogOpen.current && opener.current?.isConnected) opener.current.focus();
  }, []);

  // --- previews (drawn by the records lane's DealPreview / ClientPreview)
  const [preview, setPreview] = useState<Preview>(null);
  const previewDeal = preview?.kind === "deal" ? (findDeal(data, preview.deal.id) ?? preview.deal) : null;
  const openDeal = useCallback((deal: DealRow) => setPreview({ kind: "deal", deal }), []);
  // From the Clients list the client carries its row's facts (owner, agreements) for the preview.
  const openClient = useCallback((client: ClientRef) => setPreview({ kind: "client", client }), []);

  // --- actions
  const onReset = useCallback(() => {
    commit(resetFilters(state));
    setSelected(new Set());
  }, [commit, state]);

  const onFocusView = (key: FocusKey) => {
    commit(applyFocus(state, key));
    if (dialog) closeDialog();
  };

  const onOpenView = (view: SavedWorkspaceView) => {
    commit(stateFromView(view, state));
    setSelected(new Set());
    if (dialog) closeDialog();
    toast({ title: `Opened saved view: ${view.name}` });
  };

  const onToggleGroup = (groupId: string) => {
    commit(withFilters(state, { group: state.query.group === groupId ? null : groupId }));
    if (dialog) closeDialog();
  };

  const onToggleWatch = useCallback(
    async (deal: DealRow) => {
      try {
        if (deal.watching) await unwatchDeal(deal.id);
        else await watchDeal(deal.id);
        setPreview((current) =>
          current?.kind === "deal" && current.deal.id === deal.id
            ? { kind: "deal", deal: { ...current.deal, watching: !deal.watching } }
            : current,
        );
      } catch (err) {
        toast({ title: "Watching could not change.", description: errorText(err, "Try again."), variant: "destructive" });
        // The star and the preview show the click at once; a rejection tells them to undo it.
        throw err;
      } finally {
        refetch();
      }
    },
    [refetch, toast],
  );

  const onWatchSelected = useCallback(async () => {
    const ids = [...selected];
    if (!ids.length) return;
    try {
      for (let i = 0; i < ids.length; i += WATCH_BATCH) {
        await Promise.all(ids.slice(i, i + WATCH_BATCH).map((id) => watchDeal(id)));
      }
      setSelected(new Set());
      toast({ title: "Selected opportunities added to Watching." });
    } catch (err) {
      toast({ title: "Watching could not change.", description: errorText(err, "Try again."), variant: "destructive" });
    } finally {
      refetch();
    }
  }, [refetch, selected, toast]);

  const [exporting, setExporting] = useState(false);
  const onExport = useCallback(async () => {
    setExporting(true);
    try {
      const filename = await downloadWorkspaceCsv(state.query);
      toast({ title: `Downloaded ${filename}.` });
    } catch (err) {
      toast({
        title: "The export could not download.",
        description: errorText(err, "Try again."),
        variant: "destructive",
      });
    } finally {
      setExporting(false);
    }
  }, [state.query, toast]);

  const showClientDeals = useCallback(
    (clientName: string) => {
      const reset = resetFilters(state);
      commit({
        query: { ...reset.query, status: "all", q: clientName.slice(0, SEARCH_MAX), tab: "deals" },
        statusBefore: null,
      });
      setPreview(null);
    },
    [commit, state],
  );

  const showStageInList = useCallback(
    (stageId: number) => {
      const next = setStages(state, [stageId]);
      commit({ ...next, query: { ...next.query, layout: "list" } });
    },
    [commit, state],
  );

  const collections = {
    focus: data?.focus ?? null,
    activeFocus: activeFocus(state.query),
    views,
    groups,
    activeGroup: state.query.group,
    loadError: viewsError ?? groupsError,
    onFocus: onFocusView,
    onOpenView,
    onDeleteView: (view: SavedWorkspaceView) => openDialog({ kind: "deleteView", view }),
    onToggleGroup,
    onSaveView: () => openDialog({ kind: "saveView" }),
    onCreateGroup: () => openDialog({ kind: "group", mode: "create" }),
    onRetry: () => {
      reloadViews();
      reloadGroups();
    },
  };

  const ownerKind = state.query.tab === "clients" ? "account" : "deal";

  return (
    <div className="flex flex-col gap-6">
      <PipelineHeader
        showExport={canExport(me?.groups)}
        exporting={exporting}
        onExport={() => void onExport()}
        hubspotPortalId={hubspotPortalId}
      />
      {data ? <FreshnessLine freshness={data.freshness} onInspect={() => openDialog({ kind: "sync" })} /> : null}
      {/* A failed load is reported once, in the records panel (with Retry). */}
      {!data && !ws.error ? (
        <p role="status" className="text-body text-text-secondary">
          Loading the Pipeline…
        </p>
      ) : null}
      {data && !ws.error ? (
        <>
          <MetricCards metrics={data.metrics} onDrill={(drill) => commit(applyDrill(state, drill))} />
          <StageNavigator
            stages={data.stages}
            selected={state.query.stage}
            onToggle={(stageId) => commit(toggleStage(state, stageId))}
          />
        </>
      ) : null}
      <div className="grid gap-6 md:grid-cols-[135px_minmax(0,1fr)] xl:grid-cols-[157px_minmax(0,1fr)] 2xl:grid-cols-[175px_minmax(0,1fr)]">
        <CollectionsSidebar className="hidden md:flex" {...collections} />
        <RecordsPanel
          workspace={data}
          loading={ws.loading}
          error={ws.error}
          state={state}
          onStateChange={commit}
          onShowStageInList={showStageInList}
          selected={selected}
          onSelectedChange={setSelected}
          onOpenDeal={openDeal}
          onOpenClient={openClient}
          onToggleWatch={onToggleWatch}
          onWatchSelected={onWatchSelected}
          onAddSelectedToGroup={() => openDialog({ kind: "group", mode: "add" })}
          onOpenViewsPanel={() => openDialog({ kind: "views" })}
          onResetFilters={onReset}
          onRetry={refetch}
          filterBar={
            <>
              <FilterToolbar
                state={state}
                ready={Boolean(data)}
                onSearch={(q) => commit(withFilters(state, { q }), { replace: state.query.q.trim() !== "" })}
                onStatus={(status) => commit(setStatus(state, status))}
                onOpenOwner={() => openDialog({ kind: "owner" })}
                onOpenBusinessUnit={() => openDialog({ kind: "bu" })}
                onOpenDate={() => openDialog({ kind: "date" })}
                onOpenMore={() => openDialog({ kind: "more" })}
              />
              <FilterChips
                state={state}
                options={data?.options ?? null}
                stages={data?.stages ?? null}
                groups={groups}
                today={data?.today ?? null}
                onChange={(next) => commit(next)}
                onReset={onReset}
                onSaveView={() => openDialog({ kind: "saveView" })}
              />
            </>
          }
        />
      </div>
      <PipelineFooter today={data?.today ?? null} />

      {data ? (
        <>
          <SyncHealthPanel
            open={dialog?.kind === "sync"}
            onOpenChange={onDrawerChange}
            onCloseAutoFocus={returnFocus}
            freshness={data.freshness}
            canRunSync={isAdmin && Boolean(data.freshness.recovery?.available)}
            onSynced={refetch}
          />
          <OwnerFilterDialog
            open={dialog?.kind === "owner"}
            onOpenChange={onDrawerChange}
            onCloseAutoFocus={returnFocus}
            kind={ownerKind}
            owners={ownerKind === "deal" ? data.options.deal_owners : data.options.account_owners}
            selected={ownerKind === "deal" ? state.query.owner : state.query.account_owner}
            onApply={(ids) => {
              commit(withFilters(state, ownerKind === "deal" ? { owner: ids } : { account_owner: ids }));
              closeDialog();
            }}
          />
          <BusinessUnitDialog
            open={dialog?.kind === "bu"}
            onOpenChange={onDrawerChange}
            onCloseAutoFocus={returnFocus}
            businessUnits={data.options.business_units}
            unmappedDeals={data.unmapped_regions}
            selected={state.query.bu}
            onApply={(bu) => {
              commit(withFilters(state, { bu }));
              closeDialog();
            }}
          />
          <DateDialog
            open={dialog?.kind === "date"}
            onOpenChange={onDrawerChange}
            onCloseAutoFocus={returnFocus}
            today={data.today}
            value={state.query}
            onApply={(patch) => {
              commit(withFilters(state, patch));
              closeDialog();
            }}
          />
          <MoreFiltersDialog
            open={dialog?.kind === "more"}
            onOpenChange={onDrawerChange}
            onCloseAutoFocus={returnFocus}
            sowStates={data.options.sow_states}
            groups={groups ?? []}
            watchingCount={data.focus.watching}
            value={state.query}
            onApply={(patch) => {
              commit(withFilters(state, patch));
              closeDialog();
            }}
          />
          <DealPreview
            deal={previewDeal}
            open={preview?.kind === "deal"}
            onOpenChange={(open) => {
              if (!open) setPreview(null);
            }}
            today={data.today}
            hubspotPortalId={hubspotPortalId}
            assigneeId={me?.id ?? null}
            onOpenClient={openClient}
            onToggleWatch={onToggleWatch}
            onChanged={refetch}
          />
          <ClientPreview
            client={preview?.kind === "client" ? preview.client : null}
            open={preview?.kind === "client"}
            onOpenChange={(open) => {
              if (!open) setPreview(null);
            }}
            state={state}
            today={data.today}
            onOpenDeal={openDeal}
            onShowClientDeals={showClientDeals}
          />
        </>
      ) : null}
      <SaveViewDialog
        open={dialog?.kind === "saveView"}
        onOpenChange={onDrawerChange}
        onCloseAutoFocus={returnFocus}
        state={state}
        existingNames={(views ?? []).map((view) => view.name)}
        onSaved={(view) => {
          setViews((current) => [...(current ?? []), view]);
          closeDialog();
          toast({ title: `Saved view “${view.name}”.` });
          reloadViews();
        }}
      />
      <GroupDialog
        open={dialog?.kind === "group"}
        onOpenChange={onDrawerChange}
        onCloseAutoFocus={returnFocus}
        mode={dialog?.kind === "group" ? dialog.mode : "create"}
        groups={groups ?? []}
        selectedIds={[...selected]}
        onCreated={(group) => {
          closeDialog();
          toast({ title: `Created tracking group “${group.name}”.` });
          reloadGroups();
          refetch();
        }}
        onAdded={(group) => {
          closeDialog();
          toast({ title: `Added selected opportunities to “${group.name}”.` });
          reloadGroups();
          refetch();
        }}
      />
      <ViewsPanel
        open={dialog?.kind === "views"}
        onOpenChange={onDrawerChange}
        onCloseAutoFocus={returnFocus}
        {...collections}
      />
      <DeleteViewDialog
        open={dialog?.kind === "deleteView"}
        onOpenChange={onDrawerChange}
        onCloseAutoFocus={returnFocus}
        view={dialog?.kind === "deleteView" ? dialog.view : null}
        onDeleted={(view) => {
          setViews((current) => current?.filter((v) => v.id !== view.id) ?? current);
          closeDialog();
          toast({ title: `Deleted saved view “${view.name}”.` });
          reloadViews();
        }}
      />
    </div>
  );
}
