// S23-PL2 F11 · the deal preview's next-action editor. It writes to the EXISTING
// next-action endpoint: POST /next-actions to create one for the signed-in user,
// PATCH /next-actions/{id} with the action's current revision to change it
// (api/app/routers/next_actions.py). A next action the user may not change is
// shown with who can, instead of a form the API would refuse.
import { useEffect, useId, useRef, useState } from "react";

import {
  createNextAction,
  listNextActions,
  patchNextAction,
  type NextActionRow,
} from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";

export interface ShownNextAction {
  id: string;
  text: string;
  due_on: string | null;
}

export interface NextActionEditorProps {
  dealId: string;
  /** The open next action shown for the deal (the row's, or the one just saved here). */
  current: ShownNextAction | null;
  /** The signed-in user's id: a new next action is assigned to them. */
  assigneeId: string | null;
  onSaved: (action: ShownNextAction) => void;
}

const MAX_TEXT = 140;

type Existing = { state: "none" } | { state: "loading" } | { state: "found"; row: NextActionRow } | { state: "gone" };

function shown(row: NextActionRow, fallbackText: string): ShownNextAction {
  return { id: row.id, text: row.title ?? row.description ?? fallbackText, due_on: row.due_date ?? null };
}

export function NextActionEditor({ dealId, current, assigneeId, onSaved }: NextActionEditorProps) {
  const textId = useId();
  const [text, setText] = useState(current?.text ?? "");
  const [due, setDue] = useState(current?.due_on ?? "");
  const [existing, setExisting] = useState<Existing>(current ? { state: "loading" } : { state: "none" });
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  /** The deal's open next action as the API has it now (its revision and whether this user may edit it). */
  const readExisting = async (actionId: string): Promise<Existing> => {
    const list = await listNextActions({ opportunity_id: dealId });
    const row = list.items.find((item) => item.id === actionId);
    return row ? { state: "found", row } : { state: "gone" };
  };

  // The action the row had when the editor opened; a save keeps the API's answer instead.
  const [firstId] = useState(() => current?.id ?? null);
  useEffect(() => {
    if (!firstId) return;
    let cancelled = false;
    readExisting(firstId)
      .then((found) => {
        if (!cancelled) setExisting((now) => (now.state === "loading" ? found : now));
      })
      // Unknown yet: the save asks again and reports the API's answer.
      .catch(() => {
        if (!cancelled) setExisting((now) => (now.state === "loading" ? { state: "gone" } : now));
      });
    return () => {
      cancelled = true;
    };
    // One read when the editor opens (it is keyed by deal).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstId]);

  if (existing.state === "found" && existing.row.can_edit === false) {
    return (
      <p className="text-secondary text-text-secondary">
        Only the person assigned to this next action, its creator or a sales leader can change it.
      </p>
    );
  }

  const save = async () => {
    setSaved(false);
    const title = text.trim();
    if (!title) {
      setProblem("Enter what happens next.");
      return;
    }
    setProblem(null);
    setSaving(true);
    try {
      let target: Existing = existing;
      if (existing.state === "loading" || (existing.state === "gone" && firstId)) {
        target = firstId ? await readExisting(firstId) : { state: "none" };
      }
      let row: NextActionRow;
      if (target.state === "found") {
        row = await patchNextAction(target.row.id, {
          title,
          ...(due ? { due_date: due } : { clear_due_date: true }),
          expected_revision: target.row.revision,
        });
      } else {
        if (!assigneeId) throw new Error("Your profile is still loading. Try again in a moment.");
        row = await createNextAction({
          opportunity_id: dealId,
          title,
          assignee_user_id: assigneeId,
          due_date: due || null,
        });
      }
      if (!live.current) return;
      setExisting({ state: "found", row });
      setText(row.title ?? title);
      setDue(row.due_date ?? "");
      setSaved(true);
      onSaved(shown(row, title));
    } catch (err) {
      if (!live.current) return;
      setProblem(err instanceof Error && err.message ? err.message : "The next action could not be saved.");
    } finally {
      if (live.current) setSaving(false);
    }
  };

  const creating = existing.state === "none" || existing.state === "gone";
  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <label htmlFor={textId} className="sr-only">
          Next action
        </label>
        <Input
          id={textId}
          value={text}
          maxLength={MAX_TEXT}
          placeholder="What happens next?"
          onChange={(e) => {
            setText(e.target.value);
            setSaved(false);
          }}
        />
        <Input
          type="date"
          aria-label="Due date"
          value={due}
          onChange={(e) => {
            setDue(e.target.value);
            setSaved(false);
          }}
          className="sm:w-44"
        />
      </div>
      <div>
        <Button
          variant="secondary"
          onClick={() => void save()}
          disabled={saving || (creating && !assigneeId)}
        >
          Save next action
        </Button>
      </div>
      {problem ? (
        <p role="alert" className="rounded-control border border-border bg-warning-surface px-3 py-2 text-secondary text-warning">
          {problem}
        </p>
      ) : null}
      <p role="status" className="text-secondary text-primaryText">
        {saved ? "Next action saved." : ""}
      </p>
    </div>
  );
}
