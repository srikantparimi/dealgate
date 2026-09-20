import type { AgreementRow } from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";
import { SowVersionHistory } from "./SowVersionHistory";

const STATE_TONE: Record<AgreementRow["state"], StatusTone> = {
  missing: "warn",
  requested: "warn",
  drafting: "warn",
  under_review: "warn",
  sent: "warn",
  partially_signed: "warn",
  executed: "ok",
  expired: "danger",
  terminated: "danger",
  superseded: "neutral",
};

/**
 * Documents: the mother documents and the SOW.
 *
 * MSA and NDA are per legal entity, long-lived, and carry their own state
 * machine — the table below. A SOW belongs to one engagement and is revised
 * during negotiation, so it gets a version chain instead, rendered under it.
 */
export function DocumentsTab({ snap }: { snap: WorkspaceSnapshot }) {
  const rows = [
    ...snap.agreements.map((a) => ({
      id: a.id,
      kind: a.kind as string,
      coverage: `${a.effective_from ?? "—"} → ${a.expiry ?? "—"}`,
      version: a.evidence_s3_key?.slice(-8) ?? "—",
      state: a.state as AgreementRow["state"],
    })),
  ];
  if (snap.sow) {
    rows.push({
      id: snap.sow.id,
      kind: "SOW",
      coverage: `Version ${snap.sow.id.slice(-8)}`,
      version: snap.sow.file_hash.slice(0, 8),
      state:
        snap.sow.confirmed_at != null
          ? ("executed" as AgreementRow["state"])
          : ("drafting" as AgreementRow["state"]),
    });
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No agreements registered"
        description="Register the NDA/MSA in the Agreements register to unlock signature."
      />
    );
  }

  return (
    <section
      aria-label="Documents"
      className="rounded-panel border border-divider bg-surface p-4"
      style={{ maxWidth: "960px" }}
    >
      <h2 className="text-section text-text mb-3">Documents</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full text-body">
          <thead>
            <tr className="text-left text-text-secondary text-secondary uppercase">
              <th className="py-2 pr-4">Kind</th>
              <th className="py-2 pr-4">Coverage</th>
              <th className="py-2 pr-4">Version</th>
              <th className="py-2 pr-4">State</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-divider">
                <td className="py-2 pr-4 text-text">{r.kind}</td>
                <td className="py-2 pr-4 text-text">{r.coverage}</td>
                <td className="py-2 pr-4 tnum text-text">{r.version}</td>
                <td className="py-2 pr-4">
                  <StatusBadge
                    tone={STATE_TONE[r.state] ?? "neutral"}
                    label={r.state.replace("_", " ")}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {snap.deal?.id ? (
        <SowVersionHistory opportunityId={snap.deal.id} />
      ) : null}
    </section>
  );
}
