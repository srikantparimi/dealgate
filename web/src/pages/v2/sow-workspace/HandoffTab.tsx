import { useEffect, useId, useRef, useState } from "react";
import { Check, RefreshCw, Send } from "lucide-react";
import { getHandoffGate, getDeliveryAcceptance, recordDeliveryAcceptance, releaseSignedSow,
  type DeliveryAcceptance, type HandoffGate } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import type { ExecutionProps } from "./SignedSowActions";

export function HandoffTab(props: ExecutionProps) {
  return <Handoff key={`${props.snap.approvalPackage?.id}:${props.snap.sow?.id}:${props.snap.approvalPackage?.status}:${props.snap.approvalPackage?.superseded_by}`} {...props} />;
}

function Handoff({ snap, viewer, refresh }: ExecutionProps) {
  const pkg = snap.approvalPackage;
  const [gate, setGate] = useState<HandoffGate | null>(null);
  const [acceptance, setAcceptance] = useState<DeliveryAcceptance | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [staffing, setStaffing] = useState(false);
  const [billing, setBilling] = useState(false);
  const [po, setPo] = useState(false);
  const [notes, setNotes] = useState("");
  const [released, setReleased] = useState(!!snap.signedSow?.released_at);
  const notesId = useId();
  const alive = useRef(true);
  const generation = useRef(0);
  const stale = !!pkg && (!!pkg.superseded_by || pkg.sow_version_id !== snap.sow?.id);
  const canAccept = !!viewer && viewer.groups.some(role => role === "Delivery" || role === "SystemAdmin");
  const canRelease = !!viewer && (viewer.groups.includes("SystemAdmin") || viewer.id === snap.deal?.owner_id);
  async function load() {
    if (!pkg) { setLoading(false); return; }
    const current = ++generation.current;
    setLoading(true); setError(null);
    try {
      const [nextGate, nextAcceptance] = await Promise.all([getHandoffGate(pkg.id), getDeliveryAcceptance(pkg.id)]);
      if (!alive.current || current !== generation.current) return;
      setGate(nextGate); setAcceptance(nextAcceptance);
    } catch (cause) {
      if (alive.current && current === generation.current) {
        setGate(null); setError(cause instanceof Error ? cause.message : "Handoff unavailable");
      }
    } finally { if (alive.current && current === generation.current) setLoading(false); }
  }
  useEffect(() => {
    alive.current = true; void load();
    return () => { alive.current = false; ++generation.current; };
  }, [pkg?.id]);
  useEffect(() => { setReleased(!!snap.signedSow?.released_at); }, [snap.signedSow?.released_at]);
  async function mutate(release: boolean) {
    if (!pkg || stale || busy || released) return;
    if (release ? !canRelease || !gate?.ok : !canAccept || !staffing || !billing || !po) return;
    setBusy(true); setError(null);
    try {
      if (release) {
        const result = await releaseSignedSow(pkg.id);
        if (!alive.current) return;
        setReleased(!!result.released_at);
      } else {
        const result = await recordDeliveryAcceptance(pkg.id, {
          staffing_confirmed: staffing, billing_setup_confirmed: billing, po_confirmed: po, notes,
        });
        if (!alive.current) return;
        setAcceptance(result);
      }
      await load();
      if (alive.current) await refresh?.();
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : "Handoff operation failed");
    } finally { if (alive.current) setBusy(false); }
  }
  if (!pkg) return <p>No approval package.</p>;
  return <div className="space-y-4 max-w-3xl">
    <section aria-label="Handoff status" className="space-y-2">
      <h2 className="text-section text-text">Handoff status</h2>
      <p>Execution verification: {snap.signedSow?.verify_status ?? "Not uploaded"}</p>
      <p>Handoff release: {released ? "Released" : "Not released"}</p>
      <p>Delivery acceptance: <span>{loading ? "Loading" : error ? "Unavailable" : acceptance ? "Recorded" : "Not recorded"}</span></p>
      {acceptance && <dl className="text-body">
        <dt>Staffing confirmation</dt><dd>{acceptance.staffing_confirmed ? "Confirmed" : "Not confirmed"}</dd>
        <dt>Billing setup confirmation</dt><dd>{acceptance.billing_setup_confirmed ? "Confirmed" : "Not confirmed"}</dd>
        <dt>PO confirmation</dt><dd>{acceptance.po_confirmed ? "Confirmed" : "Not confirmed"}</dd>
      </dl>}
      <a className="text-link underline" href={`/handoffs/${pkg.id}`}>Distribution receipts</a>
    </section>
    {stale && <p role="alert">This package is superseded or belongs to a different SOW version.</p>}
    {error && <p role="alert" className="text-danger">{error}</p>}
    {gate?.reasons.length ? <ul>{gate.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : null}
    <Button variant="secondary" disabled={loading || busy} onClick={() => void load()}><RefreshCw size={16} />Refresh handoff</Button>
    {canAccept && !stale && !released && <section aria-label="Delivery acceptance" className="border-t border-divider pt-4 space-y-3">
      <h2 className="text-section text-text">Delivery acceptance</h2>
      <label className="flex gap-2"><input type="checkbox" checked={staffing} disabled={busy} onChange={e => setStaffing(e.target.checked)} />Staffing confirmed</label>
      <label className="flex gap-2"><input type="checkbox" checked={billing} disabled={busy} onChange={e => setBilling(e.target.checked)} />Billing setup confirmed</label>
      <label className="flex gap-2"><input type="checkbox" checked={po} disabled={busy} onChange={e => setPo(e.target.checked)} />PO confirmed</label>
      <label className="block" htmlFor={notesId}>Acceptance notes</label>
      <textarea id={notesId} className="block border border-divider p-2 w-full" value={notes} maxLength={2048} disabled={busy} onChange={e => setNotes(e.target.value)} />
      <Button disabled={busy || loading || !staffing || !billing || !po} onClick={() => void mutate(false)}><Check size={16} />Record delivery acceptance</Button>
    </section>}
    {canRelease && !stale && !released && <Button disabled={busy || loading || !gate?.ok} onClick={() => void mutate(true)}><Send size={16} />Release handoff</Button>}
  </div>;
}
