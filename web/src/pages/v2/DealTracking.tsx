import { useState } from "react";
import { Check, Pencil, Pin, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { ApiError, createDealComment, createNextAction, deleteDealComment, patchDealComment, patchNextAction,
  type DealCommentList, type DealCommentRow, type NextActionList, type NextActionRow } from "../../api/client";
import { Button } from "../../ui-v2/primitives/button";

const inputClass = "w-full rounded border border-divider bg-surface px-2 py-1.5 text-body text-text";

export function DealTracking({ opportunityId, actions, comments, refresh }: {
  opportunityId: string; actions: NextActionList; comments: DealCommentList; refresh: () => Promise<void>;
}) {
  const [commentDraft, setCommentDraft] = useState<{ row: DealCommentRow | null; body: string } | null>(null);
  const [actionDraft, setActionDraft] = useState<{ row: NextActionRow | null; title: string; assignee: string; due: string } | null>(null);
  const [deleting, setDeleting] = useState<DealCommentRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function mutate(operation: () => Promise<unknown>, close?: () => void, refreshAfter = true) {
    setBusy(true);
    setError(null);
    try {
      await operation();
      close?.();
      if (refreshAfter) await refresh();
    } catch (err) {
      setError(err instanceof ApiError && (err.status === 409 || err.status === 428)
        ? "This record changed. Reload tracking and reopen the editor before saving. Your draft has not been submitted."
        : err instanceof Error ? err.message : "Unable to update tracking.");
    } finally { setBusy(false); }
  }

  function revision(row: { revision?: string }): string {
    if (!row.revision) throw new Error("Revision unavailable. Reload tracking before editing.");
    return row.revision;
  }

  return <div className="space-y-4">
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-danger">
      <span>{error}</span>
      <Button variant="secondary" disabled={busy} onClick={() => void mutate(refresh, undefined, false)}>
        <RefreshCw className="mr-1 h-4 w-4" aria-hidden />Reload tracking
      </Button>
    </div>}
    <div className="grid gap-6 md:grid-cols-2">
      <section aria-label="Next action" data-testid="deal-next-action" className="min-w-0 border-t border-divider pt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-heading-3 text-text">Next actions</h2>
          {actions.can_create && <Button variant="secondary" disabled={busy} onClick={() => setActionDraft({ row: null, title: "", assignee: actions.assignees?.[0]?.id ?? "", due: "" })}>
            <Plus className="mr-1 h-4 w-4" aria-hidden />Add action
          </Button>}
        </div>
        {actionDraft && <form aria-label="Action editor" className="mb-4 space-y-3" onSubmit={e => {
          e.preventDefault();
          const draft = actionDraft;
          void mutate(() => draft.row ? patchNextAction(draft.row.id, {
            expected_revision: revision(draft.row), title: draft.title.trim(), assignee_user_id: draft.assignee,
            due_date: draft.due || null, clear_due_date: !draft.due,
          }) : createNextAction({ opportunity_id: opportunityId, title: draft.title.trim(), assignee_user_id: draft.assignee, due_date: draft.due || null }), () => setActionDraft(null));
        }}>
          <label className="block text-secondary">Action title<input className={inputClass} required maxLength={255} value={actionDraft.title} onChange={e => setActionDraft({ ...actionDraft, title: e.target.value })} /></label>
          <label className="block text-secondary">Assignee<select className={inputClass} required value={actionDraft.assignee} onChange={e => setActionDraft({ ...actionDraft, assignee: e.target.value })}>
            <option value="">Select assignee</option>
            {actions.assignees?.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select></label>
          <label className="block text-secondary">Due date<input className={inputClass} type="date" value={actionDraft.due} onChange={e => setActionDraft({ ...actionDraft, due: e.target.value })} /></label>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !actionDraft.title.trim() || !actionDraft.assignee}><Save className="mr-1 h-4 w-4" aria-hidden />Save action</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setActionDraft(null)}><X className="mr-1 h-4 w-4" aria-hidden />Cancel</Button>
          </div>
        </form>}
        {!actions.items.length && <p className="text-body text-text-secondary">No next actions.</p>}
        <ol className="divide-y divide-divider">
          {actions.items.map(row => <li key={row.id} className="py-3" data-testid={`next-action-${row.id}`}>
            <div className="break-words font-medium text-text">{row.title || row.description}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-secondary text-text-secondary">
              <span data-testid={`next-action-status-${row.status}`}>{row.status}</span>
              <span>{actions.assignees?.find(p => p.id === (row.assignee_user_id ?? row.owner_user_id))?.name ?? "Assignee unavailable"}</span>
              <span>{row.due_date ? `Due ${row.due_date}` : "No due date"}</span>
              {row.can_edit && <>
                <button type="button" disabled={busy} title="Edit action" aria-label="Edit action" className="p-2" onClick={() => setActionDraft({ row, title: row.title || row.description, assignee: row.assignee_user_id ?? row.owner_user_id, due: row.due_date ?? "" })}><Pencil className="h-4 w-4" /></button>
                {row.status !== "complete" && !row.approval_package_id && <button type="button" disabled={busy} title="Mark complete" aria-label="Mark complete" data-testid={`next-action-complete-${row.id}`} className="p-2" onClick={() => void mutate(() => patchNextAction(row.id, { expected_revision: revision(row), status: "complete" }))}><Check className="h-4 w-4" /></button>}
              </>}
            </div>
            {row.blocker && <p className="text-secondary">Blocker: {row.blocker}</p>}
            {row.outcome && <p className="text-secondary">Outcome: {row.outcome}</p>}
          </li>)}
        </ol>
      </section>
      <section aria-label="Comments" data-testid="deal-latest-comment" className="min-w-0 border-t border-divider pt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-heading-3 text-text">Comments</h2>
          {comments.can_create && <Button variant="secondary" disabled={busy} onClick={() => setCommentDraft({ row: null, body: "" })}><Plus className="mr-1 h-4 w-4" aria-hidden />Add comment</Button>}
        </div>
        {commentDraft && <form aria-label="Comment editor" className="mb-4 space-y-3" onSubmit={e => {
          e.preventDefault();
          const draft = commentDraft;
          void mutate(() => draft.row ? patchDealComment(draft.row.id, { expected_revision: revision(draft.row), body: draft.body.trim() }) : createDealComment(opportunityId, draft.body.trim()), () => setCommentDraft(null));
        }}>
          <label htmlFor="tracking-comment" className="block text-secondary">Comment</label>
          <textarea id="tracking-comment" className={inputClass} rows={4} required value={commentDraft.body} onChange={e => setCommentDraft({ ...commentDraft, body: e.target.value })} />
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !commentDraft.body.trim()}><Save className="mr-1 h-4 w-4" aria-hidden />Save comment</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setCommentDraft(null)}><X className="mr-1 h-4 w-4" aria-hidden />Cancel</Button>
          </div>
        </form>}
        {!comments.items.length && <p className="text-body text-text-secondary">No comments yet.</p>}
        <ol className="divide-y divide-divider">
          {comments.items.map(row => <li key={row.id} className="py-3" data-testid={`comment-${row.id}`}>
            <div className="whitespace-pre-wrap break-words text-body text-text">{row.body}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-secondary text-text-secondary">
              <span>{row.author_name || row.author_name_fallback || "Author unavailable"}</span>
              <time dateTime={row.edited_at || row.created_at}>{new Date(row.edited_at || row.created_at).toLocaleString()}</time>
              {row.edited_at && <span>Edited</span>}
              {row.source === "hubspot_note" && <span>HubSpot note</span>}
              {row.pinned && <span>Pinned</span>}
              {row.source === "internal" && row.can_edit && <>
                <button type="button" className="p-2" disabled={busy} title="Edit comment" aria-label="Edit comment" onClick={() => setCommentDraft({ row, body: row.body })}><Pencil className="h-4 w-4" /></button>
                <button type="button" className="p-2" disabled={busy} title={row.pinned ? "Unpin comment" : "Pin comment"} aria-label={row.pinned ? "Unpin comment" : "Pin comment"} onClick={() => void mutate(() => patchDealComment(row.id, { expected_revision: revision(row), pinned: !row.pinned }))}><Pin className="h-4 w-4" /></button>
              </>}
              {row.source === "internal" && row.can_delete && <button type="button" className="p-2" disabled={busy} title="Delete comment" aria-label="Delete comment" onClick={() => setDeleting(row)}><Trash2 className="h-4 w-4" /></button>}
            </div>
            {deleting?.id === row.id && <div role="alertdialog" aria-label="Delete comment" className="mt-2 space-y-2">
              <p>Delete this comment? Its history is retained.</p>
              <Button disabled={busy} onClick={() => void mutate(() => deleteDealComment(row.id, revision(row)), () => setDeleting(null))}>Delete</Button>
              <Button variant="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel</Button>
            </div>}
          </li>)}
        </ol>
      </section>
    </div>
  </div>;
}
