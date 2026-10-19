// S24-AG1 F1/F8/F9 · the records under the cards and standard panels: the
// Clients / Documents / Activity tabs with counts, the filter toolbar and chips,
// then the open tab's basis line, list (or its empty state) and paging. The
// page (AgreementsRegister.tsx) owns every piece of state; this panel asks for
// changes through `onStateChange` and the callbacks.
import { clsx } from "clsx";
import { useEffect, type ReactNode } from "react";

import type { ActivityRow, AgreementsWorkspace, DocumentRow } from "../../../api/agreements";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { Button } from "../../../ui-v2/primitives/button";
import { plural } from "../pipeline/format";
import { Glyph } from "../pipeline/tags";
import { ActivityTable } from "./ActivityTable";
import { AgreementsChips } from "./AgreementsChips";
import { AgreementsClientsTable } from "./AgreementsClientsTable";
import { AgreementsPagination, pageCount } from "./AgreementsPagination";
import { AgreementsToolbar } from "./AgreementsToolbar";
import { DocumentsTable } from "./DocumentsTable";
import { AgreementNote } from "./UploadForm";
import {
  resetFilters,
  setTab,
  withFilters,
  type AgreementsClientRow,
  type AgreementsTab,
  type AgreementsUrlState,
} from "./agreementsState";
import type { AgreementRoles, ListPage, QueryResult } from "./useAgreementsWorkspace";

export interface AgreementsRecordsProps {
  state: AgreementsUrlState;
  /** `replace` marks a correction the user did not ask for (a page past the end) or a search keystroke. */
  onStateChange: (next: AgreementsUrlState, opts?: { replace?: boolean }) => void;
  workspace: AgreementsWorkspace | null;
  workspaceLoading: boolean;
  workspaceError: string | null;
  onRetryWorkspace: () => void;
  documents: QueryResult<ListPage<DocumentRow>>;
  activity: QueryResult<ListPage<ActivityRow>>;
  roles: AgreementRoles | null;
  onOpenClient: (clientId: string) => void;
  onUploadClientCopy: (row: AgreementsClientRow) => void;
  onDownloadDocument: (row: DocumentRow) => void;
  onDocumentHistory: (row: DocumentRow) => void;
  onReplaceDocument: (row: DocumentRow) => void;
}

function count(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

export function AgreementsRecords(props: AgreementsRecordsProps) {
  const { state, onStateChange, workspace, documents, activity, roles } = props;
  const tab = state.tab;
  const onReset = () => onStateChange(resetFilters(state));
  const go = (next: AgreementsTab) => {
    if (next !== tab) onStateChange(setTab(state, next));
  };

  // Tab counts: the open list's own total (it follows its search); otherwise the workspace's count.
  const counts: Record<AgreementsTab, number | undefined> = {
    clients: count(workspace?.total),
    documents: tab === "documents" && documents.data ? documents.data.total : count(workspace?.document_count),
    activity: tab === "activity" && activity.data ? activity.data.total : count(workspace?.activity_count),
  };

  let basis: string | null = null;
  let body: ReactNode;
  let total = 0;
  let shown = 0;
  let ready = false;
  let busy = false;

  if (tab === "clients") {
    busy = props.workspaceLoading;
    if (props.workspaceError && !workspace) {
      body = (
        <ErrorState
          className="m-4"
          title="The clients could not load."
          description={props.workspaceError}
          retryLabel="Try again"
          onRetry={props.onRetryWorkspace}
        />
      );
    } else if (!workspace) {
      body = <LoadingLine text="Loading clients…" />;
    } else {
      ready = true;
      total = workspace.total;
      shown = workspace.items.length;
      basis = `${total} ${plural(total, "client", "clients")} · same population as the cards above`;
      const list =
        total === 0 && shown === 0 ? (
          <NoMatch what="No clients match this view." onReset={onReset} />
        ) : (
          <AgreementsClientsTable
            rows={workspace.items as AgreementsClientRow[]}
            roles={roles}
            onOpenClient={props.onOpenClient}
            onUploadClientCopy={props.onUploadClientCopy}
          />
        );
      // A failed refresh (a poll while a batch runs, or after a write) keeps the rows already loaded.
      body = props.workspaceError ? (
        <>
          <div role="alert" className="m-4 flex flex-col items-start gap-2">
            <AgreementNote tone="warning">
              {`The clients could not refresh; this is the last list loaded. ${props.workspaceError}`}
            </AgreementNote>
            <Button variant="secondary" onClick={props.onRetryWorkspace}>
              Try again
            </Button>
          </div>
          {list}
        </>
      ) : (
        list
      );
    }
  } else if (tab === "documents") {
    busy = documents.loading;
    if (documents.error) {
      body = (
        <ErrorState
          className="m-4"
          title="The documents could not load."
          description={documents.error}
          retryLabel="Try again"
          onRetry={documents.refetch}
        />
      );
    } else if (!documents.data) {
      body = <LoadingLine text="Loading documents…" />;
    } else {
      ready = true;
      total = documents.data.total;
      shown = documents.data.items.length;
      basis = `${total} ${plural(total, "document", "documents")} · one row per client and type`;
      body =
        total === 0 && shown === 0 ? (
          state.q.trim() ? (
            <NoMatch what="No documents match this view." onReset={onReset} />
          ) : (
            <EmptyState
              className="m-4"
              title="No documents yet."
              description="Upload the standard NDA and MSA, or a client copy."
            />
          )
        ) : (
          <DocumentsTable
            rows={documents.data.items}
            roles={roles}
            onOpenClient={props.onOpenClient}
            onDownload={props.onDownloadDocument}
            onHistory={props.onDocumentHistory}
            onReplace={props.onReplaceDocument}
          />
        );
    }
  } else {
    busy = activity.loading;
    if (activity.error) {
      body = (
        <ErrorState
          className="m-4"
          title="The activity could not load."
          description={activity.error}
          retryLabel="Try again"
          onRetry={activity.refetch}
        />
      );
    } else if (!activity.data) {
      body = <LoadingLine text="Loading activity…" />;
    } else {
      ready = true;
      total = activity.data.total;
      shown = activity.data.items.length;
      basis = `${total} ${plural(total, "event", "events")} · uploads, attachments, marks, undo and downloads`;
      body =
        total === 0 && shown === 0 ? (
          state.q.trim() ? (
            <NoMatch what="No activity matches this view." onReset={onReset} />
          ) : (
            <EmptyState
              className="m-4"
              title="No agreement activity yet."
              description="Every upload, attach, mark, undo and download is recorded here and in the audit log."
            />
          )
        ) : (
          <ActivityTable rows={activity.data.items} />
        );
    }
  }

  // A page past the end (an old link, or rows that went away) moves to the last page, in place
  // of the empty page in the history.
  const lastPage = pageCount(total, state.page_size);
  const pastEnd = ready && shown === 0 && total > 0 && state.page > lastPage;
  useEffect(() => {
    if (pastEnd) onStateChange({ ...state, page: lastPage }, { replace: true });
    // Only when an answer says the page is past the end.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pastEnd, lastPage]);

  return (
    <section aria-label="Agreement records" aria-busy={busy} className="flex min-w-0 flex-col gap-3">
      <div role="group" aria-label="Records" className="flex flex-wrap items-end gap-x-6 gap-y-2 border-b border-border">
        <TabButton pressed={tab === "clients"} label="Clients" count={counts.clients} onClick={() => go("clients")} />
        <TabButton pressed={tab === "documents"} label="Documents" count={counts.documents} onClick={() => go("documents")} />
        <TabButton pressed={tab === "activity"} label="Activity" count={counts.activity} onClick={() => go("activity")} />
      </div>
      <AgreementsToolbar
        state={state}
        onSearch={(q) => onStateChange(withFilters(state, { q }), { replace: state.q.trim() !== "" })}
        onRelationship={(relationship) => onStateChange(withFilters(state, { relationship }))}
        onStatus={(status) => onStateChange(withFilters(state, { status }))}
        onStage={(stage) => onStateChange(withFilters(state, { stage }))}
        onBusinessUnits={(bu) => onStateChange(withFilters(state, { bu }))}
        onSort={(sort) => onStateChange(withFilters(state, { sort }))}
      />
      <AgreementsChips state={state} onChange={(next) => onStateChange(next)} onReset={onReset} />
      <div className="min-w-0 overflow-hidden rounded-panel border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <p className="min-h-[18px] text-secondary text-text-secondary">{basis}</p>
        </div>
        {body}
        {ready ? (
          <AgreementsPagination
            total={total}
            page={state.page}
            pageSize={state.page_size}
            onPage={(page) => onStateChange({ ...state, page })}
            onPageSize={(page_size) => onStateChange({ ...state, page_size, page: 1 })}
          />
        ) : null}
      </div>
    </section>
  );
}

function LoadingLine({ text }: { text: string }) {
  return (
    <p role="status" className="px-4 py-8 text-center text-body text-text-secondary">
      {text}
    </p>
  );
}

function NoMatch({ what, onReset }: { what: string; onReset: () => void }) {
  return (
    <EmptyState
      className="m-4"
      title={what}
      description="Remove a filter or reset the view."
      action={
        <button
          type="button"
          onClick={onReset}
          className="rounded-control text-body font-semibold text-primary hover:underline focus-visible:outline-focus"
        >
          Reset filters
          <Glyph>→</Glyph>
        </button>
      }
    />
  );
}

function TabButton({
  pressed,
  onClick,
  label,
  count: n,
}: {
  pressed: boolean;
  onClick: () => void;
  label: string;
  count: number | undefined;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={clsx(
        "-mb-px inline-flex items-center gap-2 border-b-2 px-1 pb-2 text-body transition-motion focus-visible:outline-focus",
        pressed ? "border-primary font-semibold text-text" : "border-transparent text-text-secondary hover:text-text",
      )}
    >
      {label}{" "}
      {n !== undefined ? (
        <span className="rounded-chip bg-surface-sunken px-1.5 font-mono text-secondary text-text-secondary tnum">{n}</span>
      ) : null}
    </button>
  );
}
