// S23-PL2 F6 / F12 · focus views, saved views and tracking groups: the sidebar
// on wide screens and the "Your views & groups" panel on narrow ones (F16).
// Focus counts come from `workspace.focus` (independent of the current
// filters); views and groups are the caller's own (per user, B11).
import { Trash2 } from "lucide-react";
import { useId, useState } from "react";

import {
  deleteWorkspaceView,
  type FocusCounts,
  type SavedWorkspaceView,
  type TrackingGroupSummary,
} from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../ui-v2/primitives/dialog";
import { PipelineDrawer, type DrawerControlProps } from "./FilterToolbar";
import { FOCUS_VIEWS, type FocusKey } from "./workspaceState";

export const MINE_UNLINKED_HINT = "Your user is not linked to a HubSpot owner yet. An administrator can link it in Settings → People & access.";

/** The focus view's count, or null when it has none to show ("My opportunities" without an owner link). */
export function focusCount(focus: FocusCounts | null, key: FocusKey): number | null {
  if (!focus) return null;
  switch (key) {
    case "all":
      return focus.all_open;
    case "closing":
      return focus.closing_this_month;
    case "mine":
      return focus.mine_available ? focus.mine : null;
    case "attention":
      return focus.needs_attention;
    case "watching":
      return focus.watching;
  }
}

export interface CollectionsProps {
  focus: FocusCounts | null;
  activeFocus: FocusKey | null;
  views: SavedWorkspaceView[] | null;
  groups: TrackingGroupSummary[] | null;
  activeGroup: string | null;
  /** Why the views or groups could not be listed. */
  loadError: string | null;
  onFocus: (key: FocusKey) => void;
  onOpenView: (view: SavedWorkspaceView) => void;
  onDeleteView: (view: SavedWorkspaceView) => void;
  onToggleGroup: (groupId: string) => void;
  onSaveView: () => void;
  onCreateGroup: () => void;
  onRetry: () => void;
}

const HEADING = "text-label uppercase text-text-secondary";
const ITEM =
  "flex w-full items-center justify-between gap-2 rounded-control px-2 py-1.5 text-left text-table transition-motion focus-visible:outline-focus";
const ADD = "rounded-control px-2 py-1 text-left text-table font-medium text-primary-text hover:bg-primary-subtle focus-visible:outline-focus";

function itemTone(active: boolean): string {
  return active ? "bg-primary-subtle text-primary-text" : "text-text hover:bg-primary-subtle";
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-1 text-secondary text-danger">
      <p>{message}</p>
      <button type="button" onClick={onRetry} className="font-medium underline focus-visible:outline-focus">
        Retry
      </button>
    </div>
  );
}

/** The left column on wide screens (hidden on narrow ones, where the panel replaces it). */
export function CollectionsSidebar({ className, ...props }: CollectionsProps & { className?: string }) {
  const hintId = useId();
  const { focus, activeFocus, views, groups, activeGroup } = props;
  return (
    <aside aria-label="Views and groups" className={`flex flex-col gap-6 ${className ?? ""}`}>
      <section className="flex flex-col gap-1">
        <h2 className={HEADING}>Focus views</h2>
        {FOCUS_VIEWS.map(({ key, label }) => {
          const unlinked = key === "mine" && focus !== null && !focus.mine_available;
          const count = focusCount(focus, key);
          return (
            <div key={key} className="flex flex-col">
              <button
                type="button"
                aria-pressed={activeFocus === key}
                disabled={unlinked}
                aria-describedby={unlinked ? hintId : undefined}
                onClick={() => props.onFocus(key)}
                className={`${ITEM} ${itemTone(activeFocus === key)} disabled:cursor-not-allowed disabled:opacity-60`}
              >
                <span>{label}</span>
                {count !== null ? <span className="font-mono text-secondary">{count}</span> : null}
              </button>
              {unlinked ? (
                <p id={hintId} className="px-2 text-secondary text-text-secondary">
                  {MINE_UNLINKED_HINT}
                </p>
              ) : null}
            </div>
          );
        })}
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={HEADING}>Saved views</h2>
        {views?.length
          ? views.map((view) => (
              <div key={view.id} className="flex items-center gap-1">
                <button type="button" onClick={() => props.onOpenView(view)} className={`${ITEM} ${itemTone(false)} min-w-0`}>
                  <span className="min-w-0 break-words">
                    <span aria-hidden>◈ </span>
                    {view.name}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete saved view ${view.name}`}
                  onClick={() => props.onDeleteView(view)}
                  className="shrink-0 rounded-control p-1 text-text-secondary hover:bg-danger-surface hover:text-danger focus-visible:outline-focus"
                >
                  <Trash2 aria-hidden className="h-3.5 w-3.5" />
                </button>
              </div>
            ))
          : views
            ? <p className="px-2 text-secondary text-text-secondary">Keep the filters you use most.</p>
            : null}
        <button type="button" onClick={props.onSaveView} className={ADD}>
          ＋ Save current view
        </button>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className={HEADING}>Tracking groups</h2>
        {groups?.length
          ? groups.map((group) => (
              <button
                key={group.id}
                type="button"
                aria-pressed={activeGroup === group.id}
                onClick={() => props.onToggleGroup(group.id)}
                className={`${ITEM} ${itemTone(activeGroup === group.id)}`}
              >
                <span className="min-w-0 break-words">
                  <span aria-hidden>◌ </span>
                  {group.name}
                </span>
                <span className="font-mono text-secondary">{group.deal_ids.length}</span>
              </button>
            ))
          : groups
            ? <p className="px-2 text-secondary text-text-secondary">No groups yet.</p>
            : null}
        <button type="button" onClick={props.onCreateGroup} className={ADD}>
          ＋ Create group
        </button>
        <p className="px-2 text-secondary text-text-secondary">
          Groups collect deals.
          <br />
          Views remember filters.
        </p>
      </section>
      {props.loadError ? <LoadError message={props.loadError} onRetry={props.onRetry} /> : null}
    </aside>
  );
}

const PANEL_BUTTON =
  "w-full rounded-control border px-3 py-2 text-center text-body transition-motion focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60";

/** "Your views & groups": the sidebar's content in a drawer, opened from the records' "Views & groups" button. */
export function ViewsPanel({
  open,
  onOpenChange,
  onCloseAutoFocus,
  ...props
}: CollectionsProps & DrawerControlProps) {
  const hintId = useId();
  const { focus, activeFocus, views, groups, activeGroup } = props;
  return (
    <PipelineDrawer open={open} onOpenChange={onOpenChange} onCloseAutoFocus={onCloseAutoFocus} title="Your views & groups">
      <section className="flex flex-col gap-2">
        <h3 className="text-section text-text">Focus views</h3>
        {FOCUS_VIEWS.map(({ key, label }) => {
          const unlinked = key === "mine" && focus !== null && !focus.mine_available;
          const count = focusCount(focus, key);
          return (
            <div key={key} className="flex flex-col gap-1">
              <button
                type="button"
                aria-pressed={activeFocus === key}
                disabled={unlinked}
                aria-describedby={unlinked ? hintId : undefined}
                onClick={() => props.onFocus(key)}
                className={`${PANEL_BUTTON} ${
                  activeFocus === key ? "border-primary bg-primary-subtle text-primary-text" : "border-input-border bg-surface text-text"
                }`}
              >
                {count !== null ? `${label} · ${count}` : label}
              </button>
              {unlinked ? (
                <p id={hintId} className="text-secondary text-text-secondary">
                  {MINE_UNLINKED_HINT}
                </p>
              ) : null}
            </div>
          );
        })}
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-section text-text">Saved views</h3>
        {views?.length
          ? views.map((view) => (
              <div key={view.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => props.onOpenView(view)}
                  className={`${PANEL_BUTTON} border-input-border bg-surface text-text`}
                >
                  {view.name}
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete saved view ${view.name}`}
                  onClick={() => props.onDeleteView(view)}
                  className="shrink-0 text-text-secondary hover:text-danger"
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </Button>
              </div>
            ))
          : views
            ? <p className="text-body text-text-secondary">No saved views yet.</p>
            : null}
        <Button variant="secondary" onClick={props.onSaveView}>
          ＋ Save current view
        </Button>
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-section text-text">Tracking groups</h3>
        {groups?.length
          ? groups.map((group) => (
              <button
                key={group.id}
                type="button"
                aria-pressed={activeGroup === group.id}
                onClick={() => props.onToggleGroup(group.id)}
                className={`${PANEL_BUTTON} ${
                  activeGroup === group.id ? "border-primary bg-primary-subtle text-primary-text" : "border-input-border bg-surface text-text"
                }`}
              >
                {`${group.name} · ${group.deal_ids.length}`}
              </button>
            ))
          : groups
            ? <p className="text-body text-text-secondary">No groups yet.</p>
            : null}
        <Button variant="secondary" onClick={props.onCreateGroup}>
          ＋ Create group
        </Button>
      </section>
      {props.loadError ? <LoadError message={props.loadError} onRetry={props.onRetry} /> : null}
    </PipelineDrawer>
  );
}

export interface DeleteViewDialogProps extends DrawerControlProps {
  view: SavedWorkspaceView | null;
  onDeleted: (view: SavedWorkspaceView) => void;
}

/** Confirms removing one of the caller's saved views (DELETE /pipeline/views/{id}). */
export function DeleteViewDialog({ open, onOpenChange, onCloseAutoFocus, view, onDeleted }: DeleteViewDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    if (!view) return;
    setBusy(true);
    setError(null);
    try {
      await deleteWorkspaceView(view.id);
      onDeleted(view);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "The view could not be deleted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setError(null);
        onOpenChange(next);
      }}
    >
      <DialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>
            <span className="text-section text-text">Delete saved view</span>
          </DialogTitle>
          <DialogDescription>
            {view ? `“${view.name}” will be removed from your saved views. The filters on this page stay as they are.` : ""}
          </DialogDescription>
        </DialogHeader>
        <p role="alert" className="text-body text-danger">
          {error}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="destructive" onClick={() => void confirm()} disabled={busy}>
            Delete view
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Keep view
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
