import { useCallback, useEffect, useId, useRef, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { ApiError } from "../api/client";
import { getExtractionConflicts, resolveExtractionConflict, type ExtractionConflict } from "../api/extraction-conflicts";
import { Button } from "../ui-v2/primitives/button";

type Decision = "keep_confirmed" | "accept_candidate";
type Draft = { reviewToken: string; choice?: Decision; reason: string };
function failure(error: unknown) {
  if (error instanceof ApiError) {
    const detail = (error.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "Extraction review unavailable";
}
function display(value: unknown) {
  return value == null ? "Not supplied" : typeof value === "string" ? value : JSON.stringify(value);
}

export function ExtractionConflicts({ versionId, onResolved }: { versionId: string; onResolved: () => void }) {
  const prefix = useId();
  const generation = useRef(0);
  const [items, setItems] = useState<ExtractionConflict[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const receive = useCallback((next: ExtractionConflict[]) => {
    setDrafts((prior) => Object.fromEntries(next.flatMap((item) => {
      const draft = prior[item.field];
      return draft?.reviewToken === item.review_token ? [[item.field, draft] as const] : [];
    })));
    setItems(next);
  }, []);
  function draftFor(item: ExtractionConflict) {
    const draft = drafts[item.field];
    return draft?.reviewToken === item.review_token ? draft : undefined;
  }
  function changeDraft(item: ExtractionConflict, change: Partial<Pick<Draft, "choice" | "reason">>) {
    setDrafts((prior) => ({ ...prior, [item.field]: {
      ...(prior[item.field]?.reviewToken === item.review_token ? prior[item.field] : { reviewToken: item.review_token, reason: "" }),
      ...change,
    } }));
  }
  const reload = useCallback(async () => {
    const token = ++generation.current;
    setBusy(true); setError("");
    try {
      const result = await getExtractionConflicts(versionId);
      if (token === generation.current) receive(result.items);
    } catch (caught) { if (token === generation.current) setError(failure(caught)); }
    finally { if (token === generation.current) setBusy(false); }
  }, [versionId, receive]);
  useEffect(() => {
    setItems(null); setDrafts({}); void reload();
    return () => { generation.current += 1; };
  }, [reload]);
  async function save(item: ExtractionConflict) {
    const draft = draftFor(item);
    if (busy || !draft?.choice || !draft.reason.trim()) return;
    const token = generation.current;
    setBusy(true); setError("");
    try {
      const result = await resolveExtractionConflict(versionId, item.field, { review_token: draft.reviewToken,
        decision: draft.choice, reason: draft.reason.trim() });
      if (token !== generation.current) return;
      receive(result.items); onResolved();
    } catch (caught) { if (token === generation.current) setError(failure(caught)); }
    finally { if (token === generation.current) setBusy(false); }
  }
  return <section aria-labelledby={`${prefix}-title`} className="min-w-0 space-y-4 border-b pb-5">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id={`${prefix}-title`} className="text-lg font-semibold">Extraction conflicts</h2>
      <Button variant="secondary" disabled={busy} onClick={() => void reload()}>
        <RefreshCw className="h-4 w-4" />Reload conflicts</Button>
    </header>
    {busy && <p role="status">Loading review...</p>}
    {error && <p role="alert" className="break-words text-danger">{error}</p>}
    {items?.length === 0 && !error && <p>No unresolved extraction conflicts</p>}
    {items?.map((item) => <form key={item.field} className="space-y-3 border-t py-4"
      onSubmit={(event) => { event.preventDefault(); void save(item); }}>
      <h3 className="break-words text-base font-semibold capitalize">{item.field.replaceAll("_", " ")}</h3>
      <dl className="grid min-w-0 gap-4 sm:grid-cols-2">
        {([["Confirmed value", item.current], ["New extraction", item.candidate]] as const).map(([label, field]) =>
          <div key={label} className="min-w-0 space-y-1">
            <dt className="text-sm font-medium">{label}</dt>
            <dd className="whitespace-pre-wrap break-words text-sm">{display(field.value)}</dd>
            <dd className="text-sm text-text-secondary">{field.provenance ?? "Unknown provenance"}; source reference {field.page_ref ?? "unavailable"}</dd>
          </div>)}
      </dl>
      <fieldset disabled={busy} className="flex flex-wrap gap-4">
        <legend className="sr-only">Decision for {item.field}</legend>
        {([["keep_confirmed", "Keep confirmed value"], ["accept_candidate", "Accept new extraction"]] as const).map(([value, label]) =>
          <label key={value} className="flex items-center gap-2 text-sm"><input type="radio" name={`${prefix}-${item.field}`}
            value={value} checked={draftFor(item)?.choice === value}
            onChange={() => changeDraft(item, { choice: value })} />{label}</label>)}
      </fieldset>
      <div className="space-y-1">
        <label htmlFor={`${prefix}-${item.field}-reason`} className="text-sm">Review reason</label>
        <textarea id={`${prefix}-${item.field}-reason`} rows={2} maxLength={2000} required disabled={busy}
          className="block w-full rounded-md border bg-background p-2" value={draftFor(item)?.reason ?? ""}
          onChange={(event) => changeDraft(item, { reason: event.target.value })} />
      </div>
      <Button type="submit" disabled={busy || !draftFor(item)?.choice || !draftFor(item)?.reason.trim()}>
        <Save className="h-4 w-4" />Save review</Button>
    </form>)}
  </section>;
}
