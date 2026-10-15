// S23-PL2 F7 · "Filter by deal owner" (Opportunities tab) and "Filter by
// account owner" (Clients tab). Owner names come from the workspace options;
// the ids only travel in the query.
import { useId, useState } from "react";

import { Button } from "../../../ui-v2/primitives/button";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { PipelineDrawer, type DrawerControlProps } from "./FilterToolbar";

export const PRECISE_FILTERS_TEXT =
  "Select one or more. Choices within a filter combine with OR; different filters combine with AND.";

export interface CheckboxOption {
  value: string;
  label: string;
  /** Right-hand note, e.g. a business unit's region. */
  note?: string;
}

/** Checkbox rows of a precise filter. */
export function CheckboxOptions({
  options,
  checked,
  onChange,
}: {
  options: CheckboxOption[];
  checked: readonly string[];
  onChange: (next: string[]) => void;
}) {
  const base = useId();
  return (
    <div className="flex flex-col gap-2">
      {options.map((option, index) => {
        const id = `${base}-${index}`;
        const on = checked.includes(option.value);
        return (
          <div
            key={option.value}
            className="flex items-center gap-3 rounded-control border border-border bg-surface px-3 py-2"
          >
            <Checkbox
              id={id}
              checked={on}
              onCheckedChange={(value) =>
                onChange(
                  value === true
                    ? [...checked.filter((v) => v !== option.value), option.value]
                    : checked.filter((v) => v !== option.value),
                )
              }
            />
            <label htmlFor={id} className="flex flex-1 items-center justify-between gap-3 text-body text-text">
              <span>{option.label}</span>
              {option.note ? <span className="text-secondary text-text-secondary">{option.note}</span> : null}
            </label>
          </div>
        );
      })}
    </div>
  );
}

export interface OwnerFilterDialogProps extends DrawerControlProps {
  kind: "deal" | "account";
  owners: { id: string; name: string }[];
  selected: string[];
  onApply: (ids: string[]) => void;
}

export function OwnerFilterDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  kind,
  owners,
  selected,
  onApply,
}: OwnerFilterDialogProps) {
  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      kicker="Precise filters"
      title={kind === "deal" ? "Filter by deal owner" : "Filter by account owner"}
      description={PRECISE_FILTERS_TEXT}
    >
      <OwnerFilterBody kind={kind} owners={owners} selected={selected} onApply={onApply} />
    </PipelineDrawer>
  );
}

/** Mounted each time the drawer opens, so the choices start from the applied filter. */
function OwnerFilterBody({ kind, owners, selected, onApply }: Omit<OwnerFilterDialogProps, keyof DrawerControlProps>) {
  const [draft, setDraft] = useState<string[]>(selected);
  const options: CheckboxOption[] = [
    ...owners.map((owner) => ({ value: owner.id, label: owner.name })),
    { value: "none", label: kind === "deal" ? "No deal owner" : "No account owner" },
    ...(kind === "deal" ? [{ value: "former", label: "Former HubSpot user" }] : []),
  ];
  return (
    <>
      <CheckboxOptions options={options} checked={draft} onChange={setDraft} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => onApply(draft)}>Apply filter</Button>
        <Button variant="secondary" onClick={() => onApply([])}>
          Clear this filter
        </Button>
      </div>
    </>
  );
}
