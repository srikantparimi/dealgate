import { useEffect, useRef, useState } from "react";
import { FileCheck, Upload } from "lucide-react";
import { uploadSignedSowFile, verifySignedSow, type MeResponse } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import type { WorkspaceSnapshot } from "./readiness";

export interface ExecutionProps {
  snap: WorkspaceSnapshot;
  viewer?: MeResponse | null;
  refresh?: () => void | Promise<void>;
}

export function SignedSowActions(props: ExecutionProps) {
  return <Actions key={`${props.snap.approvalPackage?.id}:${props.snap.sow?.id}:${props.snap.approvalPackage?.status}:${props.snap.approvalPackage?.superseded_by}`} {...props} />;
}

function Actions({ snap, viewer, refresh }: ExecutionProps) {
  const pkg = snap.approvalPackage;
  const [file, setFile] = useState<File | null>(null);
  const [attested, setAttested] = useState(false);
  const [upload, setUpload] = useState(snap.signedSow);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { setUpload(snap.signedSow); }, [snap.signedSow]);
  const owner = !!viewer && (viewer.groups.includes("SystemAdmin") || viewer.id === snap.deal?.owner_id);
  const stale = !!pkg && (!!pkg.superseded_by || pkg.sow_version_id !== snap.sow?.id);
  const eligible = !!pkg && pkg.status === "ready_to_sign" && !stale && !upload?.released_at;
  async function act(verify: boolean) {
    if (!pkg || !owner || !eligible || busy || (!verify && (!file || !attested))) return;
    setBusy(true); setError(null);
    try {
      const result = verify ? await verifySignedSow(pkg.id) : await uploadSignedSowFile(pkg.id, file!, attested);
      if (!alive.current) return;
      setUpload(result);
      await refresh?.();
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : "Document operation failed");
    } finally { if (alive.current) setBusy(false); }
  }
  return <section aria-label="Execution upload" className="space-y-3 border-t border-divider pt-4">
    <h2 className="text-section text-text">Executed document</h2>
    {pkg && <p className="text-secondary text-text-secondary break-all">Approved package {pkg.id} · SOW version {pkg.sow_version_id}</p>}
    {stale ? <p role="alert">This package is superseded or belongs to a different SOW version.</p>
      : !pkg ? <p>No approved package.</p>
      : !eligible && !upload?.released_at ? <p>Current package approval is required before signature upload.</p> : null}
    {upload && <div role="status"><p>Verification: {upload.verify_status}</p>
      {upload.signer_state && <p>Signer state: {upload.signer_state}</p>}
      {upload.verify_reason && <p>{upload.verify_reason}</p>}</div>}
    {error && <p role="alert" className="text-danger">{error}</p>}
    {owner && eligible && <>
      <label className="block text-body">Executed document
        <input className="block max-w-full mt-1" type="file" accept=".pdf,.docx" disabled={busy}
          onChange={event => { setFile(event.target.files?.[0] ?? null); setAttested(false); }} />
      </label>
      <label className="flex items-center gap-2 text-body"><input type="checkbox" checked={attested} disabled={busy}
        onChange={event => setAttested(event.target.checked)} />This document contains signature evidence</label>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || !file || !attested} onClick={() => void act(false)}><Upload size={16} />Upload executed document</Button>
        <Button disabled={busy || !upload || upload.verify_status === "verified"} onClick={() => void act(true)}><FileCheck size={16} />Verify executed document</Button>
      </div>
    </>}
  </section>;
}
