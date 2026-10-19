// S24-AG1 F1/F4 · the line under the header: whether the cutover is set, and the
// latest batch. Not set: amber, "Not set up yet." Set: the cutover date (an
// America/Los_Angeles calendar date), what it means, and the latest batch that
// is not undone, with "Undo batch AG-…" (SystemAdmin; locked for everyone else).
import type { AgreementsWorkspace } from "../../../api/agreements";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { longCalendarDate, plural } from "../pipeline/format";
import { isBatchLabel } from "./agreementsFormat";
import type { AgreementsBatch } from "./agreementsState";
import type { AgreementRoles } from "./useAgreementsWorkspace";

export interface CutoverLineProps {
  cutover: AgreementsWorkspace["cutover"];
  standard: AgreementsWorkspace["standard"];
  roles: AgreementRoles | null;
  onUndo: (label: string) => void;
}

/** The latest batch in one sentence (leading space included), or "No active batch." */
export function batchSentence(batch: AgreementsBatch | null | undefined): string {
  if (!batch || !isBatchLabel(batch.id)) return " No active batch.";
  const id = batch.id;
  switch (batch.status) {
    case "running":
      return ` Batch ${id} is attaching standard copies: ${batch.done_count} of ${batch.target_count} ${plural(batch.target_count, "client", "clients")} done.`;
    case "undoing":
      return ` Batch ${id} is being undone.`;
    case "failed":
      // The phase decides the words: a finished batch whose undo stopped did not stop itself.
      return batch.failed_phase === "undo"
        ? ` The undo of batch ${id} stopped before it finished. Press Undo again to finish.`
        : ` Batch ${id} stopped after ${batch.done_count} of ${batch.target_count} ${plural(batch.target_count, "client", "clients")}. Attach the standard copies again to finish.`;
    case "undone":
      return " No active batch.";
    default: {
      const n = batch.attached_clients;
      return typeof n === "number"
        ? ` Latest batch ${id} attached ${n} ${plural(n, "client", "clients")}.`
        : ` Latest batch ${id}.`;
    }
  }
}

/** Undo is offered for a finished batch (done, or failed part-way); never while one runs or is being undone. */
export function canUndo(batch: AgreementsBatch | null | undefined): batch is AgreementsBatch {
  return Boolean(batch && isBatchLabel(batch.id) && (batch.status === "done" || batch.status === "failed"));
}

export function CutoverLine({ cutover, standard, roles, onUndo }: CutoverLineProps) {
  if (!cutover.set || !cutover.date) {
    const anyStandard = Boolean(standard.NDA || standard.MSA);
    return (
      <div data-state="not-set" className="border-l-4 border-warning py-2 pl-3 text-table text-warning">
        <p className="min-w-0">
          <strong className="font-semibold">Not set up yet.</strong>
          {anyStandard ? "" : " No NDA or MSA has been uploaded."}
          {" Existing and net-new are provisional until you attach the standard copies, which also sets the cutover date."}
        </p>
      </div>
    );
  }
  const batch = (cutover.latest_batch ?? null) as AgreementsBatch | null;
  return (
    <div
      data-state="set"
      className="flex flex-col gap-1 border-l-4 border-border-strong py-2 pl-3 text-table text-text-secondary sm:flex-row sm:items-center sm:justify-between sm:gap-4"
    >
      <p className="min-w-0 flex-1 [overflow-wrap:anywhere]">
        <strong className="font-semibold text-text">{`Cutover ${longCalendarDate(cutover.date)}.`}</strong>
        {" Clients that existed at the cutover are covered. Clients created or closing a first deal after it need their own copy."}
        {batchSentence(batch)}
      </p>
      {canUndo(batch) ? (
        <LockedButton
          variant="tertiary"
          size="sm"
          aria-haspopup="dialog"
          lock={roles && !roles.isAdmin ? "admin" : null}
          disabled={roles === null}
          onClick={() => onUndo(batch.id)}
          className="shrink-0 self-start font-semibold underline sm:self-auto"
        >
          {`Undo batch ${batch.id}`}
        </LockedButton>
      ) : null}
    </div>
  );
}
