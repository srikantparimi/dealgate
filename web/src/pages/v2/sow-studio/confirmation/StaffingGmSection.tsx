import { useEffect, useRef, useState } from "react";
import { Save } from "lucide-react";
import { getSowStaffing, previewDeliveryModel, putSowStaffing, type DeliveryCostLineInput, type SowConfirmationPayload, type SowResourcesState } from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { formatQuantity, formatRate } from "../../sow-workspace/format";
import { FinanceGmPanel, type FinanceGmResult } from "../../sow-workspace/staffing/FinanceGmPanel";
import { costsComplete, DirectCostsEditor, proposalCosts } from "../../sow-workspace/staffing/DirectCostsEditor";
import { isFixedFee } from "../../sow-staffing/StaffingGate";
import { Section } from "./Section";
import { ProvenanceChip } from "./provenance";

export interface StaffingGmSectionProps {
  payload: SowConfirmationPayload;
  opportunityId?: string;
  onSaved?: () => void | Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
}

export function formatAllocationPct(raw: string | number): string {
  const n = Number(raw);
  return Number.isFinite(n) ? (n * 100).toLocaleString("en-US", { maximumFractionDigits: 1 }) : String(raw);
}

export function StaffingGmSection({ payload, opportunityId, onSaved, onDirtyChange }: StaffingGmSectionProps) {
  const [costs, setCosts] = useState<DeliveryCostLineInput[]>(() => payload.gm_model?.cost_lines?.length ? payload.gm_model.cost_lines : proposalCosts(payload.direct_cost_proposals));
  const [state, setState] = useState<SowResourcesState | null>(null);
  const [preview, setPreview] = useState<FinanceGmResult | null>(null);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [reason, setReason] = useState("");
  const lines = payload.staffing.lines;
  const fixedFee = isFixedFee(payload.engagement.primary.type);

  useEffect(() => {
    if (!opportunityId) return;
    dirtyRef.current = false;
    setDirty(false); setCosts([]); setPreview(null); setState(null);
    onDirtyChange?.(false);
  }, [opportunityId]);

  useEffect(() => {
    if (!opportunityId) return;
    let active = true;
    getSowStaffing(opportunityId).then((res) => {
      if (!active) return;
      setState(res);
      if (dirtyRef.current) return;
      setCosts(res.cost_lines?.length ? res.cost_lines : proposalCosts(res.direct_cost_proposals ?? payload.direct_cost_proposals));
      const proposed = !res.cost_lines?.length && (res.direct_cost_proposals ?? payload.direct_cost_proposals ?? []).length > 0;
      setDirty(proposed);
      dirtyRef.current = proposed;
      onDirtyChange?.(proposed);
    }).catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : "Could not load direct costs"); });
    return () => { active = false; };
  }, [opportunityId, payload.gm_model?.id]);

  useEffect(() => {
    if (!dirty || !state?.resource_lines || !costsComplete(costs)) { setPreview(null); return; }
    let active = true;
    const timer = setTimeout(() => {
      previewDeliveryModel({ engagement_type: payload.engagement.primary.type, inputs: { resource_lines: state.resource_lines!, cost_lines: costs, ...(state.total_price ? { total_price: state.total_price } : {}) } }).then((res) => {
        if (active) { setPreview({ ...res.computed, ...res.computed.policy, gm_version: state.margin.gm_version }); setError(null); }
      }).catch((e: unknown) => { if (active) { setPreview(null); setError(e instanceof Error ? e.message : "Could not preview direct costs"); } });
    }, 400);
    return () => { active = false; clearTimeout(timer); };
  }, [costs, dirty, state, payload.engagement.primary.type]);

  function changeCosts(next: DeliveryCostLineInput[]) {
    setCosts(next); setDirty(true); dirtyRef.current = true; setPreview(null); onDirtyChange?.(true);
  }
  async function save() {
    if (!state || !opportunityId) return;
    setBusy(true); setError(null);
    try {
      await putSowStaffing(opportunityId, { engagement_type: state.engagement_type ?? payload.engagement.primary.type, cost_lines: costs, ...(state.requires_notice_on_change ? { effective_from: effectiveFrom, reason } : {}) });
      setDirty(false); dirtyRef.current = false; onDirtyChange?.(false); setPreview(null); await onSaved?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save direct costs"); }
    finally { setBusy(false); }
  }
  const result = preview ?? (dirty ? { gm_version: payload.floors.gm_version } : { ...payload.floors, gm_version: payload.floors.gm_version ?? payload.gm_model?.version, revenue_total: payload.floors.revenue_total ?? (lines.some((line) => line.location === "India") ? undefined : payload.gm_model?.revenue_us) });
  return <Section id="section-staffing" title="Staffing & GM">
    <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <div className="min-w-0 space-y-5">
        {lines.length ? <div className="overflow-x-auto"><table aria-label="Staffing grid" className="w-full min-w-[720px] text-secondary tnum">
          <thead className="border-b border-divider bg-surface-sunken text-left text-text-secondary"><tr>{["Role · seniority", "Location", "Bill rate", "Cost /hr", "Hours", "Allocation", "Provenance"].map((title) => <th key={title} className="px-3 py-2 font-medium">{title}</th>)}</tr></thead>
          <tbody>{lines.map((line, i) => <tr key={i} className="border-b border-divider"><td className="px-3 py-2"><span className="font-medium">{line.role}</span><span className="ml-2 text-text-secondary">{line.seniority}</span></td><td className="px-3 py-2">{line.location}</td><td className="whitespace-nowrap px-3 py-2 text-right">{fixedFee ? "— fixed price" : formatRate(line.hourly_bill_rate)}</td><td className="px-3 py-2 text-right">{formatRate(line.hourly_cost)}</td><td className="px-3 py-2 text-right">{formatQuantity(line.hours_billable)}</td><td className="px-3 py-2 text-right">{formatAllocationPct(line.allocation_pct)}%</td><td className="px-3 py-2"><ProvenanceChip entry={{ value: line.role, provenance: line.provenance, source_id: line.source_id ?? undefined, warning: line.warning ?? undefined }} /></td></tr>)}</tbody>
        </table></div> : <p className="text-warning">No staffing lines yet.</p>}
        {payload.staffing.warnings.length ? <ul className="space-y-1 text-secondary text-text-secondary">{payload.staffing.warnings.map((warning, i) => <li key={i} data-testid="staffing-warning">{warning}</li>)}</ul> : null}
        {(!opportunityId || state?.cost_lines !== undefined) ? <DirectCostsEditor rows={costs} onChange={opportunityId && state ? changeCosts : undefined} disabled={busy} /> : null}
        {state?.requires_notice_on_change && dirty ? <div className="flex flex-wrap gap-3"><label>Effective from<Input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} /></label><label>Reason<Input value={reason} onChange={(e) => setReason(e.target.value)} /></label></div> : null}
        {opportunityId && state?.cost_lines !== undefined ? <Button disabled={!dirty || !state || !costsComplete(costs) || busy || (state.requires_notice_on_change && (!effectiveFrom || !reason.trim()))} onClick={() => void save()}><Save className="h-4 w-4" aria-hidden />{busy ? "Saving…" : "Save direct costs"}</Button> : null}
        {error ? <p role="alert" className="text-secondary text-danger">{error}</p> : null}
        {dirty && !preview && !error ? <p role="status" className="text-secondary text-text-secondary">{costsComplete(costs) ? "Updating GM…" : "Direct cost amount needed."}</p> : null}
      </div>
      <FinanceGmPanel result={result} locations={lines.map((line) => line.location)} />
    </div>
  </Section>;
}
