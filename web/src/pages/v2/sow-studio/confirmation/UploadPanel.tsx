/**
 * Compact upload panel — the only thing the screen shows before an
 * opportunity id is resolved.
 *
 * The moment the file is uploaded and the extract completes, the
 * caller flips the URL to `/sows/new?opportunityId=<id>` and the
 * confirmation payload takes over.
 */
import { useEffect, useState } from "react";
import { Upload } from "lucide-react";
import {
  listClients,
  type ClientListRow,
} from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { Label } from "../../../../ui-v2/primitives/label";
import { Section } from "./Section";

export interface UploadPanelProps {
  /**
   * Called when the reviewer submits the pair (client + file). The
   * SowStudio page owns the actual upload → extract wiring; this panel
   * just collects the two inputs.
   */
  onSubmit: (input: { client: ClientListRow; file: File }) => Promise<void>;
  submitting: boolean;
  error: string | null;
}

export function UploadPanel({ onSubmit, submitting, error }: UploadPanelProps) {
  const [query, setQuery] = useState("");
  const [clients, setClients] = useState<ClientListRow[]>([]);
  const [selected, setSelected] = useState<ClientListRow | null>(null);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    let cancelled = false;
    listClients({ search: query, size: 10 })
      .then((r) => {
        if (!cancelled) setClients(r.items);
      })
      .catch(() => {
        if (!cancelled) setClients([]);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const ready = Boolean(selected && file);

  return (
    <Section
      id="section-upload"
      title="Upload a SOW to start"
      description="Pick the client and the SOW file. The system extracts every commercial field, classifies the engagement, builds the staffing plan and computes the GM. You confirm on the next screen."
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready) return;
          void onSubmit({ client: selected!, file: file! });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="upload-client">Client</Label>
            <Input
              id="upload-client"
              placeholder="Start typing…"
              value={selected ? selected.name : query}
              onChange={(e) => {
                setSelected(null);
                setQuery(e.target.value);
              }}
              data-testid="upload-client-input"
            />
            {clients.length && !selected ? (
              <ul className="mt-2 max-h-40 overflow-y-auto rounded-panel border border-divider bg-surface">
                {clients.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(c)}
                      className="block w-full px-3 py-2 text-left text-body text-text hover:bg-primary-subtle focus-visible:outline-focus"
                      data-testid={`upload-client-option-${c.id}`}
                    >
                      {c.name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div>
            <Label htmlFor="upload-file">SOW file</Label>
            <input
              id="upload-file"
              type="file"
              accept="application/pdf,.pdf,.docx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-secondary text-text-secondary"
              data-testid="upload-file-input"
            />
            {file ? (
              <p className="mt-1 text-secondary text-text-secondary">
                Staged: {file.name} ·{" "}
                {Math.max(1, Math.round(file.size / 1024))} kB
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-secondary text-text-secondary">
            No fields to fill here — that is the point. Everything else is
            derived.
          </p>
          <Button
            type="submit"
            variant="primary"
            disabled={!ready || submitting}
            data-testid="upload-submit"
          >
            <Upload className="h-4 w-4" aria-hidden />
            {submitting ? "Extracting…" : "Upload & extract"}
          </Button>
        </div>
        {error ? (
          <p role="alert" className="text-danger">
            {error}
          </p>
        ) : null}
      </form>
    </Section>
  );
}
