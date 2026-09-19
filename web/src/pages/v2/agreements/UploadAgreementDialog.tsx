/**
 * UploadAgreementDialog — the six-step upload flow from spec §12:
 *   Select file + type → Associate entity/opportunity → Extract →
 *   Review + uncertainty → Save draft → Submit for review.
 *
 * The evidence PUT is deferred until the agreement row exists, so the
 * dialog collects metadata and hands the file to the parent's
 * `onSubmit`. Real S3 uploads reuse `getUploadUrl` from `AgreementsPanel`
 * once the row is created — this dialog keeps the intake honest without
 * duplicating that logic.
 */

import { useState, type FormEvent } from "react";
import { Button } from "../../../ui-v2/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../ui-v2/primitives/dialog";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";
import type { AgreementKind } from "../../../api/client";

export interface UploadDraft {
  file: File | null;
  kind: AgreementKind;
  entity: string;
  linkedOpportunity: string;
  ownerEmail: string;
  reviewNote: string;
}

export interface UploadAgreementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (draft: UploadDraft) => void;
}

const EMPTY: UploadDraft = {
  file: null,
  kind: "NDA",
  entity: "",
  linkedOpportunity: "",
  ownerEmail: "",
  reviewNote: "",
};

export function UploadAgreementDialog({
  open,
  onOpenChange,
  onSubmit,
}: UploadAgreementDialogProps) {
  const [draft, setDraft] = useState<UploadDraft>(EMPTY);
  const [step, setStep] = useState(0);

  function update<K extends keyof UploadDraft>(key: K, value: UploadDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function reset() {
    setDraft(EMPTY);
    setStep(0);
  }

  function handleClose(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit(draft);
    reset();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent aria-label="Upload agreement">
        <DialogHeader>
          <DialogTitle>Upload agreement</DialogTitle>
          <DialogDescription>
            Select the file and type, associate an entity, and submit for
            Legal review. Extraction confidence is never legal
            verification (spec §12).
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          {step === 0 ? (
            <fieldset className="flex flex-col gap-3">
              <legend className="text-secondary text-text-secondary">
                Step 1 · Select file &amp; type
              </legend>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-file">Document</Label>
                <input
                  id="agr-file"
                  type="file"
                  accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(e) =>
                    update("file", e.target.files?.[0] ?? null)
                  }
                  className="text-body text-text"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-kind">Type</Label>
                <select
                  id="agr-kind"
                  value={draft.kind}
                  onChange={(e) => update("kind", e.target.value as AgreementKind)}
                  className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
                >
                  <option value="NDA">NDA</option>
                  <option value="MSA">MSA</option>
                </select>
              </div>
            </fieldset>
          ) : null}

          {step === 1 ? (
            <fieldset className="flex flex-col gap-3">
              <legend className="text-secondary text-text-secondary">
                Step 2 · Associate entity &amp; opportunity
              </legend>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-entity">Legal entity</Label>
                <Input
                  id="agr-entity"
                  value={draft.entity}
                  onChange={(e) => update("entity", e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-opp">Linked opportunity (optional)</Label>
                <Input
                  id="agr-opp"
                  value={draft.linkedOpportunity}
                  onChange={(e) =>
                    update("linkedOpportunity", e.target.value)
                  }
                  placeholder="HubSpot deal id or SOW ref"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-owner">Legal owner</Label>
                <Input
                  id="agr-owner"
                  type="email"
                  value={draft.ownerEmail}
                  onChange={(e) => update("ownerEmail", e.target.value)}
                  placeholder="legal@smartek21.com"
                />
              </div>
            </fieldset>
          ) : null}

          {step === 2 ? (
            <fieldset className="flex flex-col gap-3">
              <legend className="text-secondary text-text-secondary">
                Step 3 · Review &amp; submit
              </legend>
              <p className="text-body text-text-secondary">
                Extraction runs after Legal accepts the draft. The row is
                created in <em>Drafting</em> state so the register shows a
                real audit trail before signature.
              </p>
              <div className="flex flex-col gap-1">
                <Label htmlFor="agr-note">Reviewer note (optional)</Label>
                <Input
                  id="agr-note"
                  value={draft.reviewNote}
                  onChange={(e) => update("reviewNote", e.target.value)}
                  placeholder="Anything the Legal reviewer should see first"
                />
              </div>
            </fieldset>
          ) : null}

          <div className="flex items-center justify-between pt-2">
            <div className="text-secondary text-text-secondary">
              Step {step + 1} of 3
            </div>
            <div className="flex gap-2">
              {step > 0 ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setStep((s) => s - 1)}
                >
                  Back
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => handleClose(false)}
                >
                  Cancel
                </Button>
              )}
              {step < 2 ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => setStep((s) => s + 1)}
                  disabled={step === 0 && !draft.file}
                >
                  Next
                </Button>
              ) : (
                <Button type="submit" variant="primary">
                  Submit for review
                </Button>
              )}
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
