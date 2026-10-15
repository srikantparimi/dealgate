// S23-PL2 F12 / F13 · tracking groups. "Create a tracking group" (sidebar or
// views panel) and "Add selected deals to a group" (the bulk bar). A group
// stores deal membership; the selected deals go into a new group or an
// existing one. Names are unique per user, any letter case (409 otherwise).
import { useId, useState, type FormEvent } from "react";

import { ApiError } from "../../../api/client";
import {
  addDealsToGroup,
  createWorkspaceGroup,
  type TrackingGroupSummary,
} from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { FieldLabel, PipelineDrawer, SELECT_CLASS, type DrawerControlProps } from "./FilterToolbar";
import { plural } from "./format";

export const DUPLICATE_GROUP_MESSAGE = "A group with this name already exists.";

export interface GroupDialogProps extends DrawerControlProps {
  mode: "create" | "add";
  groups: TrackingGroupSummary[];
  /** The deals selected in the list; a new group starts with them. */
  selectedIds: string[];
  onCreated: (group: TrackingGroupSummary) => void;
  onAdded: (group: TrackingGroupSummary) => void;
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

export function GroupDialog({ open, onOpenChange, onCloseAutoFocus, ...body }: GroupDialogProps) {
  const n = body.selectedIds.length;
  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      title={body.mode === "add" ? "Add selected deals to a group" : "Create a tracking group"}
      description={
        n
          ? `${n} selected ${plural(n, "opportunity", "opportunities")} will be included.`
          : "Pick opportunities with the list checkboxes, then add them to a group. You can create an empty group now."
      }
    >
      <GroupBody {...body} />
    </PipelineDrawer>
  );
}

function GroupBody({ mode, groups, selectedIds, onCreated, onAdded }: Omit<GroupDialogProps, keyof DrawerControlProps>) {
  const ids = useId();
  const canAdd = mode === "add" && groups.length > 0;
  const [groupId, setGroupId] = useState(groups[0]?.id ?? "");
  const [name, setName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add() {
    const group = groups.find((g) => g.id === groupId);
    if (!group) return;
    setBusy(true);
    setAddError(null);
    try {
      await addDealsToGroup(group.id, selectedIds);
      onAdded(group);
    } catch (err) {
      setAddError(message(err, "The deals could not be added to the group."));
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setCreateError("Enter a group name.");
      return;
    }
    const folded = trimmed.toLocaleLowerCase();
    if (groups.some((g) => g.name.trim().toLocaleLowerCase() === folded)) {
      setCreateError(DUPLICATE_GROUP_MESSAGE);
      return;
    }
    setBusy(true);
    setCreateError(null);
    try {
      const group = await createWorkspaceGroup({ name: trimmed, deal_ids: selectedIds });
      onCreated(group);
    } catch (err) {
      setCreateError(
        err instanceof ApiError && err.status === 409
          ? DUPLICATE_GROUP_MESSAGE
          : message(err, "The group could not be created."),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {canAdd ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <FieldLabel htmlFor={`${ids}-existing`}>Existing group</FieldLabel>
            <select
              id={`${ids}-existing`}
              value={groupId}
              onChange={(event) => setGroupId(event.target.value)}
              className={SELECT_CLASS}
            >
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
          </div>
          <p role="alert" className="text-body text-text">
            {addError}
          </p>
          <div>
            <Button onClick={() => void add()} disabled={busy}>
              Add selected
            </Button>
          </div>
          <h3 className="text-section text-text">Or create a new group</h3>
        </div>
      ) : null}
      <form onSubmit={create} className="flex flex-col gap-3" noValidate>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-name`}>Group name</FieldLabel>
          <Input
            id={`${ids}-name`}
            value={name}
            maxLength={60}
            placeholder="e.g. Strategic renewals"
            onChange={(event) => {
              setName(event.target.value);
              setCreateError(null);
            }}
          />
        </div>
        <p role="alert" className="text-body text-text">
          {createError}
        </p>
        <div>
          <Button type="submit" variant={canAdd ? "secondary" : "primary"} disabled={busy}>
            Create group
          </Button>
        </div>
      </form>
    </div>
  );
}
