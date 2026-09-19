import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";

interface HandoffRow {
  id: string;
  label: string;
  status: StatusTone;
  statusLabel: string;
  hint?: string;
}

export function HandoffTab({ snap }: { snap: WorkspaceSnapshot }) {
  const signed = snap.signedSow;
  const executed = signed?.verify_status === "verified";
  const released = signed?.released_at != null;

  const rows: HandoffRow[] = [
    {
      id: "verify",
      label: "Execution verification",
      status: executed ? "ok" : "warn",
      statusLabel: executed ? "Verified" : "Awaiting signed PDF",
      hint: executed ? undefined : "Upload the countersigned PDF in Signature.",
    },
    {
      id: "release",
      label: "Handoff release",
      status: released ? "ok" : "warn",
      statusLabel: released ? "Released" : "Not released",
    },
    {
      id: "distribution",
      label: "Distribution recipients & receipts",
      status: released ? "ok" : "neutral",
      statusLabel: released ? "Notified" : "Pending",
    },
    {
      id: "delivery_ack",
      label: "Account / Delivery acknowledgement",
      status: released ? "ok" : "neutral",
      statusLabel: released ? "Acknowledged" : "Pending",
    },
    {
      id: "billing",
      label: "Billing / PO setup",
      status: released ? "ok" : "neutral",
      statusLabel: released ? "Configured" : "Pending",
    },
    {
      id: "renewal",
      label: "Renewal record created",
      status: released ? "ok" : "neutral",
      statusLabel: released ? "Created" : "Pending",
    },
  ];

  const anyIncomplete = rows.some((r) => r.status !== "ok");

  return (
    <div className="space-y-4" style={{ maxWidth: "960px" }}>
      <section
        aria-label="Handoff status"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-section text-text">Handoff status</h2>
          {anyIncomplete ? (
            <StatusBadge tone="warn" label="In progress" />
          ) : (
            <StatusBadge tone="ok" label="Complete" />
          )}
        </div>
        <p className="text-secondary text-text-secondary mt-1">
          Handoff is only marked complete once every downstream system has
          acknowledged.
        </p>
      </section>
      <section
        aria-label="Handoff checklist"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <ul className="divide-y divide-divider">
          {rows.map((r) => (
            <li key={r.id} className="py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-body text-text">{r.label}</span>
                <StatusBadge tone={r.status} label={r.statusLabel} />
              </div>
              {r.hint ? (
                <p className="text-secondary text-text-secondary mt-1">
                  {r.hint}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
