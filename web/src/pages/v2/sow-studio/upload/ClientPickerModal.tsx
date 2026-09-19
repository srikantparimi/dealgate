/**
 * S10-01 — client picker modal.
 *
 * Renders the top-3 candidates the resolver found plus a "Create new
 * client" option pre-filled from the SOW extract (docs/sow-first-
 * principles.md — pre-filled is the default state, and the reviewer
 * confirms rather than types). Submitting POSTs to
 * ``/sows/jobs/{id}/pick`` and the parent flow takes over from there.
 */
import { useMemo, useState, type FormEvent } from "react";
import {
  pickSowJobClient,
  type SowUploadCandidate,
  type SowUploadJobResponse,
  type SowUploadNeedsPickCreateNew,
  type SowUploadNeedsPickPayload,
} from "../../../../api/client";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../../ui-v2/primitives/dialog";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { Label } from "../../../../ui-v2/primitives/label";

export interface ClientPickerModalProps {
  open: boolean;
  jobId: string;
  needsPick: SowUploadNeedsPickPayload;
  onPicked: (job: SowUploadJobResponse) => void;
  onCancel: () => void;
}

type SelectedKey = string; // "candidate:<uuid>" | "new"

function keyFor(candidate: SowUploadCandidate): SelectedKey {
  return `candidate:${candidate.client_id}`;
}

const CREATE_NEW_KEY: SelectedKey = "new";

export function ClientPickerModal({
  open,
  jobId,
  needsPick,
  onPicked,
  onCancel,
}: ClientPickerModalProps) {
  const candidates = needsPick.candidates ?? [];
  const initialCreateNew: SowUploadNeedsPickCreateNew = useMemo(() => {
    const c = needsPick.create_new ?? {
      legal_name: null,
      domain: null,
      address_lines: [],
    };
    return {
      legal_name: c.legal_name ?? "",
      domain: c.domain ?? "",
      address_lines: c.address_lines ?? [],
    } as SowUploadNeedsPickCreateNew;
  }, [needsPick.create_new]);

  const [selected, setSelected] = useState<SelectedKey>(() => {
    if (candidates.length > 0) return keyFor(candidates[0]);
    return CREATE_NEW_KEY;
  });
  const [createNew, setCreateNew] = useState<SowUploadNeedsPickCreateNew>(
    initialCreateNew,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      let job: SowUploadJobResponse;
      if (selected === CREATE_NEW_KEY) {
        if (!createNew.legal_name || !createNew.legal_name.trim()) {
          setError("Legal name is required to create a new client.");
          setSubmitting(false);
          return;
        }
        job = await pickSowJobClient(jobId, {
          create_new: {
            legal_name: createNew.legal_name.trim(),
            domain: createNew.domain?.trim() || null,
            address_lines: createNew.address_lines ?? null,
          },
        });
      } else {
        const clientId = selected.slice("candidate:".length);
        job = await pickSowJobClient(jobId, { client_id: clientId });
      }
      onPicked(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pick failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent data-testid="client-picker-modal">
        <DialogHeader>
          <DialogTitle>Which client is this SOW for?</DialogTitle>
          <DialogDescription>
            The system could not lock a match. Pick one of the candidates
            below, or confirm the new-client details the extract read
            from the file.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <fieldset className="flex flex-col gap-2">
            <legend className="sr-only">Candidates</legend>
            {candidates.length === 0 ? (
              <p
                className="text-secondary text-text-secondary"
                data-testid="picker-no-candidates"
              >
                No existing client matched — confirm the new-client details
                below.
              </p>
            ) : (
              candidates.slice(0, 3).map((c) => (
                <label
                  key={c.client_id}
                  className="flex items-center gap-2 rounded-panel border border-divider p-3 hover:bg-primary-subtle"
                  data-testid={`picker-candidate-${c.client_id}`}
                >
                  <input
                    type="radio"
                    name="candidate"
                    value={keyFor(c)}
                    checked={selected === keyFor(c)}
                    onChange={() => setSelected(keyFor(c))}
                  />
                  <span className="flex-1 text-body text-text">{c.name}</span>
                  {typeof c.score === "number" ? (
                    <span className="text-secondary text-text-secondary">
                      score {c.score.toFixed(2)}
                    </span>
                  ) : c.confidence ? (
                    <span className="text-secondary text-text-secondary">
                      score {c.confidence}
                    </span>
                  ) : null}
                </label>
              ))
            )}
            <label
              className="flex items-center gap-2 rounded-panel border border-divider p-3 hover:bg-primary-subtle"
              data-testid="picker-create-new"
            >
              <input
                type="radio"
                name="candidate"
                value={CREATE_NEW_KEY}
                checked={selected === CREATE_NEW_KEY}
                onChange={() => setSelected(CREATE_NEW_KEY)}
              />
              <span className="flex-1 text-body text-text">
                Create a new client from the SOW
              </span>
            </label>
          </fieldset>
          {selected === CREATE_NEW_KEY ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="picker-new-legal-name">Legal name</Label>
                <Input
                  id="picker-new-legal-name"
                  value={createNew.legal_name ?? ""}
                  onChange={(e) =>
                    setCreateNew((prev) => ({
                      ...prev,
                      legal_name: e.target.value,
                    }))
                  }
                  data-testid="picker-new-legal-name"
                />
              </div>
              <div>
                <Label htmlFor="picker-new-domain">Domain</Label>
                <Input
                  id="picker-new-domain"
                  value={createNew.domain ?? ""}
                  onChange={(e) =>
                    setCreateNew((prev) => ({
                      ...prev,
                      domain: e.target.value,
                    }))
                  }
                  data-testid="picker-new-domain"
                />
              </div>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-danger" data-testid="picker-error">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              disabled={submitting}
              data-testid="picker-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={submitting}
              data-testid="picker-submit"
            >
              {submitting ? "Linking…" : "Use this client"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
