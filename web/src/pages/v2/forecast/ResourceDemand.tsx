import { useEffect, useId, useRef, useState } from "react";
import { GitMerge, RefreshCw, Send, X } from "lucide-react";
import { CoverageEditor } from "../../../components/CoverageEditor";
import { ApiError, getMe } from "../../../api/client";
import {
  getDemandSources,
  demandSourceId,
  publishDemand,
  type DemandLine,
  type DemandSource,
  type DemandSources,
  type DemandEnrichment,
} from "../../../api/people-demand";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { formatPercent } from "../sow-workspace/format";

const readRoles = [
  "HR",
  "Delivery",
  "Finance",
  "CEO",
  "SystemAdmin",
  "Sales",
  "SalesLeader",
];
type Draft = { skills: string; level: string; evidence: string };
const draftFor = (line: DemandLine): Draft => ({
  skills: line.skills.join("\n"),
  level: line.level,
  evidence: line.evidence.join("\n"),
});
const entries = (value: string) =>
  value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
const label = (value: string) => value.replaceAll("_", " ");
function missingLabels(values: string[]): string {
  return [
    ...new Set(values.map((value) => label(value.split(":").at(-1) ?? value))),
  ].join(", ");
}
function failure(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail
        .map(
          (item: { loc?: unknown[]; msg?: string }) =>
            `${item.loc?.join(".") ?? "Publication"}: ${item.msg ?? "Invalid value"}`,
        )
        .join("\n");
  }
  return error instanceof Error ? error.message : "Demand request failed";
}
function dated(line: DemandLine): boolean {
  const valid = (value: string | null) => {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const timestamp = Date.parse(`${value}T00:00:00Z`);
    return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
  };
  return valid(line.start_date) && valid(line.end_date) && line.start_date! <= line.end_date!;
}

export function ResourceDemand({
  accountId,
  forecastSearch,
  period,
  onRefresh,
}: {
  accountId?: string;
  forecastSearch?: string;
  period?: { start: string; end_exclusive: string };
  onRefresh?: () => void;
}) {
  const prefix = useId();
  const [allowed, setAllowed] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [data, setData] = useState<DemandSources | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [coverageSource, setCoverageSource] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const draftBasis = useRef<Record<string, Draft>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const revealedAnchor = useRef("");
  const request = useRef({ body: "", key: "" });
  function sourceHref(href: string) {
    if (!forecastSearch || !href.startsWith("/forecast?")) return href;
    const target = new URL(href, window.location.origin);
    const context = new URLSearchParams(forecastSearch);
    for (const key of ["scenario", "future_quarters", "as_of", "month"]) {
      const value = context.get(key);
      if (value) target.searchParams.set(key, value);
    }
    return `${target.pathname}${target.search}${target.hash}`;
  }
  useEffect(() => {
    let active = true;
    getMe()
      .then(async (me) => {
        if (!active) return;
        if (!me.groups.some((role) => readRoles.includes(role))) {
          setLoadError("Demand planning permission required");
          setLoading(false);
          return;
        }
        setAllowed(true);
        setCanWrite(
          me.groups.some((role) => ["Delivery", "SystemAdmin"].includes(role)),
        );
        await reload();
      })
      .catch((caught) => {
        if (active) {
          setLoadError(failure(caught));
          setLoading(false);
        }
      });
    return () => {
      active = false;
      generation.current += 1;
    };
  }, []);
  useEffect(() => {
    setEditing(null);
    setCoverageSource(null);
    setError("");
    setNotice("");
  }, [accountId, period?.start, period?.end_exclusive]);
  useEffect(() => {
    const anchor = window.location.hash.slice(1);
    if (loading || loadError || !data || !anchor || revealedAnchor.current === anchor) return;
    if (!data.items.some((source) => `demand-${demandSourceId(source)}` === anchor)) return;
    const target = document.getElementById(anchor);
    if (target) {
      target.scrollIntoView({ block: "start" });
      revealedAnchor.current = anchor;
    }
  }, [data, loading, loadError]);
  async function reload() {
    const token = ++generation.current;
    setLoading(true);
    try {
      const next = await getDemandSources();
      if (token !== generation.current) return;
      setData(next);
      setLoadError("");
      request.current = { body: "", key: "" };
    } catch (caught) {
      if (token === generation.current) setLoadError(failure(caught));
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  function edit(source: DemandSource) {
    setEditing(demandSourceId(source));
    draftBasis.current = Object.fromEntries(
      source.lines.map((line) => [line.line_key, draftFor(line)]),
    );
    setDrafts(draftBasis.current);
    setReason("");
    setError("");
    setNotice("");
    request.current = { body: "", key: "" };
  }
  function change(line: DemandLine, field: keyof Draft, value: string) {
    setDrafts((current) => ({
      ...current,
      [line.line_key]: {
        ...(current[line.line_key] ?? draftFor(line)),
        [field]: value,
      },
    }));
  }
  async function publish(source: DemandSource) {
    setError("");
    const enrichments: Record<string, DemandEnrichment> = {};
    for (const line of source.lines) {
      const draft = drafts[line.line_key];
      const basis = draftBasis.current[line.line_key] ?? draftFor(line);
      if (!draft || JSON.stringify(draft) === JSON.stringify(basis)) continue;
      const evidence = entries(draft.evidence);
      if (!evidence.length) {
        setError(`Evidence is required for ${line.role || "this assignment"}`);
        return;
      }
      enrichments[line.line_key] = {
        ...(draft.skills !== basis.skills
          ? { skills: entries(draft.skills) }
          : {}),
        ...(draft.level !== basis.level ? { level: draft.level.trim() } : {}),
        evidence,
      };
    }
    const body = {
      ...(source.project_id ? { project_id: source.project_id } : { plan_id: source.plan_id }),
      expected_source_version_id: source.source_version_id,
      expected_publication_version_id: source.publication_version_id,
      reason: reason.trim(),
      enrichments,
    };
    const serialized = JSON.stringify(body);
    if (request.current.body !== serialized)
      request.current = { body: serialized, key: crypto.randomUUID() };
    setBusy(true);
    try {
      const published = await publishDemand({
        ...body,
        request_key: request.current.key,
      });
      setNotice(
        `Demand revision ${published.revision} published${published.missing.length ? `; missing: ${missingLabels(published.missing)}` : ""}`,
      );
      setEditing(null);
      await reload();
      onRefresh?.();
    } catch (caught) {
      setError(failure(caught));
    } finally {
      setBusy(false);
    }
  }
  function displayedLines(source: DemandSource) {
    return source.lines.filter((line) => !period || !dated(line) ||
      (line.start_date! < period.end_exclusive && line.end_date! >= period.start));
  }
  const visible =
    data?.items.filter(
      (source) => (!accountId || source.account_id === accountId) &&
        (!period || source.state !== "current" || source.lines.length === 0 || displayedLines(source).length > 0),
    ) ?? [];
  return (
    <section aria-label="Resource demand" className="min-w-0 space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Resource demand</h2>
          <p className="text-sm text-muted-foreground">
            {accountId ? "Selected account demand" : data?.scope_label ?? "Demand sources"}
          </p>
          {period && <p className="text-sm text-muted-foreground">
            {period.start} to {period.end_exclusive} (exclusive)
          </p>}
        </div>
        {allowed && (
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => void reload()}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Reload sources
          </Button>
        )}
      </header>
      {loading && <p role="status">Loading demand sources...</p>}
      {loadError && (
        <p
          role="alert"
          className="whitespace-pre-wrap text-sm text-destructive"
        >
          {loadError}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="whitespace-pre-wrap text-sm text-destructive"
        >
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      {!loading && !loadError && data && visible.length === 0 && (
        <p className="text-sm text-muted-foreground">No demand sources</p>
      )}
      {visible.map((source) => (
        <section
          key={demandSourceId(source)}
          id={`demand-${demandSourceId(source)}`}
          className="min-w-0 space-y-3 border-b pb-5"
          aria-label={source.title}
        >
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="text-xs text-muted-foreground">
                {source.account_name || "Account unavailable"}
              </p>
              <h3 className="break-words text-base font-semibold">
                {source.source_url ? (
                  <a
                    className="underline underline-offset-2"
                    href={sourceHref(source.source_url)}
                  >
                    {source.title || "Untitled source"}
                  </a>
                ) : (
                  source.title || "Untitled source"
                )}
              </h3>
              <p className="text-sm capitalize">
                {source.state} · Source revision {source.source_revision} ·{" "}
                {label(source.lifecycle)}
                {!source.selected ? " · Not selected" : ""}
              </p>
              <p className="text-sm text-muted-foreground">
                Win probability:{" "}
                {formatPercent(source.probability) ?? "Unknown"}
              </p>
              {source.missing.length > 0 && (
                <p className="text-sm text-amber-700">
                  Missing: {missingLabels(source.missing)}
                </p>
              )}
            </div>
            {canWrite && editing !== demandSourceId(source) && (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy || loading || !!loadError}
                onClick={() => edit(source)}
              >
                <Send className="mr-2 h-4 w-4" />
                {source.state === "current"
                  ? "Revise demand"
                  : "Publish demand"}
              </Button>
            )}
          </header>
          {source.lines.some((line) => !dated(line)) && (
            <p className="text-sm text-amber-700">Service period unresolved</p>
          )}
          {source.lines.length > 0 && displayedLines(source).length === 0 && (
            <p className="text-sm text-muted-foreground">Published assignments outside selected period</p>
          )}
          {displayedLines(source).length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    {[
                      "Role / capability",
                      "Location",
                      "People",
                      "Allocation",
                      "Service dates",
                      "Model / evidence",
                    ].map((heading) => (
                      <th
                        key={heading}
                        scope="col"
                        className="px-2 py-2 font-medium"
                      >
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayedLines(source).map((line) => (
                    <tr key={line.line_key} className="border-b align-top">
                      <td className="max-w-60 break-words px-2 py-3">
                        <strong>{line.role || "Unknown role"}</strong>
                        <div>{line.level || "Level unknown"}</div>
                        <div>{line.skills.join(", ") || "Skills unknown"}</div>
                        {line.missing.length > 0 && (
                          <div className="text-amber-700">
                            Missing: {missingLabels(line.missing)}
                          </div>
                        )}
                      </td>
                      <td className="px-2 py-3">
                        {line.location || "Unknown"}
                        <div className="text-xs text-muted-foreground">
                          {line.timezone || "Timezone unknown"}
                        </div>
                      </td>
                      <td className="px-2 py-3 tabular-nums">
                        {line.quantity ?? "Unknown"}
                      </td>
                      <td className="px-2 py-3 tabular-nums">
                        {line.allocation ?? "Unknown"}
                      </td>
                      <td className="px-2 py-3">
                        {line.start_date ?? "Unknown"} to{" "}
                        {line.end_date ?? "Unknown"}
                      </td>
                      <td className="max-w-64 break-words px-2 py-3">
                        <span className="capitalize">
                          {label(line.delivery_model)}
                        </span>
                        {line.evidence.map((item, index) => (
                          <div
                            key={index}
                            className="text-xs text-muted-foreground"
                          >
                            {item}
                          </div>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {source.lines.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {source.state === "current"
                ? "No confirmed staffing assignments"
                : "Latest source demand is not published"}
            </p>
          )}
          {source.plan_id && source.publication_id && (
            <Button variant="secondary" size="sm"
              aria-expanded={coverageSource === demandSourceId(source)}
              onClick={() => setCoverageSource((current) => current === demandSourceId(source) ? null : demandSourceId(source))}>
              <GitMerge className="mr-2 h-4 w-4" />
              Staffing coverage
            </Button>
          )}
          {coverageSource === demandSourceId(source) && source.plan_id && data && (
            <CoverageEditor plan={source} available={data.items} onSaved={async () => {
              await reload();
              onRefresh?.();
            }} />
          )}
          {canWrite && editing === demandSourceId(source) && (
            <form
              className="space-y-4 border-t pt-4"
              onSubmit={(event) => {
                event.preventDefault();
                void publish(source);
              }}
            >
              {source.lines.map((line, index) => {
                const draft = drafts[line.line_key] ?? draftFor(line);
                const id = `${prefix}-${index}`;
                return (
                  <fieldset
                    key={line.line_key}
                    disabled={busy}
                    className="grid min-w-0 gap-3 sm:grid-cols-3"
                  >
                    <legend className="mb-2 text-sm font-medium">
                      {line.role || "Assignment"} ·{" "}
                      {line.location || "Location unknown"}
                    </legend>
                    <div className="space-y-1 text-sm">
                      <label htmlFor={`${id}-skills`}>
                        Skills for {line.role}
                      </label>
                      <textarea
                        id={`${id}-skills`}
                        rows={3}
                        className="block w-full rounded-md border bg-background p-2"
                        value={draft.skills}
                        onChange={(event) =>
                          change(line, "skills", event.target.value)
                        }
                      />
                    </div>
                    <div className="space-y-1 text-sm">
                      <label htmlFor={`${id}-level`}>
                        Level for {line.role}
                      </label>
                      <Input
                        id={`${id}-level`}
                        value={draft.level}
                        onChange={(event) =>
                          change(line, "level", event.target.value)
                        }
                      />
                    </div>
                    <div className="space-y-1 text-sm">
                      <label htmlFor={`${id}-evidence`}>
                        Evidence for {line.role}
                      </label>
                      <textarea
                        id={`${id}-evidence`}
                        rows={3}
                        className="block w-full rounded-md border bg-background p-2"
                        value={draft.evidence}
                        onChange={(event) =>
                          change(line, "evidence", event.target.value)
                        }
                      />
                    </div>
                  </fieldset>
                );
              })}
              <div className="block space-y-1 text-sm">
                <label htmlFor={`${prefix}-reason`}>Publication reason</label>
                <textarea
                  id={`${prefix}-reason`}
                  required
                  maxLength={2000}
                  rows={2}
                  disabled={busy}
                  className="block w-full rounded-md border bg-background p-2"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  disabled={busy || loading || !!loadError || !reason.trim()}
                >
                  <Send className="mr-2 h-4 w-4" />
                  {busy ? "Publishing..." : "Publish latest source"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => setEditing(null)}
                >
                  <X className="mr-2 h-4 w-4" />
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </section>
      ))}
    </section>
  );
}
