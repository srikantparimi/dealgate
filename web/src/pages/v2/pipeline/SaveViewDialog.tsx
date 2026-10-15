// S23-PL2 F12 / B11 · "Save your working view". A saved view keeps the
// filters, tab and layout (the same shape as the URL); names are unique per
// user, any letter case (the API answers 409 for a duplicate).
import { useId, useState, type FormEvent } from "react";

import { ApiError } from "../../../api/client";
import { createWorkspaceView, type SavedWorkspaceView } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { FieldLabel, PipelineDrawer, type DrawerControlProps } from "./FilterToolbar";
import { viewFromState, type WorkspaceUrlState } from "./workspaceState";

export const DUPLICATE_VIEW_MESSAGE = "You already have a view with this name.";

export interface SaveViewDialogProps extends DrawerControlProps {
  state: WorkspaceUrlState;
  /** The caller's saved view names, for the duplicate check before asking. */
  existingNames: string[];
  onSaved: (view: SavedWorkspaceView) => void;
}

export function SaveViewDialog({ open, onOpenChange, onCloseAutoFocus, ...body }: SaveViewDialogProps) {
  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      title="Save your working view"
      description="Keeps the current filters, tab and layout together."
    >
      <SaveViewBody {...body} />
    </PipelineDrawer>
  );
}

function SaveViewBody({ state, existingNames, onSaved }: Omit<SaveViewDialogProps, keyof DrawerControlProps>) {
  const id = useId();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Enter a name for this view.");
      return;
    }
    const folded = trimmed.toLocaleLowerCase();
    if (existingNames.some((existing) => existing.trim().toLocaleLowerCase() === folded)) {
      setError(DUPLICATE_VIEW_MESSAGE);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const view = await createWorkspaceView({ name: trimmed, ...viewFromState(state) });
      onSaved(view);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? DUPLICATE_VIEW_MESSAGE
          : err instanceof Error
            ? err.message
            : "The view could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
      <div className="flex flex-col gap-1">
        <FieldLabel htmlFor={id}>View name</FieldLabel>
        <Input
          id={id}
          value={name}
          maxLength={60}
          placeholder="e.g. Retro Rabbit · closing this month"
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(event) => {
            setName(event.target.value);
            setError(null);
          }}
        />
      </div>
      <p id={`${id}-error`} role="alert" className="text-body text-text">
        {error}
      </p>
      <div>
        <Button type="submit" disabled={saving} aria-busy={saving}>
          Save view
        </Button>
      </div>
    </form>
  );
}
