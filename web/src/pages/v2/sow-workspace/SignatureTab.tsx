import { Button } from "../../../ui-v2/primitives/button";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";

interface Check {
  id: string;
  label: string;
  status: StatusTone;
  statusLabel: string;
  hint?: string;
}

/**
 * Signature tab — every pre-release check listed as an independent line.
 * When Send is held the user sees the specific reason; disabled without
 * explanation is banned by spec §4.
 */
export function SignatureTab({ snap }: { snap: WorkspaceSnapshot }) {
  const checks: Check[] = [];
  const nda = snap.agreements.find(
    (a) => a.kind === "NDA" && a.state === "executed",
  );
  const msa = snap.agreements.find(
    (a) => a.kind === "MSA" && a.state === "executed",
  );
  checks.push({
    id: "nda",
    label: "NDA coverage",
    status: nda ? "ok" : "danger",
    statusLabel: nda ? "In force" : "Missing",
    hint: nda
      ? undefined
      : "Register the executed NDA in the Agreements register.",
  });
  checks.push({
    id: "msa",
    label: "MSA coverage",
    status: msa ? "ok" : "danger",
    statusLabel: msa ? "In force" : "Missing",
  });

  const pkg = snap.approvalPackage;
  const approvedFns = new Set(
    (pkg?.approvals ?? [])
      .filter((a) => a.decision === "approve")
      .map((a) => a.function),
  );
  for (const fn of ["delivery", "hr", "finance", "legal"] as const) {
    const ok = approvedFns.has(fn);
    checks.push({
      id: `fn-${fn}`,
      label: `${fn[0].toUpperCase()}${fn.slice(1)} approval`,
      status: ok ? "ok" : "warn",
      statusLabel: ok ? "Approved" : "Pending",
    });
  }

  const ceoRequired = pkg?.floors?.requires_ceo === true;
  if (ceoRequired) {
    const ceoDone =
      pkg?.status === "ready_to_sign" || pkg?.status === "released";
    checks.push({
      id: "ceo",
      label: "CEO exception on file",
      status: ceoDone ? "ok" : "danger",
      statusLabel: ceoDone ? "Recorded" : "Missing",
      hint: ceoDone ? undefined : "Route to the CEO exception decision page.",
    });
  }

  const signed = snap.signedSow;
  checks.push({
    id: "conditions",
    label: "Pre-signature conditions",
    status:
      pkg && (pkg.status === "ready_to_sign" || pkg.status === "released")
        ? "ok"
        : "warn",
    statusLabel:
      pkg && (pkg.status === "ready_to_sign" || pkg.status === "released")
        ? "Met"
        : "Outstanding",
  });
  checks.push({
    id: "outgoing",
    label: "Outgoing document version",
    status: snap.sow ? "ok" : "danger",
    statusLabel: snap.sow ? snap.sow.file_hash.slice(0, 8) : "Missing",
  });
  checks.push({
    id: "signatories",
    label: "Signatories verified",
    status: signed?.verify_status === "verified" ? "ok" : "warn",
    statusLabel:
      signed?.verify_status === "verified"
        ? "Verified"
        : "Not yet verified",
  });

  const failing = checks.filter((c) => c.status !== "ok");
  const canSend = failing.length === 0;

  return (
    <div className="space-y-4" style={{ maxWidth: "960px" }}>
      <section
        aria-label="Signature checks"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h2 className="text-section text-text mb-3">Signature checks</h2>
        <ul className="divide-y divide-divider">
          {checks.map((c) => (
            <li key={c.id} className="py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-body text-text">{c.label}</span>
                <StatusBadge tone={c.status} label={c.statusLabel} />
              </div>
              {c.hint ? (
                <p className="text-secondary text-text-secondary mt-1">
                  {c.hint}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <section
        aria-label="Send"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-section text-text">Send for signature</h2>
            {canSend ? (
              <p className="text-body text-text-secondary">
                All pre-signature checks pass — this will send the exact
                package version above.
              </p>
            ) : (
              <p className="text-body text-danger">
                Held: {failing.map((f) => f.label).join(" · ")}
              </p>
            )}
          </div>
          <Button
            type="button"
            disabled={!canSend}
            aria-label="Send for signature"
          >
            Send for signature
          </Button>
        </div>
      </section>
    </div>
  );
}
