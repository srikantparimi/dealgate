/**
 * RenewalWorkspaceSheet — the right Sheet drawer opened from a row on
 * the Renewals V2 page. Spec §16 requires: agreement summary; expiry /
 * notice logic; owners; client engagement timeline; proposal /
 * amendment; next step; reminders + escalation; final outcome evidence.
 *
 * Outcomes are a fixed enum (spec §16):
 *   discussion_in_progress | proposal_requested | negotiation |
 *   extension_signed | replaced | not_renewing | completed_closeout.
 * "Client interested" is not a signed renewal — the enum enforces that.
 */

import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  patchRenewal,
  type RenewalRow,
  type UUID,
} from "../../../api/client";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import { Label } from "../../../ui-v2/primitives/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../../ui-v2/primitives/sheet";
import { computeReminderPlan } from "./reminders";

export type RenewalOutcome =
  | "discussion_in_progress"
  | "proposal_requested"
  | "negotiation"
  | "extension_signed"
  | "replaced"
  | "not_renewing"
  | "completed_closeout";

export const RENEWAL_OUTCOMES: RenewalOutcome[] = [
  "discussion_in_progress",
  "proposal_requested",
  "negotiation",
  "extension_signed",
  "replaced",
  "not_renewing",
  "completed_closeout",
];

const OUTCOME_LABEL: Record<RenewalOutcome, string> = {
  discussion_in_progress: "Discussion in progress",
  proposal_requested: "Proposal requested",
  negotiation: "Negotiation",
  extension_signed: "Extension signed",
  replaced: "Replaced by new SOW",
  not_renewing: "Not renewing",
  completed_closeout: "Completed closeout",
};

function isSignedOutcome(o: RenewalOutcome): boolean {
  return o === "extension_signed" || o === "replaced";
}

export interface RenewalWorkspaceSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  renewal: RenewalRow | null;
  onSaved?: (renewal: RenewalRow) => void;
  today?: string;
}

export function RenewalWorkspaceSheet({
  open,
  onOpenChange,
  renewal,
  onSaved,
  today,
}: RenewalWorkspaceSheetProps) {
  const [update, setUpdate] = useState("");
  const [outcome, setOutcome] = useState<RenewalOutcome>(
    "discussion_in_progress",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUpdate("");
    setOutcome("discussion_in_progress");
    setError(null);
  }, [renewal?.id]);

  if (!renewal) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent aria-label="Renewal workspace" />
      </Sheet>
    );
  }

  const plan = computeReminderPlan({
    today: today ?? new Date().toISOString().slice(0, 10),
    expiryDate: renewal.term_end,
  });

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!renewal) return;
    setSaving(true);
    setError(null);
    try {
      const summary = update.trim()
        ? `${OUTCOME_LABEL[outcome]}: ${update.trim()}`
        : OUTCOME_LABEL[outcome];
      const patched = await patchRenewal(renewal.id as UUID, {
        outcome_summary: summary,
        status: isSignedOutcome(outcome) ? "extended" : "closed",
      });
      onSaved?.(patched);
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        aria-label="Renewal workspace"
        className="flex flex-col gap-4 overflow-y-auto"
      >
        <SheetHeader>
          <SheetTitle>Renewal workspace</SheetTitle>
          <SheetDescription>
            Opportunity {renewal.opportunity_id.slice(0, 8)} · term ends{" "}
            {renewal.term_end}. Logging an update preserves the next weekly
            review unless a configured rule defers it.
          </SheetDescription>
        </SheetHeader>

        <section
          className="rounded-panel border border-divider p-3"
          data-testid="renewal-summary"
        >
          <h3 className="text-section text-text">Agreement summary</h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-body">
            <div>
              <dt className="text-secondary text-text-secondary">Expiry</dt>
              <dd className="tnum text-text">{renewal.term_end}</dd>
            </div>
            <div>
              <dt className="text-secondary text-text-secondary">
                Days remaining
              </dt>
              <dd className="tnum text-text">{renewal.days_until_end}</dd>
            </div>
            <div>
              <dt className="text-secondary text-text-secondary">First alert</dt>
              <dd className="tnum text-text">{plan.firstAlertDate}</dd>
            </div>
            <div>
              <dt className="text-secondary text-text-secondary">
                Weekly reviews
              </dt>
              <dd className="tnum text-text">{plan.weeklyOccurrences.length}</dd>
            </div>
          </dl>
        </section>

        <section
          className="rounded-panel border border-divider p-3"
          data-testid="renewal-owners"
        >
          <h3 className="text-section text-text">Owners</h3>
          <ul className="mt-2 text-body">
            <li className="text-text">
              Account owner:{" "}
              {renewal.owner_id
                ? renewal.owner_id.slice(0, 8)
                : "Unassigned"}
            </li>
            <li className="text-text-secondary">
              Delivery owner: from Delivery workspace
            </li>
          </ul>
        </section>

        <section
          className="rounded-panel border border-divider p-3"
          data-testid="renewal-timeline"
        >
          <h3 className="text-section text-text">Client engagement timeline</h3>
          {renewal.outcome_summary ? (
            <p className="mt-2 text-body text-text">
              {renewal.outcome_summary}
            </p>
          ) : (
            <p className="mt-2 text-body text-text-secondary">
              No update logged yet. Record the first client conversation to
              start the timeline.
            </p>
          )}
        </section>

        <form onSubmit={save} className="flex flex-col gap-3">
          <h3 className="text-section text-text">Record update</h3>
          <div className="flex flex-col gap-1">
            <Label htmlFor="renewal-update">Substantive note</Label>
            <textarea
              id="renewal-update"
              data-testid="renewal-update"
              value={update}
              onChange={(e) => setUpdate(e.target.value)}
              rows={3}
              className="rounded-control border border-input-border bg-surface px-3 py-2 text-body text-text focus-visible:outline-focus"
              placeholder="What did the client actually say?"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="renewal-outcome">Outcome</Label>
            <select
              id="renewal-outcome"
              data-testid="renewal-outcome"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as RenewalOutcome)}
              className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
            >
              {RENEWAL_OUTCOMES.map((o) => (
                <option key={o} value={o}>
                  {OUTCOME_LABEL[o]}
                </option>
              ))}
            </select>
            {!isSignedOutcome(outcome) ? (
              <p className="mt-1 text-secondary text-text-secondary">
                <StatusBadge tone="neutral" label="Not a signed renewal" />
              </p>
            ) : null}
          </div>
          {error ? (
            <div
              role="alert"
              className="rounded-control border border-danger/40 bg-danger-surface p-2 text-body text-text"
            >
              {error}
            </div>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={saving}
              data-testid="renewal-save"
            >
              {saving ? "Saving…" : "Save update"}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}

export function outcomeLabel(o: RenewalOutcome): string {
  return OUTCOME_LABEL[o];
}
