import { Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../ui-v2/primitives/button";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";

export interface Condition {
  id: string;
  text: string;
  owner: string;
  due: string;
  evidence: string;
  blocksSignature: boolean;
  blocksDelivery: boolean;
  blocksMilestones: boolean;
}

export interface ConditionsEditorProps {
  conditions: Condition[];
  onChange: (next: Condition[]) => void;
}

/**
 * Individual-condition editor. A single free-text note is not enough
 * for a conditional approval (spec §14) — every condition carries its
 * own owner, due date, evidence requirement and blocking scope.
 */
export function ConditionsEditor({
  conditions,
  onChange,
}: ConditionsEditorProps) {
  const [nextId, setNextId] = useState(1);

  const add = () => {
    onChange([
      ...conditions,
      {
        id: `c${nextId}`,
        text: "",
        owner: "",
        due: "",
        evidence: "",
        blocksSignature: true,
        blocksDelivery: false,
        blocksMilestones: false,
      },
    ]);
    setNextId((n) => n + 1);
  };

  const update = (id: string, patch: Partial<Condition>) => {
    onChange(conditions.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  };

  const remove = (id: string) => {
    onChange(conditions.filter((c) => c.id !== id));
  };

  return (
    <div className="space-y-3">
      {conditions.length === 0 ? (
        <p className="text-body text-text-secondary">
          No conditions yet. Add one to switch this approval to conditional.
        </p>
      ) : (
        conditions.map((c) => (
          <ConditionRow
            key={c.id}
            condition={c}
            onUpdate={(patch) => update(c.id, patch)}
            onRemove={() => remove(c.id)}
          />
        ))
      )}
      <Button type="button" variant="secondary" size="sm" onClick={add}>
        Add condition
      </Button>
    </div>
  );
}

function ConditionRow({
  condition,
  onUpdate,
  onRemove,
}: {
  condition: Condition;
  onUpdate: (patch: Partial<Condition>) => void;
  onRemove: () => void;
}) {
  const ownerMissing = condition.owner.trim() === "";
  const dueMissing = condition.due.trim() === "";
  return (
    <div
      data-testid={`condition-row-${condition.id}`}
      className="rounded-panel border border-divider bg-surface p-3 space-y-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <Label htmlFor={`text-${condition.id}`}>Condition</Label>
          <Input
            id={`text-${condition.id}`}
            value={condition.text}
            onChange={(e) => onUpdate({ text: e.target.value })}
            placeholder="Describe what must be true"
          />
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove condition"
          className="mt-6 text-text-secondary hover:text-danger focus-visible:outline-focus"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <Label htmlFor={`owner-${condition.id}`}>
            Owner{" "}
            {ownerMissing ? (
              <span className="text-danger">*</span>
            ) : null}
          </Label>
          <Input
            id={`owner-${condition.id}`}
            value={condition.owner}
            onChange={(e) => onUpdate({ owner: e.target.value })}
            aria-invalid={ownerMissing}
          />
        </div>
        <div>
          <Label htmlFor={`due-${condition.id}`}>
            Due date{" "}
            {dueMissing ? (
              <span className="text-danger">*</span>
            ) : null}
          </Label>
          <Input
            id={`due-${condition.id}`}
            type="date"
            value={condition.due}
            onChange={(e) => onUpdate({ due: e.target.value })}
            aria-invalid={dueMissing}
          />
        </div>
        <div>
          <Label htmlFor={`evidence-${condition.id}`}>
            Evidence{" "}
            {condition.evidence.trim() === "" ? (
              <span className="text-danger">*</span>
            ) : null}
          </Label>
          <Input
            id={`evidence-${condition.id}`}
            value={condition.evidence}
            onChange={(e) => onUpdate({ evidence: e.target.value })}
            placeholder="Document / link required"
            aria-invalid={condition.evidence.trim() === ""}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-secondary text-text">
        <label className="inline-flex items-center gap-2">
          <Checkbox
            checked={condition.blocksSignature}
            onCheckedChange={(v) => onUpdate({ blocksSignature: v === true })}
          />
          Blocks signature
        </label>
        <label className="inline-flex items-center gap-2">
          <Checkbox
            checked={condition.blocksDelivery}
            onCheckedChange={(v) => onUpdate({ blocksDelivery: v === true })}
          />
          Blocks delivery
        </label>
        <label className="inline-flex items-center gap-2">
          <Checkbox
            checked={condition.blocksMilestones}
            onCheckedChange={(v) => onUpdate({ blocksMilestones: v === true })}
          />
          Blocks milestones
        </label>
      </div>
    </div>
  );
}

/** True when every condition has an owner + due date + evidence. */
export function allConditionsComplete(conditions: Condition[]): boolean {
  if (conditions.length === 0) return false;
  return conditions.every(
    (c) =>
      c.owner.trim() !== "" &&
      c.due.trim() !== "" &&
      c.evidence.trim() !== "",
  );
}
