import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, RotateCcw, X, RefreshCw } from "lucide-react";
import { decideApprovalPackage, routeMissingApprovals, recordConditionEvidence, type ApprovalAssignment, type ApprovalDecision, type ApprovalPackage } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { reviewError } from "./SubmitApprovalDialog";
import type { WorkspaceSnapshot } from "./readiness";

const labels = { delivery: "Delivery", hr: "HR", finance: "Finance", legal: "Legal" };
const versions = (pkg: ApprovalPackage) => `SOW v${pkg.sow_version ?? "?"} · GM v${pkg.gm_version ?? "?"} · ${pkg.package_hash.slice(0, 12)}`;
const when = (time: string | null) => time ? new Date(time).toLocaleString() : "";

export function ApprovalsTab({ snap, refresh, updatedAt = Date.now(), canSubmit = false }: {
  snap: WorkspaceSnapshot; refresh?: () => Promise<void>; updatedAt?: number; canSubmit?: boolean;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const packages = snap.approvalHistory ?? (snap.approvalPackage ? [snap.approvalPackage] : []);
  return <div className="space-y-5">
    <div className="flex items-center justify-between gap-2"><h2 className="text-section">Review stream</h2><span className="text-secondary text-text-secondary">Updated {Math.max(0, Math.floor((now - updatedAt) / 1000))}s ago</span></div>
    {!packages.length && <p className="text-body text-text-secondary">No reviews submitted.</p>}
    {packages.map(pkg => <PackageStream key={pkg.id} pkg={pkg} refresh={refresh} canSubmit={canSubmit} />)}
  </div>;
}

function PackageStream({ pkg, refresh, canSubmit }: { pkg: ApprovalPackage; refresh?: () => Promise<void>; canSubmit: boolean }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [evidence, setEvidence] = useState("");
  const exception = pkg.ceo_exception;
  const closed = ["rejected", "voided", "released"].includes(pkg.status);
  async function route() {
    setBusy(true); setError("");
    try { await routeMissingApprovals(pkg.id); await refresh?.(); } catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  async function recordEvidence() {
    setBusy(true); setError("");
    try { await recordConditionEvidence(pkg.id, evidence); await refresh?.(); setEvidence(""); } catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  const decisions = [...pkg.approvals].sort((a, b) => (b.decided_at ?? "").localeCompare(a.decided_at ?? ""));
  const pending = (pkg.assignments ?? []).filter(a => !pkg.approvals.some(d => d.function === a.function)).sort((a, b) => Number(b.active) - Number(a.active) || Object.keys(labels).indexOf(a.function) - Object.keys(labels).indexOf(b.function));
  return <section aria-label={`Package ${versions(pkg)}`} className="border-t border-divider pt-4 space-y-3">
    <div className="flex flex-wrap justify-between gap-2"><span className="text-secondary text-text-secondary break-all">{versions(pkg)}</span><StatusBadge tone={closed ? "neutral" : "warn"} label={pkg.status.replaceAll("_", " ")} /></div>
    {error && <p role="alert" className="text-danger">{error}</p>}
    {!!pkg.routing_blockers?.length && <div className="border-l-2 border-warning pl-3 text-body"><ul>{pkg.routing_blockers.map(b => <li key={b}>{b}</li>)}</ul><Link to="/settings/people?tab=groups" className="text-primary underline">Open groups</Link>{canSubmit && <Button variant="secondary" disabled={busy} className="ml-3" onClick={route}><RefreshCw className="h-4 w-4 mr-2" />Route configured reviewers</Button>}</div>}
    {exception && <article className="border border-divider rounded-panel p-4 space-y-2">
      <h3 className="font-medium">CEO {exception.decision ? exception.decision.replaceAll("_", " ") : "decision pending"}</h3>
      {!exception.decision && <p className="text-body">Pending with {pkg.ceo_pending_with ?? "Executive group"}</p>}
      <p className="text-secondary text-text-secondary">{versions(pkg)} · {exception.decided_by_name} {when(exception.decided_at)}</p>
      {exception.rationale_text && <p className="text-body whitespace-pre-wrap">{exception.rationale_text}</p>}
      {exception.conditions_text && <p className="text-body">{exception.conditions_unmet ? "Blocked: " : "Conditions: "}{exception.conditions_text} · Owner: {pkg.owner?.name ?? "Account owner"}</p>}
      {exception.expired && <p className="text-danger">CEO exception expired. A new review is required.</p>}
      {exception.evidence && <p className="text-body">Evidence: {exception.evidence}</p>}
      {exception.conditions_unmet && <p className="text-secondary text-text-secondary">Evidence needed: documentation that the CEO's conditions have been satisfied.</p>}
      {exception.conditions_unmet && canSubmit && <div className="space-y-2"><textarea aria-label="Condition evidence" className="w-full border border-divider rounded-control p-2" value={evidence} onChange={e => setEvidence(e.target.value)} /><Button disabled={busy || !evidence.trim()} onClick={recordEvidence}>Record condition evidence</Button></div>}
      <Link className="text-primary underline text-body" to={`/ceo-exceptions/${exception.id}`}>Open CEO exception</Link>
    </article>}
    {!exception && pkg.floors?.requires_ceo && <p className="text-body border-l-2 border-warning pl-3">CEO exception queued after functional reviews · {versions(pkg)}</p>}
    {decisions.map(d => <article key={d.id} className="border border-divider rounded-panel p-4 space-y-2">
      <h3 className="font-medium text-body">{labels[d.function]} · {d.decision === "approve" ? "Approved" : d.decision === "request_changes" ? "Changes requested" : "Rejected"}</h3>
      <p className="text-secondary text-text-secondary">{d.approver_name ?? "Reviewer"} · {when(d.decided_at)} · {versions(pkg)}</p>
      <p className="whitespace-pre-wrap text-body">{d.reason}</p>
    </article>)}
    {pending.map(a => <article key={a.function} className="border border-divider rounded-panel p-4 space-y-2" data-testid={`review-${a.function}`}>
      <div className="flex gap-3 items-center"><span aria-hidden className="w-8 h-8 shrink-0 rounded-full bg-primary-subtle text-primary flex items-center justify-center text-secondary">{a.approver_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()}</span><div className="min-w-0"><h3 className="font-medium text-body">{labels[a.function]} · {closed ? "Review closed" : a.blocked ? "Blocked - SystemAdmin" : `${a.active ? "Pending with" : "Queued for"} ${a.approver_name}`}</h3><p className="text-secondary text-text-secondary">Due {a.due_date} · {Math.max(0, Math.floor((Date.now() - new Date(pkg.submitted_at ?? Date.now()).getTime()) / 86400000))}d · {versions(pkg)}</p></div></div>
      {a.can_decide && <ReviewActions pkg={pkg} assignment={a} refresh={refresh} />}
    </article>)}
    <p className="text-body text-text-secondary">Submitted by {pkg.submitted_by_name ?? "Account owner"} · {when(pkg.submitted_at)} · {versions(pkg)}</p>
  </section>;
}

function ReviewActions({ pkg, assignment, refresh }: { pkg: ApprovalPackage; assignment: ApprovalAssignment; refresh?: () => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(decision: ApprovalDecision) {
    setBusy(true); setError("");
    try { await decideApprovalPackage(pkg.id, assignment.function, { decision, reason: reason.trim() }); await refresh?.(); }
    catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  return <div className="space-y-2 pt-2">
    <label className="text-secondary">Reason (required)<textarea aria-label={`${labels[assignment.function]} reason`} maxLength={4096} className="block mt-1 w-full border border-divider rounded-control p-2 text-body" value={reason} onChange={e => setReason(e.target.value)} /></label>
    {error && <p role="alert" className="text-danger text-body">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={busy || !reason.trim()} onClick={() => act("approve")}><Check className="h-4 w-4 mr-2" />Approve</Button>
      <Button variant="secondary" disabled={busy || !reason.trim()} onClick={() => act("request_changes")}><RotateCcw className="h-4 w-4 mr-2" />Request changes</Button>
      <Button variant="secondary" disabled={busy || !reason.trim()} onClick={() => act("reject")}><X className="h-4 w-4 mr-2" />Reject</Button>
    </div>
  </div>;
}
