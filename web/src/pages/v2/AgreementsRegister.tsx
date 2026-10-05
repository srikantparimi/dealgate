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
import { Link, useSearchParams } from "react-router-dom";
import {
  Download,
  FilePlus2,
  FileText,
  History,
  Replace,
  Trash2,
  RefreshCw,
} from "lucide-react";
import {
  type AgreementKind,
  type AgreementRow,
  type ClientListRow,
  type UUID,
  deleteAgreement,
  getAgreementDownloadUrl,
  listAgreements,
  listClients,
  getClient,
  uploadAgreement,
  getMe,
  listAgreementVersions,
  replaceAgreement,
  getAgreementVersionDownloadUrl,
  type AgreementFileVersion,
  type DeletionJobResponse,
  getDeletionJob,
  retryDeletionJob,
} from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { EmptyState } from "../../ui-v2/EmptyState";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { ClientAgreementPresence } from "../../ui-v2/ClientAgreementPresence";
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
  const [params] = useSearchParams();
  return (
    <AgreementsRegister
      key={params.toString()}
      clientId={params.get("client_id") || undefined}
      kind={params.get("kind")}
      openUpload={params.get("upload") === "1"}
    />
  );
}

function RevisionDialog({
  row,
  canWrite,
  onClose,
  onSaved,
}: {
  row: AgreementRow;
  canWrite: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [versions, setVersions] = useState<AgreementFileVersion[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [expected, setExpected] = useState(row.version_no ?? 1);
  useEffect(() => {
    let live = true;
    setVersions(null);
    listAgreementVersions(row.id).then(
      (result) => {
        if (!live) return;
        setVersions(result.items);
        if (result.items.length) setExpected(result.items[0].version_no);
        setError(null);
      },
      (e) => {
        if (live)
          setError(e instanceof Error ? e.message : "History unavailable");
      },
    );
    return () => {
      live = false;
    };
  }, [row.id, reload]);
  const save = async () => {
    if (!file || !canWrite || !versions) return;
    setBusy(true);
    setError(null);
    try {
      await replaceAgreement(row.id, expected, file);
      await onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replacement failed");
    } finally {
      setBusy(false);
    }
  };
  const downloadVersion = async (version: number) => {
    try {
      const result = await getAgreementVersionDownloadUrl(row.id, version);
      window.open(result.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  };
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row.kind} document history</DialogTitle>
        </DialogHeader>
        <p>{row.client_name}</p>
        {error && (
          <p role="alert" className="text-danger">
            {error}
          </p>
        )}
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => setReload((n) => n + 1)}
        >
          Reload latest version
        </Button>
        {versions === null ? (
          <p role="status">Loading history...</p>
        ) : (
          <ul className="max-h-64 overflow-y-auto space-y-3">
            {versions.map((version) => (
              <li
                key={version.version_no}
                className="border-b border-divider py-2"
              >
                <p className="break-words">
                  v{version.version_no}: {version.filename}
                </p>
                <p>
                  {version.uploaded_by_name} · {formatDate(version.uploaded_at)}
                </p>
                <Button
                  variant="secondary"
                  aria-label={`Download version ${version.version_no}`}
                  onClick={() => void downloadVersion(version.version_no)}
                >
                  <Download size={16} />
                  Download
                </Button>
              </li>
            ))}
          </ul>
        )}
        {canWrite && (
          <>
            <label htmlFor="agreement-replacement">Replacement file</label>
            <input
              id="agreement-replacement"
              type="file"
              accept={ACCEPT}
              disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </>
        )}
        <DialogFooter>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Close
          </Button>
          {canWrite && (
            <Button
              disabled={busy || !file || !versions?.length}
              onClick={() => void save()}
            >
              {busy ? "Saving..." : "Save replacement"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AgreementsRegister({
  clientId,
  kind,
  openUpload,
}: {
  clientId?: string;
  kind: string | null;
  openUpload: boolean;
}) {
  const [canWrite, setCanWrite] = useState(false);
  const [revision, setRevision] = useState<AgreementRow | null>(null);
  const [cleanup, setCleanup] = useState<DeletionJobResponse | null>(null);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [rows, setRows] = useState<AgreementRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [clients, setClients] = useState<ClientListRow[]>([]);
  const [search, setSearch] = useState("");
  const [upload, setUpload] = useState<UploadState>({
    ...INITIAL_UPLOAD,
    open: openUpload,
    clientId: clientId || "",
    kind: kind === "NDA" || kind === "MSA" ? kind : "",
  });
  const [pendingDelete, setPendingDelete] = useState<AgreementRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const actor = await getMe();
      const writable = actor.groups.some((group) =>
        ["Legal", "SystemAdmin"].includes(group),
      );
      setCanWrite(writable);
      const [ags, cs] = await Promise.all([
        listAgreements({ client_id: clientId }),
        writable
          ? listClients({ size: 200 })
          : Promise.resolve({ items: [] as ClientListRow[] }),
      ]);
      setRows(ags.items);
      if (
        writable &&
        clientId &&
        !cs.items.some((client) => client.id === clientId)
      ) {
        const selected = await getClient(clientId);
        cs.items.push({
          id: selected.id,
          name: selected.name,
          hubspot_company_id: selected.hubspot_company_id,
          opportunity_count: selected.opportunities.length,
          owner_ids: [],
          owners: [],
          sources: [],
        });
      }
      setClients(cs.items);
    } catch (e) {
      setError(e);
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = search.trim().toLowerCase();
    const scoped =
      kind === "NDA" || kind === "MSA"
        ? rows.filter((r) => r.kind === kind)
        : rows;
    if (!q) return scoped;
    return scoped.filter(
      (r) =>
        r.client_name.toLowerCase().includes(q) ||
        r.kind.toLowerCase().includes(q) ||
        r.filename.toLowerCase().includes(q) ||
        r.uploaded_by_name.toLowerCase().includes(q),
    );
  }, [rows, search, kind]);

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
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const receipt = await deleteAgreement(pendingDelete.id);
      setCleanup(receipt);
      setCleanupError(null);
      setPendingDelete(null);
      await load();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Delete failed";
      setDeleteError(message);
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, load, deleting]);

  const refreshCleanup = async (retry = false) => {
    if (!cleanup || cleanupBusy) return;
    setCleanupBusy(true);
    setCleanupError(null);
    try {
      setCleanup(
        await (retry
          ? retryDeletionJob(cleanup.job_id)
          : getDeletionJob(cleanup.job_id)),
      );
    } catch (e) {
      setCleanupError(
        e instanceof Error ? e.message : "Cleanup status unavailable",
      );
    } finally {
      setCleanupBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="NDA & MSA"
        actions={
          <div className="flex gap-2 items-center">
            <Input
              aria-label="Search agreements"
              placeholder="Search by client, type, filename, uploader"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {canWrite && (
              <Button
                onClick={() =>
                  setUpload({
                    open: true,
                    clientId: clientId || "",
                    kind: kind === "NDA" || kind === "MSA" ? kind : "",
                    file: null,
                    submitting: false,
                    error: null,
                  })
                }
              >
                <FilePlus2 className="h-4 w-4 mr-2" />
                Upload
              </Button>
            )}
          </div>
        }
      />
      {cleanup && (
        <section
          aria-label="Agreement deletion receipt"
          className="my-4 border-y border-divider py-3 space-y-2"
        >
          <p>
            {cleanup.source_deleted
              ? "Agreement removed from active records"
              : "Agreement removal pending"}
          </p>
          <p role="status">
            {cleanup.status === "done"
              ? "File cleanup complete"
              : cleanup.status === "failed"
                ? "File cleanup failed"
                : "File cleanup pending"}
          </p>
          {cleanup.last_error && <p role="alert">{cleanup.last_error}</p>}
          {cleanupError && <p role="alert">{cleanupError}</p>}
          <Link to={`/deletions/${cleanup.job_id}`} className="underline">
            Cleanup receipt {cleanup.job_id}
          </Link>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={cleanupBusy}
              onClick={() => void refreshCleanup()}
            >
              <RefreshCw size={16} />
              Refresh cleanup
            </Button>
            {canWrite && cleanup.status === "failed" && (
              <Button
                disabled={cleanupBusy}
                onClick={() => void refreshCleanup(true)}
              >
                <RefreshCw size={16} />
                Retry cleanup
              </Button>
            )}
          </div>
        </section>
      )}
      {clientId && (
        <ClientAgreementPresence
          key={rows?.map((row) => `${row.id}:${row.version_no ?? 1}`).join(",")}
          clientId={clientId}
        />
      )}

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
          description="No documents on file."
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
                      <FileText className="h-4 w-4" />
                      {row.kind}
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="font-medium">{row.filename}</span>
                    <span className="ml-2">v{row.version_no ?? 1}</span>
                    <span className="ml-2 text-secondary text-text-secondary">
                      {formatBytes(row.file_size)}
                    </span>
                  </td>
                  <td className="p-3">{row.uploaded_by_name}</td>
                  <td className="p-3">{formatDate(row.uploaded_at)}</td>
                  <td className="p-3 text-right">
                    <div className="inline-flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        aria-label={`History ${row.filename}`}
                        onClick={() => setRevision(row)}
                      >
                        <History size={16} />
                        History
                      </Button>
                      {canWrite && (
                        <Button
                          variant="secondary"
                          aria-label={`Replace ${row.filename}`}
                          onClick={() => setRevision(row)}
                        >
                          <Replace size={16} />
                          Replace
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        onClick={() => void download(row)}
                        aria-label={`Download ${row.filename}`}
                      >
                        <Download className="h-4 w-4 mr-1" />
                        Download
                      </Button>
                      {canWrite && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setDeleteError(null);
                            setPendingDelete(row);
                          }}
                          aria-label={`Delete ${row.filename}`}
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        open={upload.open && canWrite}
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
            <fieldset className="block">
              <legend className="text-secondary">Type</legend>
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
            </fieldset>
            <label className="block">
              <span className="text-secondary">File (PDF or DOCX)</span>
              <input
                aria-label="Agreement file"
                type="file"
                accept={ACCEPT}
                className="mt-1 block w-full text-body"
                onChange={(e) =>
                  setUpload((s) => ({
                    ...s,
                    file: e.target.files?.[0] ?? null,
                  }))
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
                !upload.clientId ||
                !upload.kind ||
                !upload.file ||
                upload.submitting
              }
            >
              {upload.submitting ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {revision && (
        <RevisionDialog
          key={revision.id}
          row={revision}
          canWrite={canWrite}
          onClose={() => setRevision(null)}
          onSaved={async () => {
            setRevision(null);
            await load();
          }}
        />
      )}

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) =>
          !open && !deleting ? setPendingDelete(null) : undefined
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this agreement?</DialogTitle>
          </DialogHeader>
          {deleteError && <p role="alert">{deleteError}</p>}
          {pendingDelete ? (
            <div className="space-y-2 text-body">
              <p>
                {pendingDelete.kind} ·{" "}
                <span className="font-medium">{pendingDelete.filename}</span>
              </p>
              <p>Client: {pendingDelete.client_name}</p>
              <p className="text-secondary text-text-secondary">
                This removes the document and all its versions. Stored files are
                queued for cleanup. This cannot be undone.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              variant="secondary"
              disabled={deleting}
              onClick={() => setPendingDelete(null)}
            >
              Cancel
            </Button>
            <Button disabled={deleting} onClick={() => void confirmDelete()}>
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
