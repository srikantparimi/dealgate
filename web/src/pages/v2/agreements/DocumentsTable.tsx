// S24-AG1 F8 · the Documents tab: the old register, kept and extended. One row
// per client and kind that holds a file: Client (opens the panel), Type, File,
// Source ("Standard v1" with its batch label, or "Client copy"), Uploaded by,
// Uploaded (Pacific date) and the actions: Download (audited route), History
// (every version, each downloadable) and Replace (the upload dialog for that
// client and kind: over a standard copy it replaces it for that client only).
// A batch shows only as its label (AG-0001), never as an id.
import { useEffect, useState } from "react";

import type { DocumentRow } from "../../../api/agreements";
import {
  getAgreementVersionDownloadUrl,
  listAgreementVersions,
  type AgreementFileVersion,
} from "../../../api/client";
import { cn } from "../../../lib/cn";
import { AgreementTag } from "../../../ui-v2/AgreementStateTag";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import { InlineLabel, cellClass } from "../pipeline/DealsTable";
import { AgreementsDrawer } from "./UploadDialog";
import { errorText, isBatchLabel, pacificDate } from "./agreementsFormat";
import type { AgreementRoles } from "./useAgreementsWorkspace";

const HEADERS = ["Client", "Type", "File", "Source", "Uploaded by", "Uploaded", "Action"];
const WIDTHS = ["sm:w-[190px]", "sm:w-[70px]", "", "sm:w-[130px]", "sm:w-[140px]", "sm:w-[120px]", "sm:w-[290px]"];

export function documentRowKey(row: Pick<DocumentRow, "client_id" | "kind">): string {
  return `${row.client_id}:${row.kind}`;
}

export interface DocumentsTableProps {
  rows: DocumentRow[];
  roles: AgreementRoles | null;
  onOpenClient: (clientId: string) => void;
  onDownload: (row: DocumentRow) => void;
  onHistory: (row: DocumentRow) => void;
  onReplace: (row: DocumentRow) => void;
}

export function DocumentsTable({ rows, roles, onOpenClient, onDownload, onHistory, onReplace }: DocumentsTableProps) {
  const lock = roles && !roles.canWrite ? "writer" : null;
  return (
    <div className="sm:overflow-x-auto">
      <table aria-label="Documents" className="block w-full text-table sm:table sm:min-w-[860px] sm:border-collapse">
        <thead className="hidden bg-surface-sunken sm:table-header-group">
          <tr>
            {HEADERS.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={cn(
                  i === 0 ? "pl-4 pr-2" : i === HEADERS.length - 1 ? "pl-2 pr-4" : "px-2",
                  "py-2 text-left text-secondary font-medium text-text-secondary",
                  WIDTHS[i],
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="block sm:table-row-group">
          {rows.map((row) => (
            <tr
              key={documentRowKey(row)}
              data-row-key={documentRowKey(row)}
              className={cn(
                "grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border p-4 first:border-t-0",
                "sm:table-row sm:border-t-0 sm:p-0 sm:hover:bg-surface-sunken",
              )}
            >
              <td className={cn(cellClass, "col-span-2 sm:pl-4")}>
                <button
                  type="button"
                  data-row-focus
                  aria-haspopup="dialog"
                  onClick={() => onOpenClient(row.client_id)}
                  className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus [overflow-wrap:anywhere]"
                >
                  {row.client_name}
                </button>
              </td>
              <td className={cellClass}>
                <InlineLabel>Type</InlineLabel>
                <AgreementTag wrap={false}>{row.kind}</AgreementTag>
              </td>
              <td className={cellClass}>
                <InlineLabel>File</InlineLabel>
                <span className="text-table text-text [overflow-wrap:anywhere]">{row.file_name}</span>
              </td>
              <td className={cellClass}>
                <InlineLabel>Source</InlineLabel>
                <SourceCell row={row} />
              </td>
              <td className={cellClass}>
                <InlineLabel>Uploaded by</InlineLabel>
                <span className="text-table text-text">{row.uploaded_by}</span>
              </td>
              <td className={cellClass}>
                <InlineLabel>Uploaded</InlineLabel>
                <span className="text-table text-text">{pacificDate(row.uploaded_at)}</span>
              </td>
              <td className={cn(cellClass, "col-span-2 sm:pr-4")}>
                <span className="flex flex-wrap items-center gap-1">
                  <Button
                    variant="tertiary"
                    size="sm"
                    aria-label={`Download ${row.client_name} ${row.kind}`}
                    onClick={() => onDownload(row)}
                  >
                    <span aria-hidden>↓</span>
                    Download
                  </Button>
                  {row.agreement_id ? (
                    <Button
                      variant="tertiary"
                      size="sm"
                      aria-haspopup="dialog"
                      aria-label={`History of ${row.client_name} ${row.kind}`}
                      onClick={() => onHistory(row)}
                    >
                      History
                    </Button>
                  ) : null}
                  <LockedButton
                    variant="tertiary"
                    size="sm"
                    aria-haspopup="dialog"
                    aria-label={`Replace ${row.client_name} ${row.kind}`}
                    lock={lock}
                    disabled={roles === null}
                    onClick={() => onReplace(row)}
                  >
                    Replace
                  </LockedButton>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceCell({ row }: { row: DocumentRow }) {
  if (row.source === "standard") {
    return (
      <span className="flex flex-col items-start gap-1">
        <AgreementTag tone="progress" wrap={false}>
          {row.standard_version ? `Standard v${row.standard_version}` : "Standard copy"}
        </AgreementTag>
        {isBatchLabel(row.batch_id) ? (
          <span className="text-secondary text-text-secondary">{`Batch ${row.batch_id}`}</span>
        ) : null}
      </span>
    );
  }
  return (
    <AgreementTag tone="success" wrap={false}>
      Client copy
    </AgreementTag>
  );
}

// --- History (moved here from the old register's RevisionDialog) --------------------------------

/** A stored version as the legacy versions route sends it; source, note and batch are additive (B1). */
type HistoryVersion = AgreementFileVersion & {
  source?: "client" | "standard" | null;
  standard_version?: number | null;
  batch_id?: string | null;
  note?: string | null;
};

export interface DocumentHistoryDrawerProps {
  row: DocumentRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A version download is audited: the page refreshes its Activity count. */
  onDownloaded?: () => void;
}

/** The same right drawer as every Agreements dialog (kicker: the client; it returns focus on close). */
export function DocumentHistoryDrawer({ row, open, onOpenChange, onDownloaded }: DocumentHistoryDrawerProps) {
  return (
    <AgreementsDrawer
      open={open && row !== null && Boolean(row.agreement_id)}
      onOpenChange={onOpenChange}
      kicker={row?.client_name ?? ""}
      title={row ? `${row.kind} document history` : "Document history"}
    >
      {row?.agreement_id ? (
        <HistoryBody key={row.agreement_id} agreementId={row.agreement_id} onDownloaded={onDownloaded} />
      ) : null}
    </AgreementsDrawer>
  );
}

function HistoryBody({ agreementId, onDownloaded }: { agreementId: string; onDownloaded?: () => void }) {
  const [versions, setVersions] = useState<HistoryVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    setVersions(null);
    listAgreementVersions(agreementId).then(
      (result) => {
        if (!live) return;
        setVersions(result.items as HistoryVersion[]);
        setError(null);
      },
      (err: unknown) => {
        if (live) setError(errorText(err, "The history could not load."));
      },
    );
    return () => {
      live = false;
    };
  }, [agreementId]);

  const download = async (version: number) => {
    setBusy(version);
    setStatus(null);
    setError(null);
    try {
      const link = await getAgreementVersionDownloadUrl(agreementId, version);
      window.open(link.url, "_blank", "noopener,noreferrer");
      setStatus(`A download link for version ${version} was created. It expires in 5 minutes and the download is recorded.`);
      onDownloaded?.();
    } catch (err) {
      setError(errorText(err, "The download could not start."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <p role="alert" className="text-body text-danger">
          {error}
        </p>
      ) : null}
      <p role="status" className="text-secondary text-text-secondary">
        {status ?? (versions === null && !error ? "Loading history…" : "")}
      </p>
      {versions !== null ? (
        versions.length ? (
          <ul className="flex flex-col">
            {versions.map((version) => (
              <li
                key={version.version_no}
                className="flex flex-wrap items-start justify-between gap-2 border-b border-border py-3 last:border-b-0"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-body font-semibold text-text [overflow-wrap:anywhere]">
                    {`v${version.version_no}: ${version.filename}`}
                  </span>
                  <span className="text-secondary text-text-secondary">
                    {`${version.uploaded_by_name} · ${pacificDate(version.uploaded_at)}`}
                  </span>
                  {version.source === "standard" ? (
                    <span className="text-secondary text-text-secondary">
                      {`Standard copy${version.standard_version ? ` v${version.standard_version}` : ""}${
                        isBatchLabel(version.batch_id) ? ` · batch ${version.batch_id}` : ""
                      }`}
                    </span>
                  ) : null}
                  {version.note?.trim() ? (
                    <span className="text-secondary text-text-secondary [overflow-wrap:anywhere]">{`Note: ${version.note}`}</span>
                  ) : null}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={`Download version ${version.version_no}`}
                  disabled={busy !== null}
                  onClick={() => void download(version.version_no)}
                >
                  <span aria-hidden>↓</span>
                  Download
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-body text-text-secondary">No stored versions.</p>
        )
      ) : null}
    </div>
  );
}
