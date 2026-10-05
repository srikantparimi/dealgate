import { useEffect, useId, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, RotateCcw, Save } from "lucide-react";
import { ApiError } from "../api/client";
import { getAutomationHistory, getAutomationJobs, getAutomationRule, retryAutomationJob, saveAutomationRule,
  type AutomationJob, type AutomationJobs, type AutomationRule } from "../api/sourcing-automation";
import { Button } from "../ui-v2/primitives/button";

function failure(error: unknown) {
  if (error instanceof ApiError) {
    const detail = (error.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "Automation request failed";
}

export function SourcingAutomation() {
  const prefix = useId();
  const [rule, setRule] = useState<AutomationRule | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [reason, setReason] = useState("");
  const [jobs, setJobs] = useState<AutomationJobs | null>(null);
  const [history, setHistory] = useState<AutomationRule[]>([]);
  const [page, setPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [retryReasons, setRetryReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const request = useRef({ body: "", key: "" });

  async function reload(resetRule = true) {
    const token = ++generation.current;
    setLoading(true);
    try {
      const [current, nextJobs, revisions] = await Promise.all([
        getAutomationRule(), getAutomationJobs(page), getAutomationHistory(historyPage),
      ]);
      if (token !== generation.current) return;
      if (resetRule) { setRule(current); setEnabled(current.enabled); }
      setJobs(nextJobs);
      setHistory(revisions.items);
      setError("");
    } catch (caught) {
      if (token === generation.current) setError(failure(caught));
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  useEffect(() => {
    void reload(!rule);
    return () => { generation.current += 1; };
  }, [page, historyPage]);

  async function save() {
    if (!rule) return;
    const body = { expected_version_id: rule.id, enabled, reason: reason.trim() };
    const serialized = JSON.stringify(body);
    if (request.current.body !== serialized) request.current = { body: serialized, key: crypto.randomUUID() };
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await saveAutomationRule({ ...body, request_key: request.current.key });
      setRule(next); setEnabled(next.enabled); setReason("");
      setNotice(`Automation revision ${next.revision} saved`);
      await reload(false);
    } catch (caught) { setError(failure(caught)); }
    finally { setBusy(false); }
  }
  async function retry(job: AutomationJob) {
    setBusy(true); setError(""); setNotice("");
    try {
      await retryAutomationJob(job.id, { expected_attempts: job.attempts, reason: retryReasons[job.id].trim() });
      setRetryReasons((current) => ({ ...current, [job.id]: "" }));
      setNotice("Job queued");
      await reload(false);
    } catch (caught) { setError(failure(caught)); }
    finally { setBusy(false); }
  }
  const disabled = busy || loading;
  function pages(label: string, current: number, count: number, change: (value: number) => void) {
    return <nav aria-label={label} className="flex items-center gap-3">
      <Button variant="secondary" title={`Previous ${label}`} aria-label={`Previous ${label}`}
        disabled={disabled || current === 1} onClick={() => change(current - 1)}><ChevronLeft className="h-4 w-4" /></Button>
      <span className="text-sm">Page {current}</span>
      <Button variant="secondary" title={`Next ${label}`} aria-label={`Next ${label}`}
        disabled={disabled || count < 25} onClick={() => change(current + 1)}><ChevronRight className="h-4 w-4" /></Button>
    </nav>;
  }
  return <section aria-labelledby={`${prefix}-title`} className="min-w-0 space-y-4 border-b pb-6">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id={`${prefix}-title`} className="text-lg font-semibold">Sourcing automation</h2>
      <Button variant="secondary" disabled={disabled} onClick={() => void reload()}>
        <RefreshCw className="h-4 w-4" />Reload automation</Button>
    </header>
    {loading && <p role="status">Loading automation...</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <p className="text-sm">{rule?.state === "configured" ? `Rule revision ${rule.revision}` : rule ? "Unconfigured" : "Unavailable"}</p>
    <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={enabled} disabled={disabled || !rule} onChange={(event) => setEnabled(event.target.checked)} />
        Automatic sourcing refresh
      </label>
      <div className="space-y-1">
        <label htmlFor={`${prefix}-reason`}>Automation change reason</label>
        <textarea id={`${prefix}-reason`} className="block w-full rounded-md border bg-background p-2" rows={2}
          maxLength={2000} required disabled={disabled || !rule} value={reason} onChange={(event) => setReason(event.target.value)} />
      </div>
      <Button type="submit" disabled={disabled || !rule || !reason.trim()}><Save className="h-4 w-4" />Save automation</Button>
    </form>
    <div className="space-y-3">
      <h3 className="text-base font-semibold">Refresh jobs</h3>
      <p className="break-words text-sm">Last success: {jobs?.last_success_at ?? "None"}</p>
      {jobs && !jobs.items.length && <p>No refresh jobs</p>}
      <div className="max-w-full overflow-x-auto">
        <table className="w-full min-w-[700px] text-left text-sm">
          <thead><tr className="border-b">{["Source", "State", "Attempts", "Next attempt", "Result"].map((name) =>
            <th key={name} scope="col" className="p-2 font-medium">{name}</th>)}</tr></thead>
          <tbody>{jobs?.items.map((job) => <tr key={job.id} className="border-b align-top">
            <td className="max-w-56 break-all p-2"><a href={`/people/demand#demand-${encodeURIComponent(job.source_id)}`} className="underline">{job.source_id}</a>
              <div className="text-xs text-muted-foreground">{job.created_at}</div></td>
            <td className="p-2 capitalize">{job.status}</td><td className="p-2 tabular-nums">{job.attempts}</td>
            <td className="p-2">{job.next_attempt_at ?? "None"}</td>
            <td className="max-w-80 space-y-2 break-words p-2">
              {job.last_error && <p>{job.last_error}</p>}{job.completed_at && <p>{job.completed_at}</p>}
              {job.can_retry && <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void retry(job); }}>
                <label className="sr-only" htmlFor={`${prefix}-retry-${job.id}`}>Retry reason {job.id}</label>
                <textarea id={`${prefix}-retry-${job.id}`} rows={2} required maxLength={2000} disabled={disabled}
                  className="block w-full rounded-md border bg-background p-2" value={retryReasons[job.id] ?? ""}
                  onChange={(event) => setRetryReasons((current) => ({ ...current, [job.id]: event.target.value }))} />
                <Button type="submit" variant="secondary" aria-label={`Retry ${job.id}`}
                  disabled={disabled || !retryReasons[job.id]?.trim()}><RotateCcw className="h-4 w-4" />Retry</Button>
              </form>}
            </td>
          </tr>)}</tbody>
        </table>
      </div>
      {pages("job pages", page, jobs?.items.length ?? 0, setPage)}
    </div>
    <details className="space-y-3">
      <summary className="cursor-pointer font-medium">Rule history</summary>
      {history.map((item) => <div key={item.id} className="space-y-1 border-b py-2 text-sm">
        <p>Revision {item.revision}: {item.enabled ? "Enabled" : "Disabled"}</p>
        <p className="break-words">{item.reason}</p><p className="break-all text-muted-foreground">{item.created_at} / {item.created_by}</p>
      </div>)}
      {!history.length && <p>No rule revisions</p>}
      {pages("rule history pages", historyPage, history.length, setHistoryPage)}
    </details>
  </section>;
}
