/**
 * S17 Agreements: a flat NDA/MSA document store.
 *
 * One Upload button (pick client, pick NDA or MSA, attach file). Table
 * columns: client, type, file name, uploaded by, uploaded date. Each row
 * has Download and Delete. No states, no owners, no dates to fill in, no
 * extraction — the file is the record.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FilePlus2, ShieldCheck, Trash2 } from "lucide-react";
import {
  type AgreementKind,
  type AgreementRow,
  type ClientListRow,
  type UUID,
  deleteAgreement,
  getAgreementDownloadUrl,
  listAgreements,
  listClients,
  uploadAgreement,
} from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { EmptyState } from "../../ui-v2/EmptyState";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../ui-v2/primitives/dialog";

function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="mt-4 flex justify-end gap-2">{children}</div>;
}

const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

interface UploadState {
  open: boolean;
  clientId: UUID | "";
  kind: AgreementKind | "";
  file: File | null;
  submitting: boolean;
  error: string | null;
}

const INITIAL_UPLOAD: UploadState = {
  open: false,
  clientId: "",
  kind: "",
  file: null,
  submitting: false,
  error: null,
};

export function AgreementsRegisterPage() {
  const [rows, setRows] = useState<AgreementRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [clients, setClients] = useState<ClientListRow[]>([]);
  const [search, setSearch] = useState("");
  const [upload, setUpload] = useState<UploadState>(INITIAL_UPLOAD);
  const [pendingDelete, setPendingDelete] = useState<AgreementRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ags, cs] = await Promise.all([
        listAgreements(),
        listClients({ size: 200 }),
      ]);
      setRows(ags.items);
      setClients(cs.items);
    } catch (e) {
      setError(e);
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.client_name.toLowerCase().includes(q) ||
        r.kind.toLowerCase().includes(q) ||
        r.filename.toLowerCase().includes(q) ||
        r.uploaded_by_name.toLowerCase().includes(q),
    );
  }, [rows, search]);

  const submitUpload = useCallback(async () => {
    if (!upload.clientId || !upload.kind || !upload.file) return;
    setUpload((s) => ({ ...s, submitting: true, error: null }));
    try {
      await uploadAgreement(upload.clientId, upload.kind, upload.file);
      setUpload(INITIAL_UPLOAD);
      await load();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Upload failed";
      setUpload((s) => ({ ...s, submitting: false, error: message }));
    }
  }, [upload, load]);

  const download = useCallback(async (row: AgreementRow) => {
    try {
      const { url } = await getAgreementDownloadUrl(row.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Download failed";
      alert(message);
    }
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    try {
      await deleteAgreement(pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Delete failed";
      alert(message);
    }
  }, [pendingDelete, load]);

  return (
    <div>
      <PageHeader
        title="NDA & MSA"
        subtitle="Signed documents by client. Upload, download, delete."
        actions={
          <div className="flex gap-2 items-center">
            <Input
              aria-label="Search agreements"
              placeholder="Search by client, type, filename, uploader"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button
              onClick={() =>
                setUpload({
                  open: true,
                  clientId: "",
                  kind: "",
                  file: null,
                  submitting: false,
                  error: null,
                })
              }
            >
              <FilePlus2 className="h-4 w-4 mr-2" />
              Upload
            </Button>
          </div>
        }
      />

      {error ? (
        <ErrorState
          title="We couldn't load agreements"
          description={error instanceof Error ? error.message : String(error)}
          onRetry={() => void load()}
        />
      ) : loading && !rows ? (
        <EmptyState title="Loading" description="Fetching agreements." />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No agreements yet"
          description="Click Upload to attach a signed NDA or MSA for a client."
        />
      ) : (
        <div className="overflow-x-auto border border-divider rounded-panel">
          <table className="w-full text-body" aria-label="Agreements">
            <thead className="bg-surface-muted text-left">
              <tr>
                <th className="p-3">Client</th>
                <th className="p-3">Type</th>
                <th className="p-3">File</th>
                <th className="p-3">Uploaded by</th>
                <th className="p-3">Uploaded</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id} className="border-t border-divider">
                  <td className="p-3">{row.client_name}</td>
                  <td className="p-3">
                    <span className="inline-flex items-center gap-1">
                      <ShieldCheck className="h-4 w-4" />
                      {row.kind}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="font-medium">{row.filename}</span>
                    <span className="ml-2 text-secondary text-text-secondary">
                      {formatBytes(row.file_size)}
                    </span>
                  </td>
                  <td className="p-3">{row.uploaded_by_name}</td>
                  <td className="p-3">{formatDate(row.uploaded_at)}</td>
                  <td className="p-3 text-right">
                    <div className="inline-flex gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => void download(row)}
                        aria-label={`Download ${row.filename}`}
                      >
                        <Download className="h-4 w-4 mr-1" />
                        Download
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => setPendingDelete(row)}
                        aria-label={`Delete ${row.filename}`}
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        open={upload.open}
        onOpenChange={(open) => setUpload((s) => (open ? s : INITIAL_UPLOAD))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload NDA or MSA</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <label className="block">
              <span className="text-secondary">Client</span>
              <select
                aria-label="Client"
                value={upload.clientId}
                onChange={(e) =>
                  setUpload((s) => ({ ...s, clientId: e.target.value as UUID }))
                }
                className="mt-1 block w-full border border-divider rounded-control p-2 text-body"
              >
                <option value="">Pick a client…</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-secondary">Type</span>
              <div className="mt-1 flex gap-4 text-body">
                {(["NDA", "MSA"] as AgreementKind[]).map((k) => (
                  <label key={k} className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      name="kind"
                      value={k}
                      checked={upload.kind === k}
                      onChange={() => setUpload((s) => ({ ...s, kind: k }))}
                    />
                    {k}
                  </label>
                ))}
              </div>
            </label>
            <label className="block">
              <span className="text-secondary">File (PDF or DOCX)</span>
              <input
                aria-label="Agreement file"
                type="file"
                accept={ACCEPT}
                className="mt-1 block w-full text-body"
                onChange={(e) =>
                  setUpload((s) => ({ ...s, file: e.target.files?.[0] ?? null }))
                }
              />
            </label>
            {upload.error ? (
              <p role="alert" className="text-danger">
                {upload.error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setUpload(INITIAL_UPLOAD)}
              disabled={upload.submitting}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void submitUpload()}
              disabled={
                !upload.clientId || !upload.kind || !upload.file || upload.submitting
              }
            >
              {upload.submitting ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => (open ? undefined : setPendingDelete(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this agreement?</DialogTitle>
          </DialogHeader>
          {pendingDelete ? (
            <div className="space-y-2 text-body">
              <p>
                {pendingDelete.kind} ·{" "}
                <span className="font-medium">{pendingDelete.filename}</span>
              </p>
              <p>Client: {pendingDelete.client_name}</p>
              <p className="text-secondary text-text-secondary">
                The row goes and the stored file is removed. This cannot be undone.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              Cancel
            </Button>
            <Button onClick={() => void confirmDelete()}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
