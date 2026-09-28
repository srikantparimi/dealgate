import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { ApiError, getSubmissionPlan, submitApprovalPackage, type SubmissionPlan } from "../../../api/client";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../../../ui-v2/primitives/dialog";
import { Button } from "../../../ui-v2/primitives/button";

export function reviewError(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === "string") return error.detail;
  return error instanceof Error ? error.message : "The review could not be saved. Please retry.";
}

export function SubmitApprovalDialog({ id, open, onOpenChange, onSubmitted }: {
  id: string; open: boolean; onOpenChange: (open: boolean) => void; onSubmitted: () => void;
}) {
  const [plan, setPlan] = useState<SubmissionPlan | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    let current = true;
    setPlan(null); setError("");
    getSubmissionPlan(id).then(p => { if (current) setPlan(p); }).catch(e => { if (current) setError(reviewError(e)); });
    return () => { current = false; };
  }, [id, open]);
  async function submit() {
    if (!plan) return;
    setBusy(true); setError("");
    try {
      await submitApprovalPackage(id, {
        sow_version_id: plan.sow_version_id, gm_model_id: plan.gm_model_id,
        assignments: Object.fromEntries(plan.rows.map(r => [r.function, { approver_id: r.approver_id, due_date: r.due_date, use_sla: r.use_sla }])),
      });
      onOpenChange(false); onSubmitted();
    } catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  return <Dialog open={open} onOpenChange={v => { if (!busy) onOpenChange(v); }}>
    <DialogContent className="max-w-2xl max-h-[90dvh] overflow-y-auto w-[calc(100%-2rem)]">
      <DialogTitle>Submit for approval</DialogTitle>
      <DialogDescription>{plan ? `Frozen package: SOW v${plan.sow_version} · GM v${plan.gm_version}` : "Loading review assignments"}</DialogDescription>
      {error && <p role="alert" className="text-danger text-body">{error}</p>}
      {plan && <>
        <p className="text-secondary text-text-secondary">You are excluded from reviewer choices because the submitter cannot approve this package. Each function requires a different reviewer.</p>
        <div className="divide-y divide-divider">
          {plan.rows.map((row, index) => <div key={row.function} className="py-3 grid gap-2 sm:grid-cols-[90px_1fr_145px] items-center">
            <span className="font-medium text-body">{row.label}</span>
            <select aria-label={`${row.label} approver`} className="min-w-0 border border-divider rounded-control bg-surface p-2 text-body" value={row.approver_id ?? ""}
              onChange={e => setPlan({ ...plan, rows: plan.rows.map((r, i) => i === index ? { ...r, approver_id: e.target.value || null } : r) })}>
              <option value="">Unrouted - admin action needed</option>
              {row.members.map(m => <option key={m.id} value={m.id} disabled={plan.rows.some(r => r.function !== row.function && r.approver_id === m.id)}>{m.name}</option>)}
            </select>
            <input aria-label={`${row.label} due date`} type="date" min={new Date().toISOString().slice(0, 10)} className="min-w-0 border border-divider rounded-control bg-surface p-2 text-body" value={row.due_date}
              onChange={e => setPlan({ ...plan, rows: plan.rows.map((r, i) => i === index ? { ...r, due_date: e.target.value, use_sla: false } : r) })} />
            {!row.approver_id && <p className="sm:col-span-3 text-warning text-secondary">{row.label} cannot route until an eligible reviewer is assigned. Owner: SystemAdmin.</p>}
          </div>)}
          {plan.executive && <div className="py-3 text-body"><strong>CEO · {plan.executive.members.find(m => m.id === plan.executive?.approver_id)?.name ?? "Executive group needs a CEO or active delegate"}</strong><p className="text-secondary text-text-secondary">Exception - brief will be generated after functional reviews.</p></div>}
        </div>
        <div className="flex justify-end gap-2"><Button variant="secondary" disabled={busy} onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={submit} disabled={busy || plan.rows.some(r => !r.due_date)}><Send className="h-4 w-4 mr-2" />{busy ? "Submitting..." : "Confirm submission"}</Button></div>
      </>}
    </DialogContent>
  </Dialog>;
}
