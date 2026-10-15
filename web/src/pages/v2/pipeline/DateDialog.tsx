// S23-PL2 F7 / B8 · "Choose the date that matters". Calendar dates relative to
// today in America/Los_Angeles; the presets are the contract's `date_preset`
// values, computed on the server.
import { useId, useState, type FormEvent } from "react";

import type { DateField, DatePreset, WorkspaceQuery } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { FieldLabel, PipelineDrawer, SELECT_CLASS, type DrawerControlProps } from "./FilterToolbar";
import { longCalendarDate } from "./format";

export const DATE_FIELD_LABELS: Record<DateField, string> = {
  close: "Expected close",
  created: "Created",
  activity: "Last activity",
};

export const DATE_PRESET_OPTIONS: { value: DatePreset; label: string }[] = [
  { value: "any", label: "Any date" },
  { value: "passed", label: "Before today" },
  { value: "next7", label: "Next 7 days" },
  { value: "next30", label: "Next 30 days" },
  { value: "next90", label: "Next 90 days" },
  { value: "last7", label: "Last 7 days" },
  { value: "last30", label: "Last 30 days" },
  { value: "last90", label: "Last 90 days" },
  { value: "month", label: "This month" },
  { value: "quarter", label: "This quarter" },
  { value: "custom", label: "Custom range" },
];

export type DateFilter = Pick<WorkspaceQuery, "date_field" | "date_preset" | "date_from" | "date_to">;

export interface DateDialogProps extends DrawerControlProps {
  /** `workspace.today`, the Los Angeles calendar date the numbers were computed for. */
  today: string | null;
  value: DateFilter;
  onApply: (next: DateFilter) => void;
}

export function DateDialog({ open, onOpenChange, onCloseAutoFocus, ...body }: DateDialogProps) {
  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      title="Choose the date that matters"
      description={
        body.today
          ? `Calendar dates. Today is ${longCalendarDate(body.today)} (America/Los_Angeles).`
          : "Calendar dates (America/Los_Angeles)."
      }
    >
      <DateBody {...body} />
    </PipelineDrawer>
  );
}

function DateBody({ value, onApply }: Omit<DateDialogProps, keyof DrawerControlProps>) {
  const ids = useId();
  const [field, setField] = useState<DateField>(value.date_field);
  const [preset, setPreset] = useState<DatePreset>(value.date_preset);
  const [from, setFrom] = useState(value.date_from ?? "");
  const [to, setTo] = useState(value.date_to ?? "");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (preset === "custom" && from && to && from > to) {
      setError("The start date must be on or before the end date.");
      return;
    }
    const custom = preset === "custom";
    onApply({
      date_field: field,
      date_preset: preset,
      date_from: custom && from ? from : null,
      date_to: custom && to ? to : null,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-field`}>Date field</FieldLabel>
          <select
            id={`${ids}-field`}
            value={field}
            onChange={(event) => setField(event.target.value as DateField)}
            className={SELECT_CLASS}
          >
            {(Object.keys(DATE_FIELD_LABELS) as DateField[]).map((key) => (
              <option key={key} value={key}>
                {DATE_FIELD_LABELS[key]}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-preset`}>Period</FieldLabel>
          <select
            id={`${ids}-preset`}
            value={preset}
            onChange={(event) => {
              setPreset(event.target.value as DatePreset);
              setError(null);
            }}
            className={SELECT_CLASS}
          >
            {DATE_PRESET_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-from`}>From</FieldLabel>
          <Input id={`${ids}-from`} type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-to`}>Through</FieldLabel>
          <Input id={`${ids}-to`} type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </div>
      </div>
      <p className="text-secondary text-text-secondary">
        From / Through apply with Custom range. “Next” periods suit Expected close; “Last” periods suit Created and
        Last activity.
      </p>
      <div role="alert">
        {error ? (
          <p className="rounded-control border-l-4 border-warning bg-warning-surface px-3 py-2 text-body text-warning">
            {error}
          </p>
        ) : null}
      </div>
      <div>
        <Button type="submit">Apply date filter</Button>
      </div>
    </form>
  );
}
