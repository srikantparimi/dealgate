import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Send } from "lucide-react";
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
  const [busy, setBusy] = useState(false);
  return <Dialog open={open} onOpenChange={v => { if (!busy) onOpenChange(v); }}>
    <DialogContent className="max-w-2xl max-h-[90dvh] overflow-y-auto w-[calc(100%-2rem)]">
      <DialogTitle>Submit for approval</DialogTitle>
      <DialogDescription className="sr-only">Reviewer plan</DialogDescription>
      {open && <SubmissionPlanEditor key={id} id={id} onBusyChange={setBusy}
        onCancel={() => onOpenChange(false)} onSubmitted={() => { onOpenChange(false); onSubmitted(); }} />}
    </DialogContent>
  </Dialog>;
}

export function SubmissionPlanEditor({ id, onSubmitted, onCancel, onBusyChange }: {
  id: string; onSubmitted: () => void | Promise<void>; onCancel?: () => void; onBusyChange?: (busy: boolean) => void;
}) {
  const [plan, setPlan] = useState<SubmissionPlan | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    let current = true;
    setPlan(null); setError("");
    getSubmissionPlan(id).then(p => { if (current) setPlan(p); }).catch(e => { if (current) setError(reviewError(e)); });
    return () => { current = false; generation.current += 1; };
  }, [id]);
  async function submit() {
    if (!plan) return;
    const submittedGeneration = generation.current;
    setBusy(true); onBusyChange?.(true); setError("");
    try {
      await submitApprovalPackage(id, {
        sow_version_id: plan.sow_version_id, gm_model_id: plan.gm_model_id,
        assignments: Object.fromEntries(plan.rows.map(r => [r.function, { approver_id: r.approver_id, due_date: r.due_date, use_sla: r.use_sla }])),
      });
      if (submittedGeneration === generation.current) await onSubmitted();
    } catch (e) { if (submittedGeneration === generation.current) setError(reviewError(e)); }
    finally { setBusy(false); onBusyChange?.(false); }
  }
  return <section aria-label="Planned reviewers" className="space-y-3">
      <h3 className="text-heading-3">Planned reviewers</h3>
      <p className="text-secondary text-text-secondary">{plan ? `Frozen package: SOW v${plan.sow_version} · GM v${plan.gm_version}` : "Loading review assignments"}</p>
      {error && <p role="alert" className="text-danger text-body">{error}</p>}
      {plan && <>
        <p className="text-secondary text-text-secondary">You are excluded from reviewer choices because the submitter cannot approve this package. Each function requires a different reviewer.</p>
        <ApprovalPipeline plan={plan} />
        <div className="divide-y divide-divider">
          {plan.rows.map((row, index) => <div key={row.function} className="py-3 grid gap-2 sm:grid-cols-[90px_1fr_145px] items-center">
            <span className="font-medium text-body">{row.label}</span>
            <select disabled={busy} aria-label={`${row.label} approver`} className="min-w-0 border border-divider rounded-control bg-surface p-2 text-body" value={row.approver_id ?? ""}
              onChange={e => setPlan({ ...plan, rows: plan.rows.map((r, i) => i === index ? { ...r, approver_id: e.target.value || null } : r) })}>
              <option value="">Unrouted - admin action needed</option>
              {row.members.map(m => <option key={m.id} value={m.id} disabled={plan.rows.some(r => r.function !== row.function && r.approver_id === m.id)}>{m.name}</option>)}
            </select>
            <input disabled={busy} aria-label={`${row.label} due date`} type="date" min={new Date().toISOString().slice(0, 10)} className="min-w-0 border border-divider rounded-control bg-surface p-2 text-body" value={row.due_date}
              onChange={e => setPlan({ ...plan, rows: plan.rows.map((r, i) => i === index ? { ...r, due_date: e.target.value, use_sla: false } : r) })} />
            {!row.approver_id && <p className="sm:col-span-3 text-warning text-secondary">{row.label} cannot route until an eligible reviewer is assigned. Owner: SystemAdmin.</p>}
          </div>)}
          {plan.executive && <div className="py-3 text-body"><strong>CEO · {plan.executive.members.find(m => m.id === plan.executive?.approver_id)?.name ?? "Executive group needs a CEO or active delegate"}</strong><p className="text-secondary text-text-secondary">Exception - brief will be generated after functional reviews.</p></div>}
        </div>
        <div className="flex justify-end gap-2">{onCancel && <Button variant="secondary" disabled={busy} onClick={onCancel}>Cancel</Button>}<Button onClick={submit} disabled={busy || plan.rows.some(r => !r.due_date || !r.approver_id)}><Send className="h-4 w-4 mr-2" />{busy ? "Submitting..." : "Confirm submission"}</Button></div>
      </>}
  </section>;
}

function ApprovalPipeline({ plan }: { plan: SubmissionPlan }) {
  const executive = plan.executive;
  const executiveMember = executive?.members.find(
    (member) => member.id === executive.approver_id,
  );
  const stages = [
    {
      number: 1,
      label: "Function reviews",
      functions: ["delivery", "sales", "hr"],
    },
    {
      number: 2,
      label: "Commercial and legal reviews",
      functions: ["finance", "legal"],
    },
  ];
  return (
    <section aria-label="Approval pipeline" className="border-y border-divider py-4">
      <h4 className="text-heading-3">Approval pipeline</h4>
      <div className="mt-4 grid gap-4">
        {stages.map((stage) => (
          <div key={stage.number} className="grid grid-cols-[32px_minmax(0,1fr)] gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-fg font-semibold tnum">{stage.number}</span>
            <div className="min-w-0">
              <p className="font-medium text-body">Stage {stage.number} · {stage.label}</p>
              <div className="mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                {stage.functions.map((fn) => plan.rows.find((row) => row.function === fn)).filter((row) => row !== undefined).map((row) => {
                const member = row.members.find((item) => item.id === row.approver_id);
                return (
                  <div key={row.function} className="flex min-w-0 items-start gap-2 border-l-2 border-primary pl-3">
                    {member ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />}
                    <div className="min-w-0">
                      <p className="font-medium text-body">{row.label}</p>
                      <p className="truncate text-secondary text-text-secondary">{member?.name ?? "No eligible reviewer"}</p>
                      {member?.email ? <p className="truncate text-secondary text-text-muted">{member.email}</p> : null}
                    </div>
                  </div>
                );
                })}
              </div>
            </div>
          </div>
        ))}
        {executive ? (
          <div className="grid grid-cols-[32px_minmax(0,1fr)] gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-warning text-text font-semibold tnum">3</span>
            <div className="min-w-0 border-l-2 border-warning pl-3">
              <p className="font-medium text-body">Stage 3 · CEO exception</p>
              <p className="text-secondary text-text-secondary">{executiveMember?.name ?? "No eligible CEO or delegate"}</p>
              {executiveMember?.email ? <p className="text-secondary text-text-muted">{executiveMember.email}</p> : null}
              <p className="text-secondary text-text-secondary">Added because the saved GM is below a configured floor.</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-[32px_minmax(0,1fr)] gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-success-surface text-success"><CheckCircle2 className="h-4 w-4" aria-hidden /></span>
            <div className="min-w-0 border-l-2 border-success pl-3">
              <p className="font-medium text-body">CEO approval is not required</p>
              <p className="text-secondary text-text-secondary">The saved GM meets the configured margin floors.</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
