/**
 * S24-AG1 · the NDA & MSA page (route /agreements; directive F1, F8, F9, F10,
 * F12). Built on one request per view, GET /agreements/workspace (B3): the
 * cutover line, six cards, the two standard documents and the client rows. The
 * Documents and Activity lists are asked for only while their tab is open.
 * Structure, behaviour and copy follow the approved prototype; the app's own kit
 * and tokens draw it, so light and dark follow data-theme.
 *
 * The URL holds every filter, the tab, the page and the open client panel
 * (agreementsState.ts), so a link or the back button restores the view. The
 * caller's rights come from the workspace (can_write / is_admin): a write the
 * caller may not use stays visible, locked with its reason; the server answers
 * 403 regardless. One dialog at a time; closing it returns focus to the control
 * that opened it. The dialogs and the client panel are the shared components in
 * ./agreements (UploadDialog, ClientAgreementsPanel, AttachWizard,
 * UndoBatchDialog, HubspotHintsDialog), opened through their props.
 *
 * Old links keep working: ?client_id= (or ?client=) opens that client's panel,
 * and ?client_id=…&kind=MSA&upload=1 (the client and deal pages) opens the
 * upload dialog for a writer, then the client's panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  downloadAgreementsCsv,
  getClientDownloadLink,
  getStandardDownloadLink,
  type AgreementKind,
  type Card,
  type DocumentRow,
} from "../../api/agreements";
import { ErrorState } from "../../ui-v2/ErrorState";
import { LOCK_TOAST } from "../../ui-v2/LockedButton";
import { useToast } from "../../ui-v2/primitives/toaster";
import { AgreementMetricCards } from "./agreements/AgreementMetricCards";
import { AgreementsHeader } from "./agreements/AgreementsHeader";
import { AgreementsRecords } from "./agreements/AgreementsRecords";
import { AttachWizard } from "./agreements/AttachWizard";
import { ClientAgreementsPanel } from "./agreements/ClientAgreementsPanel";
import { CutoverLine } from "./agreements/CutoverLine";
import { DocumentHistoryDrawer } from "./agreements/DocumentsTable";
import { HubspotHintsDialog } from "./agreements/HubspotHintsDialog";
import { StandardPanels } from "./agreements/StandardPanels";
import { UndoBatchDialog } from "./agreements/UndoBatchDialog";
import { UploadDialog, type UploadTarget } from "./agreements/UploadDialog";
import { errorText } from "./agreements/agreementsFormat";
import {
  applyCardDrill,
  firstMissingKind,
  listQueryOf,
  readAgreementsUrl,
  workspaceQueryOf,
  writeAgreementsUrl,
  type AgreementsClientRow,
  type AgreementsUrlState,
} from "./agreements/agreementsState";
import {
  useAgreementActivity,
  useAgreementDocuments,
  useAgreementRoles,
  useAgreementsWorkspace,
} from "./agreements/useAgreementsWorkspace";
import { plural } from "./pipeline/format";

type ShellDialog =
  | { kind: "upload"; target: UploadTarget }
  | { kind: "wizard" }
  | { kind: "hubspot" }
  | { kind: "undo"; label: string }
  | { kind: "history"; row: DocumentRow };

/** While a batch runs or is being undone, the page asks again this often so the cutover line keeps up. */
export const BATCH_POLL_MS = 4000;
/** How long after a dialog closes the page still puts focus back on its row when the row re-renders. */
const FOCUS_RETURN_WINDOW_MS = 10_000;

/** Focus the row's own focus target (its client name) when the control that opened a dialog is gone. */
function focusRow(key: string | null): boolean {
  if (!key) return false;
  const row = Array.from(document.querySelectorAll<HTMLElement>("[data-row-key]")).find(
    (el) => el.getAttribute("data-row-key") === key,
  );
  const target = row?.querySelector<HTMLElement>("[data-row-focus]");
  if (!target) return false;
  target.focus();
  return true;
}

function openLink(url: string) {
  window.open(url, "_blank", "noopener,noreferrer");
}

export function AgreementsRegisterPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlKey = searchParams.toString();
  const state = useMemo(() => readAgreementsUrl(new URLSearchParams(urlKey)), [urlKey]);
  const commit = useCallback(
    (next: AgreementsUrlState, opts: { replace?: boolean } = {}) => {
      setSearchParams(writeAgreementsUrl(next), { replace: opts.replace ?? false });
    },
    [setSearchParams],
  );
  const { toast } = useToast();

  // --- data: the workspace always; Documents and Activity only while their tab is open
  const wsQuery = useMemo(() => workspaceQueryOf(state), [state]);
  const ws = useAgreementsWorkspace(wsQuery);
  const { data, refetch: refetchWorkspace } = ws;
  const roles = useAgreementRoles(data);
  const listQuery = useMemo(() => listQueryOf(state), [state]);
  const documents = useAgreementDocuments(listQuery, state.tab === "documents");
  const activity = useAgreementActivity(listQuery, state.tab === "activity");
  const { refetch: refetchDocuments } = documents;
  const { refetch: refetchActivity } = activity;

  /** After any write: the workspace (cards, counts, rows) and the open list. The panel refreshes itself. */
  const refreshAll = useCallback(() => {
    refetchWorkspace();
    if (state.tab === "documents") refetchDocuments();
    if (state.tab === "activity") refetchActivity();
  }, [refetchWorkspace, refetchDocuments, refetchActivity, state.tab]);

  // A batch that runs (or is being undone) after its dialog closed: keep the cutover line current. An
  // interval, so one failed poll (which leaves the last answer in place) never stops the asking.
  const batchStatus = data?.cutover.latest_batch?.status;
  useEffect(() => {
    if (batchStatus !== "running" && batchStatus !== "undoing") return;
    const timer = window.setInterval(refetchWorkspace, BATCH_POLL_MS);
    return () => window.clearInterval(timer);
  }, [batchStatus, refetchWorkspace]);

  // --- one dialog at a time; focus returns to the control that opened the first one (F12)
  const [dialog, setDialog] = useState<ShellDialog | null>(null);
  // The open dialog's kind, kept in step with every open and close, so a dialog that finishes after it was
  // closed (its request still in flight) never closes the one opened after it.
  const openKind = useRef<ShellDialog["kind"] | null>(null);
  const modal = useRef(state.clientId !== null);
  const opener = useRef<HTMLElement | null>(null);
  const openerRow = useRef<string | null>(null);
  const pendingRow = useRef<{ key: string; at: number } | null>(null);
  useEffect(() => {
    modal.current = dialog !== null || state.clientId !== null;
  }, [dialog, state.clientId]);

  const rememberOpener = useCallback(() => {
    if (modal.current) return; // moving from one dialog to the next keeps the first opener
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    opener.current = active && active !== document.body ? active : null;
    openerRow.current = active?.closest("[data-row-key]")?.getAttribute("data-row-key") ?? null;
  }, []);

  const restoreFocus = useCallback(() => {
    const row = openerRow.current;
    pendingRow.current = row ? { key: row, at: Date.now() } : null;
    // After Radix has unmounted the dialog (its own focus return has no trigger to go to).
    window.setTimeout(() => {
      if (modal.current) return;
      const el = opener.current;
      if (el?.isConnected) el.focus();
      else focusRow(row);
    }, 0);
  }, []);

  // Once the person clicks or types again, the page never moves their focus.
  useEffect(() => {
    const clear = () => {
      pendingRow.current = null;
    };
    document.addEventListener("pointerdown", clear, true);
    document.addEventListener("keydown", clear, true);
    return () => {
      document.removeEventListener("pointerdown", clear, true);
      document.removeEventListener("keydown", clear, true);
    };
  }, []);

  // The control that opened a dialog can be re-rendered away by the refresh after a write
  // (a client that no longer needs attention loses "↑ Upload client copy"): focus its row instead.
  useEffect(() => {
    const pending = pendingRow.current;
    if (!pending || modal.current) return;
    if (Date.now() - pending.at > FOCUS_RETURN_WINDOW_MS) {
      pendingRow.current = null;
      return;
    }
    const active = document.activeElement;
    if (!active || active === document.body) {
      if (focusRow(pending.key)) pendingRow.current = null;
    }
  }, [data, documents.data]);

  const openDialog = useCallback(
    (next: ShellDialog) => {
      rememberOpener();
      modal.current = true;
      openKind.current = next.kind;
      setDialog(next);
    },
    [rememberOpener],
  );

  const closeDialog = useCallback(
    (kind: ShellDialog["kind"]) => {
      if (openKind.current !== kind) return; // closed already, or another dialog is open now
      openKind.current = null;
      // A legacy upload link also names a client: its panel opens next and takes the focus.
      const panelNext = state.clientId !== null;
      modal.current = panelNext;
      setDialog(null);
      if (!panelNext) restoreFocus();
    },
    [restoreFocus, state.clientId],
  );

  /** One close handler per dialog kind: each closes only its own dialog. */
  const dialogOpenChange = useMemo(() => {
    const of = (kind: ShellDialog["kind"]) => (open: boolean) => {
      if (!open) closeDialog(kind);
    };
    return { upload: of("upload"), wizard: of("wizard"), hubspot: of("hubspot"), undo: of("undo"), history: of("history") };
  }, [closeDialog]);

  const openClient = useCallback(
    (clientId: string) => {
      rememberOpener();
      modal.current = true;
      commit({ ...state, clientId }, { replace: true });
    },
    [commit, rememberOpener, state],
  );

  const closePanel = useCallback(() => {
    modal.current = false;
    commit({ ...state, clientId: null }, { replace: true });
    restoreFocus();
  }, [commit, restoreFocus, state]);

  // --- old links: ?kind=…&upload=1 opens the upload dialog for a writer; then they leave the URL
  useEffect(() => {
    if (!state.upload && !state.kind) return;
    if (state.upload && roles === null && !ws.error) return; // wait until the caller's rights are known
    if (state.upload) {
      if (roles?.canWrite) {
        const row = data?.items.find((r) => r.client_id === state.clientId);
        openDialog({
          kind: "upload",
          target: {
            mode: "client",
            clientId: state.clientId,
            clientName: row?.name ?? null,
            kind: state.kind ?? undefined,
            lockTarget: state.clientId !== null,
          },
        });
      } else if (roles) {
        toast({ title: LOCK_TOAST.writer });
      }
    }
    commit({ ...state, kind: null, upload: false }, { replace: true });
  }, [commit, data, openDialog, roles, state, toast, ws.error]);

  // --- actions
  const onDrill = useCallback((card: Card) => commit(applyCardDrill(state, card.drill)), [commit, state]);

  const [exporting, setExporting] = useState(false);
  const onExport = useCallback(async () => {
    setExporting(true);
    try {
      const filename = await downloadAgreementsCsv(wsQuery);
      const n = data?.total;
      toast({
        title: `Downloaded ${filename}.`,
        description:
          typeof n === "number"
            ? `${n} ${plural(n, "client", "clients")} from the filtered view, every row, not just this page.`
            : undefined,
      });
      refetchWorkspace(); // the export is recorded: the Activity count moves
    } catch (err) {
      toast({
        title: "The export could not download.",
        description: errorText(err, "Try again."),
        variant: "destructive",
      });
    } finally {
      setExporting(false);
    }
  }, [data?.total, refetchWorkspace, toast, wsQuery]);

  const onDownloadStandard = useCallback(
    async (kind: AgreementKind) => {
      try {
        const link = await getStandardDownloadLink(kind);
        openLink(link.url);
        toast({
          title: `A download link for the standard ${kind} was created. It expires in 5 minutes and the download is recorded.`,
        });
        refetchWorkspace();
      } catch (err) {
        toast({
          title: `The standard ${kind} could not download.`,
          description: errorText(err, "Try again."),
          variant: "destructive",
        });
      }
    },
    [refetchWorkspace, toast],
  );

  const onDownloadDocument = useCallback(
    async (row: DocumentRow) => {
      try {
        const link = await getClientDownloadLink(row.client_id, row.kind);
        openLink(link.url);
        toast({
          title: `A download link for ${row.client_name}'s ${row.kind} was created. It expires in 5 minutes and the download is recorded.`,
        });
        refetchWorkspace();
      } catch (err) {
        toast({
          title: `${row.client_name}'s ${row.kind} could not download.`,
          description: errorText(err, "Try again."),
          variant: "destructive",
        });
      }
    },
    [refetchWorkspace, toast],
  );

  const uploadForRow = useCallback(
    (row: AgreementsClientRow) =>
      openDialog({
        kind: "upload",
        target: {
          mode: "client",
          clientId: row.client_id,
          clientName: row.name,
          kind: firstMissingKind(row),
          lockTarget: true,
        },
      }),
    [openDialog],
  );

  const replaceDocument = useCallback(
    (row: DocumentRow) =>
      openDialog({
        kind: "upload",
        target: { mode: "client", clientId: row.client_id, clientName: row.client_name, kind: row.kind, lockTarget: true },
      }),
    [openDialog],
  );

  const panelOpen = dialog === null && state.clientId !== null;

  return (
    <div className="flex flex-col gap-6">
      <AgreementsHeader
        roles={roles}
        exporting={exporting}
        onExport={() => void onExport()}
        onHubspotHints={() => openDialog({ kind: "hubspot" })}
        onAttachStandard={() => openDialog({ kind: "wizard" })}
        onUpload={() => openDialog({ kind: "upload", target: { mode: "client" } })}
      />
      {!data && !ws.error ? (
        <p role="status" className="text-body text-text-secondary">
          Loading NDA &amp; MSA…
        </p>
      ) : null}
      {/* On the Clients tab a failed load is reported once, in the records panel (with Try again). */}
      {!data && ws.error && state.tab !== "clients" ? (
        <ErrorState
          title="The NDA and MSA records could not load."
          description={ws.error}
          retryLabel="Try again"
          onRetry={refetchWorkspace}
        />
      ) : null}
      {data ? (
        <>
          <CutoverLine
            cutover={data.cutover}
            standard={data.standard}
            roles={roles}
            onUndo={(label) => openDialog({ kind: "undo", label })}
          />
          <AgreementMetricCards cards={data.cards} onDrill={onDrill} />
          <StandardPanels
            standard={data.standard}
            roles={roles}
            onUpload={(kind) => openDialog({ kind: "upload", target: { mode: "standard", kind } })}
            onDownload={(kind) => void onDownloadStandard(kind)}
          />
        </>
      ) : null}
      <AgreementsRecords
        state={state}
        onStateChange={commit}
        workspace={data}
        workspaceLoading={ws.loading}
        workspaceError={ws.error}
        onRetryWorkspace={refetchWorkspace}
        documents={documents}
        activity={activity}
        roles={roles}
        onOpenClient={openClient}
        onUploadClientCopy={uploadForRow}
        onDownloadDocument={(row) => void onDownloadDocument(row)}
        onDocumentHistory={(row) => openDialog({ kind: "history", row })}
        onReplaceDocument={replaceDocument}
      />

      <UploadDialog
        open={dialog?.kind === "upload"}
        target={dialog?.kind === "upload" ? dialog.target : null}
        canWrite={roles?.canWrite === true}
        onOpenChange={dialogOpenChange.upload}
        onUploaded={() => {
          closeDialog("upload");
          refreshAll();
        }}
        onBackToWizard={() => openDialog({ kind: "wizard" })}
      />
      <AttachWizard open={dialog?.kind === "wizard"} onOpenChange={dialogOpenChange.wizard} onChanged={refreshAll} />
      <HubspotHintsDialog
        open={dialog?.kind === "hubspot"}
        onOpenChange={dialogOpenChange.hubspot}
        isAdmin={roles?.isAdmin === true}
        onChanged={refreshAll}
      />
      <UndoBatchDialog
        open={dialog?.kind === "undo"}
        label={dialog?.kind === "undo" ? dialog.label : null}
        onOpenChange={dialogOpenChange.undo}
        onChanged={refreshAll}
      />
      <DocumentHistoryDrawer
        row={dialog?.kind === "history" ? dialog.row : null}
        open={dialog?.kind === "history"}
        onOpenChange={dialogOpenChange.history}
        onDownloaded={refetchWorkspace}
      />
      {state.clientId ? (
        <ClientAgreementsPanel
          key={state.clientId}
          clientId={state.clientId}
          variant="drawer"
          open={panelOpen}
          onOpenChange={(open) => {
            if (!open) closePanel();
          }}
          onChanged={refreshAll}
        />
      ) : null}
    </div>
  );
}
