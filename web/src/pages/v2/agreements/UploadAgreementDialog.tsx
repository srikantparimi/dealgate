import { useState } from "react";
import { Upload } from "lucide-react";
import {
  extractAgreement,
  executeAgreement,
  type AgreementRow,
  type AgreementDocumentDraft,
} from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../../../ui-v2/primitives/dialog";

function field(draft: AgreementDocumentDraft, key: string) {
  const raw = draft.fields[key];
  return raw && typeof raw === "object" ? raw : { value: "", page_ref: null };
}

export function UploadAgreementDialog({
  agreement,
  onClose,
  onSaved,
}: {
  agreement: AgreementRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<AgreementDocumentDraft | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const corrected =
    draft &&
    (start !== field(draft, "effective_from").value ||
      end !== field(draft, "expiry").value);
  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setDraft(null);
    setConfirmed(false);
    try {
      const result = await extractAgreement(agreement.id, file);
      setDraft(result);
      setStart(field(result, "effective_from").value ?? "");
      setEnd(field(result, "expiry").value ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      await executeAgreement(agreement.id, {
        document_id: draft.id,
        effective_from: start,
        expiry: end,
        signed_confirmed: confirmed,
        correction_reason: reason || undefined,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>File signed {agreement.kind}</DialogTitle>
          <DialogDescription>
            {agreement.client_name} ·{" "}
            {agreement.legal_entity_name ?? "Legal entity"}
          </DialogDescription>
        </DialogHeader>
        <label className="grid gap-2 text-body">
          Signed PDF or DOCX
          <Input
            type="file"
            accept=".pdf,.docx"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f);
            }}
          />
        </label>
        {busy && <p role="status">Processing...</p>}
        {error && (
          <p role="alert" className="text-danger">
            {error}
          </p>
        )}
        {draft && (
          <div className="grid gap-4 text-body">
            <p>
              Extracted entity:{" "}
              {field(draft, "client_legal_name").value || "Not found"}
            </p>
            <label className="grid gap-1">
              Effective date
              <Input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
              <span className="text-secondary text-text-secondary">
                Source {String(draft.fields.ref_unit ?? "page")}{" "}
                {field(draft, "effective_from").page_ref ?? "unavailable"}
              </span>
            </label>
            <label className="grid gap-1">
              Expiry date
              <Input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
              <span className="text-secondary text-text-secondary">
                Source {String(draft.fields.ref_unit ?? "page")}{" "}
                {field(draft, "expiry").page_ref ?? "unavailable"}
              </span>
            </label>
            {corrected && (
              <label className="grid gap-1">
                Reason for date correction
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
            )}
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              I confirm this document is signed, belongs to this legal entity,
              and these dates match the document.
            </label>
            <Button
              onClick={() => void save()}
              disabled={
                busy ||
                !confirmed ||
                !start ||
                !end ||
                end < start ||
                Boolean(corrected && !reason.trim())
              }
            >
              <Upload className="mr-2 h-4 w-4" />
              File as executed
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
