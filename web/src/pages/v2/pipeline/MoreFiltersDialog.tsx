// S23-PL2 F7 · "More ways to focus": SOW state, attention, missing information,
// tracking group and watching. SOW labels come from the workspace options (the
// nine states the code derives, D5).
import { useId, useState, type FormEvent } from "react";

import type {
  AgreementMissingFilter,
  AttentionFilter,
  MissingFilter,
  TrackingGroupSummary,
  WorkspaceQuery,
} from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Checkbox } from "../../../ui-v2/primitives/checkbox";
import { FieldLabel, PipelineDrawer, SELECT_CLASS, type DrawerControlProps } from "./FilterToolbar";

export const ATTENTION_OPTIONS: { value: AttentionFilter; label: string }[] = [
  { value: "overdue", label: "Overdue next action" },
  { value: "past_close", label: "Close date passed" },
  { value: "no_owner", label: "No deal owner" },
  { value: "inactive", label: "14+ days inactive" },
  { value: "pending_approval", label: "Pending approval" },
  { value: "any", label: "Any flag" },
];

/**
 * S24-AG1 F6 · the missing-agreement filters mean the state "Missing" (a net-new client past
 * stage 1 without it), not "no file": an existing client, a standard copy or a covered mark is not
 * missing. The option and its chip use these words.
 */
export const AGREEMENT_MISSING_TEXT: Record<AgreementMissingFilter, string> = {
  nda: "NDA (net new, past stage 1)",
  msa: "MSA (net new, past stage 1)",
  agreements: "NDA or MSA (net new, past stage 1)",
};

export const MISSING_OPTIONS: { value: MissingFilter; label: string }[] = [
  { value: "owner", label: "Deal owner" },
  { value: "close", label: "Close date" },
  { value: "activity", label: "Activity date" },
  { value: "next_action", label: "Next action" },
  { value: "nda", label: AGREEMENT_MISSING_TEXT.nda },
  { value: "msa", label: AGREEMENT_MISSING_TEXT.msa },
  { value: "agreements", label: AGREEMENT_MISSING_TEXT.agreements },
];

export type MoreFilters = Pick<WorkspaceQuery, "sow" | "attention" | "missing" | "group" | "watching">;

export interface MoreFiltersDialogProps extends DrawerControlProps {
  sowStates: { value: string; label: string }[];
  groups: TrackingGroupSummary[];
  /** Open deals the viewer watches (`focus.watching`); null hides the count. */
  watchingCount: number | null;
  value: MoreFilters;
  onApply: (next: MoreFilters) => void;
}

export function MoreFiltersDialog({ open, onOpenChange, onCloseAutoFocus, ...body }: MoreFiltersDialogProps) {
  return (
    <PipelineDrawer open={open} onOpenChange={onOpenChange} onCloseAutoFocus={onCloseAutoFocus} title="More ways to focus">
      <MoreFiltersBody {...body} />
    </PipelineDrawer>
  );
}

function MoreFiltersBody({
  sowStates,
  groups,
  watchingCount,
  value,
  onApply,
}: Omit<MoreFiltersDialogProps, keyof DrawerControlProps>) {
  const ids = useId();
  const [sow, setSow] = useState(value.sow ?? "");
  const [attention, setAttention] = useState<string>(value.attention ?? "");
  const [missing, setMissing] = useState<string>(value.missing ?? "");
  const [group, setGroup] = useState(value.group ?? "");
  const [watching, setWatching] = useState(value.watching);
  // A group in the link that is no longer one of yours still shows, so it can be cleared.
  const unknownGroup = value.group && !groups.some((g) => g.id === value.group) ? value.group : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    onApply({
      sow: sow || null,
      attention: (attention || null) as AttentionFilter | null,
      missing: (missing || null) as MissingFilter | null,
      group: group || null,
      watching,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-sow`}>SOW state</FieldLabel>
          <select id={`${ids}-sow`} value={sow} onChange={(e) => setSow(e.target.value)} className={SELECT_CLASS}>
            <option value="">Any SOW state</option>
            <option value="pending">Pending approval (in review or CEO exception)</option>
            {sowStates.map((state) => (
              <option key={state.value} value={state.value}>
                {state.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-attention`}>Attention</FieldLabel>
          <select
            id={`${ids}-attention`}
            value={attention}
            onChange={(e) => setAttention(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">Any attention state</option>
            {ATTENTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-missing`}>Missing information</FieldLabel>
          <select
            id={`${ids}-missing`}
            value={missing}
            onChange={(e) => setMissing(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">No missing-data filter</option>
            {MISSING_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={`${ids}-group`}>Tracking group</FieldLabel>
          <select id={`${ids}-group`} value={group} onChange={(e) => setGroup(e.target.value)} className={SELECT_CLASS}>
            <option value="">All groups</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
            {unknownGroup ? <option value={unknownGroup}>Unavailable group</option> : null}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-control border border-border px-3 py-2">
        <Checkbox
          id={`${ids}-watching`}
          checked={watching}
          onCheckedChange={(checked) => setWatching(checked === true)}
        />
        <label htmlFor={`${ids}-watching`} className="text-body text-text">
          {watchingCount === null
            ? "Only opportunities I’m watching"
            : `Only opportunities I’m watching (${watchingCount})`}
        </label>
      </div>
      <p className="text-secondary text-text-secondary">
        A saved view stores filters. A group stores deal membership. Watching is your personal follow list.
      </p>
      <div>
        <Button type="submit">Apply filters</Button>
      </div>
    </form>
  );
}
