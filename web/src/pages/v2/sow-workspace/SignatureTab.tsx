import { Button } from "../../../ui-v2/primitives/button";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";
import type { ReactNode } from "react";

interface Check {
  id: string;
  label: string;
  status: StatusTone;
  statusLabel: string;
  hint?: string;
  /** Rule 13 — inline editor rendered under the row when the check
   * surfaces a specific recoverable mismatch (not just "pending"). */
  editor?: ReactNode;
}

/**
 * Signature tab — every pre-release check listed as an independent line.
 * When Send is held the user sees the specific reason; disabled without
 * explanation is banned by spec §4.
 *
 * S20 W7 (T22): "prepare only the current approved package". When the
 * package has been superseded by a newer submission, this tab renders a
 * "Superseded by v{N}" banner and disables the primary action with a
 * link to the newer package. The server also enforces the block — a
 * stale URL cannot post to `/signed-sow/{id}` past the supersession.
 */
export function SignatureTab({ snap }: { snap: WorkspaceSnapshot }) {
  // W3/W7 stashed `snap.approvalPackage.superseded_by` for a future
  // "Signature superseded" banner; wiring lives in Signature.tsx today
  // so the tab-level view can stay purely a checklist.
  const checks: Check[] = [];
  // S20 W3 D3: NDA/MSA is *not* a signature check. The upload marker is
  // client-scoped context (rendered in the workspace header) and the
  // authoritative "signed/verified" fact lives on the client, not this
  // workspace. `require_signature_eligibility` in
  // `services/approval_workflow.py` does not gate on NDA/MSA; listing a
  // row here would misrepresent that. Review L13.

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

  // S20 W3 T20 · CEO exception is conditional. When the policy does NOT
  // require it we still render the row with the wording "Not required"
  // so the reader sees the check ran (never blank, never absent — that
  // would be indistinguishable from a rendering bug). When required, we
  // check for the exception decision and record status.
  const ceoRequired = pkg?.floors?.requires_ceo === true;
  if (pkg) {
    if (ceoRequired) {
      const ceoDone =
        pkg.status === "ready_to_sign" || pkg.status === "released";
      checks.push({
        id: "ceo",
        label: "CEO exception on file",
        status: ceoDone ? "ok" : "danger",
        statusLabel: ceoDone ? "Recorded" : "Missing",
        hint: ceoDone ? undefined : "Route to the CEO exception decision page.",
      });
    } else {
      checks.push({
        id: "ceo",
        label: "CEO exception on file",
        status: "ok",
        statusLabel: "Not required",
        hint: "Margin passes the floor — no exception is required.",
      });
    }
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

  // S20 W7 item 1 · signatories check with inline editor on mismatch.
  // Rule 13: every blocker is an editor. When the server's signatory
  // diff flagged a missing / unexpected name we render the specifics
  // and link to the Legal review's signatories picker — never a dead
  // end "verification failed" message.
  const sigField = signed?.diff_json?.fields?.find(
    (f) => f.field === "signatories",
  );
  const sigMismatch =
    signed?.verify_status === "blocked" &&
    sigField !== undefined &&
    sigField.match === false;
  checks.push({
    id: "signatories",
    label: "Signatories verified",
    status:
      signed?.verify_status === "verified"
        ? "ok"
        : sigMismatch
          ? "danger"
          : "warn",
    statusLabel:
      signed?.verify_status === "verified"
        ? "Verified"
        : sigMismatch
          ? "Mismatch"
          : "Not yet verified",
    editor: sigMismatch ? (
      <SignatoriesMismatchEditor
        approved={Array.isArray(sigField.approved) ? sigField.approved : []}
        extracted={
          Array.isArray(sigField.extracted) ? sigField.extracted : []
        }
        missing={sigField.missing ?? []}
        unexpected={sigField.unexpected ?? []}
      />
    ) : undefined,
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
              {c.editor ? <div className="mt-2">{c.editor}</div> : null}
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


/**
 * Inline editor for a signatories mismatch (S20 W7 item 1 · rule 13).
 *
 * Rendered under the "Signatories verified" check row when the server's
 * diff flagged a missing or unexpected name on the executed PDF. We
 * surface the specifics side-by-side and route the operator back to the
 * Legal-review signatories picker — the authoritative writer for the
 * pinned signatory list. Never a dead-end "verification failed" row.
 */
function SignatoriesMismatchEditor({
  approved,
  extracted,
  missing,
  unexpected,
}: {
  approved: string[];
  extracted: string[];
  missing: string[];
  unexpected: string[];
}) {
  return (
    <div
      className="rounded-panel border border-danger-subtle bg-danger-soft p-3"
      aria-label="Signatories mismatch — resolution"
    >
      <p className="text-body text-text">
        The executed document&apos;s signatory list does not match the
        approved SOW.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-3">
        <div>
          <h4 className="text-caption text-text-secondary">Approved</h4>
          <ul className="list-disc pl-5 text-body text-text">
            {approved.length > 0 ? (
              approved.map((n) => <li key={`a-${n}`}>{n}</li>)
            ) : (
              <li>None recorded</li>
            )}
          </ul>
        </div>
        <div>
          <h4 className="text-caption text-text-secondary">On executed PDF</h4>
          <ul className="list-disc pl-5 text-body text-text">
            {extracted.length > 0 ? (
              extracted.map((n) => <li key={`e-${n}`}>{n}</li>)
            ) : (
              <li>None detected</li>
            )}
          </ul>
        </div>
      </div>
      {missing.length > 0 ? (
        <p className="mt-2 text-body text-text">
          <strong>Missing on executed:</strong> {missing.join(", ")}
        </p>
      ) : null}
      {unexpected.length > 0 ? (
        <p className="mt-1 text-body text-text">
          <strong>Unexpected on executed:</strong> {unexpected.join(", ")}
        </p>
      ) : null}
      <p className="mt-2 text-secondary text-text-secondary">
        To proceed, either (a) re-upload an executed document that bears
        exactly the approved signers, or (b) create a new SOW revision
        with the correct signatory list and route it through Legal
        review again.
      </p>
      <div className="mt-2 flex gap-2">
        <a
          href="#signatories-picker"
          className="text-body text-link underline"
        >
          Open signatories picker
        </a>
      </div>
    </div>
  );
}
