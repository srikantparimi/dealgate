import { ClientAgreementPresence } from "../../../ui-v2/ClientAgreementPresence";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";
import { SowVersionHistory } from "./SowVersionHistory";

/**
 * Documents tab: the SOW versions, plus a link out to the client's
 * uploaded NDA/MSA docs. S17 collapsed agreements into a flat file
 * store — no per-agreement state chip lives on the SOW workspace
 * anymore.
 */
export function DocumentsTab({ snap }: { snap: WorkspaceSnapshot }) {
  return (
    <section
      aria-label="Documents"
      className="rounded-panel border border-divider bg-surface p-4"
      style={{ maxWidth: "960px" }}
    >
      <h2 className="text-section text-text mb-3">Documents</h2>
      {snap.sow ? (
        <div className="mb-3 flex flex-wrap items-center gap-3 text-body">
          <span className="font-medium">SOW</span>
          <span className="tnum text-text-secondary">
            {snap.sow.file_hash.slice(0, 8)}
          </span>
          <StatusBadge
            tone={snap.sow.confirmed_at ? "ok" : "warn"}
            label={snap.sow.confirmed_at ? "Confirmed" : "Draft"}
          />
        </div>
      ) : null}
      <ClientAgreementPresence clientId={snap.deal?.client_id} />
      {snap.deal?.id ? (
        <SowVersionHistory opportunityId={snap.deal.id} />
      ) : null}
    </section>
  );
}
