import { useEffect, useRef, useState } from "react";
import { Calculator, Save, X } from "lucide-react";
import { previewCommercial, type CommercialComponent, type CommercialSchedule } from "../../../api/commercial";
import { reviseForecastCommercial } from "../../../api/forecast";
import { Button } from "../../../ui-v2/primitives/button";
import { Field, Rows } from "../sow-workspace/commercial-editor/Fields";
import { PricingFields } from "../sow-workspace/commercial-editor/PricingFields";
import { CalendarFields } from "../sow-workspace/commercial-editor/CalendarFields";
import { HybridFields } from "../sow-workspace/commercial-editor/HybridFields";

export function PlanCommercialEditor({ planId, versionId, initial, onSaved, onCancel }: {
  planId: string; versionId: string; initial: CommercialComponent;
  onSaved: () => void; onCancel: () => void;
}) {
  const [inputs, setInputs] = useState(() => structuredClone(initial));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<CommercialSchedule | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  function change(next: CommercialComponent) { setInputs(next); setPreview(null); }
  function patch(key: keyof CommercialComponent, value: unknown) { change({ ...inputs, [key]: value }); }
  async function submit(save: boolean) {
    setBusy(true); setError("");
    try {
      if (save) {
        await reviseForecastCommercial(planId, { expected_version_id: versionId, inputs, change_reason: reason });
        if (mounted.current) onSaved();
      } else {
        const result = await previewCommercial(inputs);
        if (mounted.current) setPreview(result.commercial_snapshot?.schedule ?? null);
      }
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : "Commercial revision failed"); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Edit planning commercial terms" className="min-w-0 space-y-3 border-l-2 border-primary pl-4">
    {error && <p role="alert" className="text-danger">{error}</p>}
    <fieldset disabled={busy} className="min-w-0 space-y-4">
      <p>{inputs.profile.replaceAll("_", " ")} / {inputs.currency ?? "Unconfirmed currency"}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Service start" type="date" value={inputs.service_start} onChange={value => patch("service_start", value || null)} />
        <Field label="Service end" type="date" value={inputs.service_end} onChange={value => patch("service_end", value || null)} />
      </div>
      {inputs.profile === "hybrid" ? <HybridFields component={inputs} onChange={change} /> : <>
        <PricingFields component={inputs} onChange={value => patch("pricing", value)} />
        <CalendarFields component={inputs} onChange={change} />
      </>}
      <Rows title="Period costs" rows={inputs.costs} columns={[
        { key: "month", label: "Cost month", type: "date" },
        { key: "location", label: "Cost location", options: ["US", "India"] },
        { key: "amount", label: "Cost amount", type: "decimal" },
      ]} onChange={value => patch("costs", value)} create={() => ({ source_id: crypto.randomUUID(), month: "", location: "", amount: null })} addLabel="Add period cost" />
      <Field label="Commercial change reason" value={reason} onChange={setReason} />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => void submit(false)}><Calculator className="h-4 w-4" />Calculate plan</Button>
        <Button disabled={!reason.trim()} onClick={() => void submit(true)}><Save className="h-4 w-4" />Save commercial revision</Button>
        <Button variant="secondary" onClick={onCancel}><X className="h-4 w-4" />Cancel commercial edit</Button>
      </div>
    </fieldset>
    {preview && <section aria-label="Plan calculation" className="overflow-auto">
      <p role="status">Calculation: {preview.status}</p>
      {preview.missing.map((item, i) => <p key={i}>{item.field ?? item.key}: {item.reason}</p>)}
      <table className="w-full text-left"><thead><tr><th>Month</th><th>Location</th><th>Revenue</th><th>Cost</th></tr></thead>
        <tbody>{preview.rows.map((row, i) => <tr key={i}><td>{row.month}</td><td>{row.location}</td><td>{row.revenue}</td><td>{row.cost ?? "Unconfirmed"}</td></tr>)}</tbody>
      </table>
    </section>}
  </section>;
}
