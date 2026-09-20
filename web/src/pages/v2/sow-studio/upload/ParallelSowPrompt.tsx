/**
 * "Is this a new contract, or the one you already started?" (S10-09)
 *
 * A client can legitimately have several SOWs running at once, so a second
 * upload for the same client is not an error and is never blocked. But
 * someone re-uploading a corrected file from the wrong screen arrives at
 * exactly the same place — and continuing silently gives them two copies of
 * the same engagement in the pipeline, each with its own approval trail.
 *
 * The system cannot tell those apart; the person can. So it asks, once,
 * with enough detail to answer: what is already open, how far along it is,
 * and whether it has been signed.
 */
import type { UUID } from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { PageHeader } from "../../../../ui-v2/PageHeader";

export interface ParallelSowRow {
  opportunity_id: UUID;
  sow_version_id: UUID;
  version_no: number;
  title: string | null;
  uploaded_at: string | null;
  governance_status: string | null;
  is_signed: boolean;
}

export interface ParallelSowPromptProps {
  others: ParallelSowRow[];
  onContinueNew: () => void;
  onOpenExisting: (opportunityId: UUID) => void;
}

export function ParallelSowPrompt({
  others,
  onContinueNew,
  onOpenExisting,
}: ParallelSowPromptProps) {
  return (
    <div data-testid="parallel-sow-prompt">
      <PageHeader
        title="This client already has a SOW in progress"
        subtitle="Running several contracts at once is fine. Continuing by mistake is what puts the same engagement in the pipeline twice."
      />

      <ul className="mb-5 divide-y divide-border rounded-lg border border-border">
        {others.map((o) => (
          <li
            key={o.opportunity_id}
            className="flex flex-wrap items-center gap-3 px-4 py-3"
            data-testid={`parallel-${o.opportunity_id}`}
          >
            <span className="font-medium">
              {o.title ?? "Untitled SOW"}
            </span>
            <StatusBadge tone="neutral" label={`v${o.version_no}`} />
            {o.governance_status ? (
              <StatusBadge tone="neutral" label={o.governance_status} />
            ) : null}
            {o.is_signed ? <StatusBadge tone="ok" label="signed" /> : null}
            <span className="text-text-secondary">
              {o.uploaded_at ? o.uploaded_at.slice(0, 10) : ""}
            </span>
            <span className="ml-auto">
              <Button
                variant="secondary"
                data-testid={`open-${o.opportunity_id}`}
                onClick={() => onOpenExisting(o.opportunity_id)}
              >
                Open this one instead
              </Button>
            </span>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-3">
        <Button onClick={onContinueNew} data-testid="continue-new">
          This is a separate contract — continue
        </Button>
        <p className="text-secondary text-text-secondary">
          Picking an existing SOW leaves this upload unused. To replace a
          file on a SOW you already started, use <strong>New version</strong>{" "}
          on its Documents tab rather than uploading again here.
        </p>
      </div>
    </div>
  );
}
