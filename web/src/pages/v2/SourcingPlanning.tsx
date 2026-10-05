import { useEffect, useId, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Send,
  Trash2,
} from "lucide-react";
import { ApiError, getMe } from "../../api/client";
import { SourcingAutomation } from "../../components/SourcingAutomation";
import { demandSourceId } from "../../api/people-demand";
import {
  getSourcingHistory,
  getSourcingRules,
  getSourcingSources,
  prepareSourcingDraft,
  saveSourcingRules,
  type SourcingHistory,
  type SourcingRules,
  type SourcingSource,
} from "../../api/people-sourcing";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { formatPercent } from "./sow-workspace/format";

type RuleDraft = {
  key: string;
  skill: string;
  location: string;
  lead_days: string;
};
function failure(error: unknown) {
  if (error instanceof ApiError) {
    const detail = (error.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail
        .map(
          (item: { loc?: unknown[]; msg?: string }) =>
            `${item.loc?.join(".") ?? "Sourcing"}: ${item.msg ?? "Invalid value"}`,
        )
        .join("\n");
  }
  return error instanceof Error ? error.message : "Sourcing request failed";
}
const missingText = (missing: string[]) =>
  [
    ...new Set(
      missing.map((value) =>
        (value.split(":").at(-1) ?? value).replaceAll("_", " "),
      ),
    ),
  ].join(", ");

export function SourcingPlanningPage() {
  const prefix = useId();
  const [allowed, setAllowed] = useState(false);
  const [admin, setAdmin] = useState(false);
  const [showAutomation, setShowAutomation] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [rules, setRules] = useState<SourcingRules | null>(null);
  const [draftRules, setDraftRules] = useState<RuleDraft[]>([]);
  const [ruleReason, setRuleReason] = useState("");
  const [sources, setSources] = useState<SourcingSource[]>([]);
  const [selected, setSelected] = useState("");
  const [history, setHistory] = useState<SourcingHistory | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [revision, setRevision] = useState("");
  const [draftReason, setDraftReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const initialized = useRef(false);
  const generation = useRef(0);
  const ruleRequest = useRef({ body: "", key: "" });
  const draftRequest = useRef({ body: "", key: "" });
  const source = sources.find((item) => demandSourceId(item) === selected);
  useEffect(() => {
    let active = true;
    getMe()
      .then(async (me) => {
        if (!active) return;
        if (!me.groups.some((role) => ["HR", "SystemAdmin"].includes(role))) {
          setLoadError("Sourcing requires HR or SystemAdmin");
          setLoading(false);
          return;
        }
        setAllowed(true);
        setAdmin(me.groups.includes("SystemAdmin"));
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
    let active = true;
    setHistory(null);
    setHistoryError("");
    setRevision("");
    if (!source?.publication_id || !allowed) {
      setHistoryLoading(false);
      return;
    }
    setHistoryLoading(true);
    getSourcingHistory(source.publication_id, historyPage)
      .then((next) => {
        if (!active) return;
        setHistory(next);
        setRevision(next.items[0]?.id ?? "");
      })
      .catch((caught) => {
        if (active) setHistoryError(failure(caught));
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [source?.publication_id, allowed, refresh, historyPage]);
  async function reload() {
    const token = ++generation.current;
    setLoading(true);
    try {
      const [nextRules, nextSources] = await Promise.all([
        getSourcingRules(),
        getSourcingSources(),
      ]);
      if (token !== generation.current) return;
      setRules(nextRules);
      setSources(nextSources.items);
      setLoadError("");
      if (!initialized.current) {
        setDraftRules(
          nextRules.rules.map((rule) => ({
            ...rule,
            key: crypto.randomUUID(),
            lead_days: String(rule.lead_days),
          })),
        );
        initialized.current = true;
      }
      setSelected((current) =>
        nextSources.items.some((item) => demandSourceId(item) === current)
          ? current
          : demandSourceId(nextSources.items.find((item) => item.publication_id)),
      );
      setHistoryPage(1);
      setRefresh((value) => value + 1);
    } catch (caught) {
      if (token === generation.current) setLoadError(failure(caught));
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  function requestKey(body: unknown, reference: typeof ruleRequest) {
    const serialized = JSON.stringify(body);
    if (reference.current.body !== serialized)
      reference.current = { body: serialized, key: crypto.randomUUID() };
    return reference.current.key;
  }
  async function saveRules() {
    if (!rules) return;
    setError("");
    setNotice("");
    if (
      draftRules.some(
        (rule) =>
          !rule.skill.trim() ||
          !rule.location.trim() ||
          !/^\d+$/.test(rule.lead_days) ||
          !Number.isSafeInteger(Number(rule.lead_days)),
      )
    ) {
      setError(
        "Each rule requires a skill, location and nonnegative integer lead days",
      );
      return;
    }
    const body = {
      expected_version_id: rules.id,
      reason: ruleReason.trim(),
      rules: draftRules.map(({ skill, location, lead_days }) => ({
        skill: skill.trim(),
        location: location.trim(),
        lead_days: Number(lead_days),
      })),
    };
    setBusy(true);
    try {
      const next = await saveSourcingRules({
        ...body,
        request_key: requestKey(body, ruleRequest),
      });
      setRules(next);
      setRuleReason("");
      setNotice(`Rules revision ${next.revision} saved`);
      setRefresh((value) => value + 1);
    } catch (caught) {
      setError(failure(caught));
    } finally {
      setBusy(false);
    }
  }
  async function prepare() {
    if (
      !source?.publication_id ||
      !source.publication_version_id ||
      !rules?.id ||
      !history ||
      source.state !== "current"
    )
      return;
    const body = {
      publication_id: source.publication_id,
      expected_demand_version_id: source.publication_version_id,
      expected_rule_version_id: rules.id,
      expected_draft_version_id: history.current_version_id,
      reason: draftReason.trim(),
    };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await prepareSourcingDraft({
        ...body,
        request_key: requestKey(body, draftRequest),
      });
      setDraftReason("");
      setHistoryPage(1);
      setNotice(`Sourcing draft revision ${next.revision} prepared`);
      setRefresh((value) => value + 1);
    } catch (caught) {
      setError(failure(caught));
    } finally {
      setBusy(false);
    }
  }
  const snapshot = history?.items.find((item) => item.id === revision);
  const canPrepare =
    !busy &&
    !loading &&
    !loadError &&
    !historyLoading &&
    !historyError &&
    !!history &&
    !!rules?.id &&
    source?.state === "current" &&
    !!source.publication_version_id &&
    !!draftReason.trim();
  return (
    <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Sourcing planning</h1>
        {admin && <Button variant="secondary" aria-expanded={showAutomation}
          onClick={() => setShowAutomation((current) => !current)}>
          <Settings2 className="h-4 w-4" />Automation
        </Button>}
        {allowed && (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => void reload()}
          >
            <RefreshCw className="h-4 w-4" />
            Reload latest
          </Button>
        )}
      </header>
      {loading && <p role="status">Loading sourcing...</p>}
      {loadError && (
        <p role="alert" className="text-destructive">
          {loadError}
        </p>
      )}
      {error && (
        <p role="alert" className="whitespace-pre-wrap text-destructive">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {admin && showAutomation && <SourcingAutomation />}
      {allowed && (
        <>
          <section
            className="space-y-3 border-b pb-6"
            aria-labelledby={`${prefix}-rules`}
          >
            <header className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 id={`${prefix}-rules`} className="text-lg font-semibold">
                  Lead-time rules
                </h2>
                <p className="text-sm text-muted-foreground">
                  {rules?.state === "unconfigured"
                    ? "Unconfigured"
                    : rules
                      ? `Revision ${rules.revision}`
                      : "Unavailable"}
                </p>
              </div>
              <Button
                variant="secondary"
                disabled={busy || loading}
                onClick={() =>
                  setDraftRules((current) => [
                    ...current,
                    {
                      key: crypto.randomUUID(),
                      skill: "",
                      location: "",
                      lead_days: "",
                    },
                  ])
                }
              >
                <Plus className="h-4 w-4" />
                Add rule
              </Button>
            </header>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void saveRules();
              }}
            >
              <fieldset disabled={busy || loading} className="space-y-3">
                {draftRules.map((rule, index) => (
                  <div
                    key={rule.key}
                    className="grid grid-cols-[1fr_1fr_6rem_2rem] items-end gap-2 max-sm:grid-cols-2"
                  >
                    {(["skill", "location", "lead_days"] as const).map(
                      (field) => (
                        <div key={field} className="min-w-0 space-y-1">
                          <label
                            className="text-sm"
                            htmlFor={`${prefix}-${rule.key}-${field}`}
                          >
                            {field === "lead_days"
                              ? "Lead days"
                              : field === "skill"
                                ? "Skill"
                                : "Location"}{" "}
                            {index + 1}
                          </label>
                          <Input
                            id={`${prefix}-${rule.key}-${field}`}
                            type={field === "lead_days" ? "number" : "text"}
                            min={field === "lead_days" ? 0 : undefined}
                            step={field === "lead_days" ? 1 : undefined}
                            required
                            value={rule[field]}
                            onChange={(event) =>
                              setDraftRules((current) =>
                                current.map((item) =>
                                  item.key === rule.key
                                    ? { ...item, [field]: event.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                        </div>
                      ),
                    )}
                    <button
                      type="button"
                      title={`Remove rule ${index + 1}`}
                      aria-label={`Remove rule ${index + 1}`}
                      className="flex h-9 w-8 items-center justify-center rounded-md hover:bg-muted"
                      onClick={() =>
                        setDraftRules((current) =>
                          current.filter((item) => item.key !== rule.key),
                        )
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
                <div className="space-y-1">
                  <label htmlFor={`${prefix}-rule-reason`}>
                    Rule change reason
                  </label>
                  <textarea
                    id={`${prefix}-rule-reason`}
                    rows={2}
                    maxLength={2000}
                    required
                    className="block w-full rounded-md border bg-background p-2"
                    value={ruleReason}
                    onChange={(event) => setRuleReason(event.target.value)}
                  />
                </div>
              </fieldset>
              <Button
                type="submit"
                disabled={
                  busy || loading || !!loadError || !rules || !ruleReason.trim()
                }
              >
                <Save className="h-4 w-4" />
                Save rules
              </Button>
            </form>
          </section>
          <section className="space-y-3" aria-labelledby={`${prefix}-drafts`}>
            <h2 id={`${prefix}-drafts`} className="text-lg font-semibold">
              Sourcing drafts
            </h2>
            <div className="space-y-1">
              <label htmlFor={`${prefix}-source`}>Published source</label>
              <select
                id={`${prefix}-source`}
                disabled={busy || loading}
                className="block w-full max-w-xl rounded-md border bg-background p-2"
                value={selected}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setHistoryPage(1);
                  setDraftReason("");
                  setError("");
                  setNotice("");
                }}
              >
                <option value="">Select a published source</option>
                {sources.map((item) => (
                  <option
                    key={demandSourceId(item)}
                    value={demandSourceId(item)}
                    disabled={!item.publication_id}
                  >
                    {item.account_name || "Account unavailable"}:{" "}
                    {item.title || "Untitled source"} ({item.state})
                  </option>
                ))}
              </select>
            </div>
            {source && (
              <p className="text-sm capitalize">
                Demand publication: {source.state}
              </p>
            )}
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void prepare();
              }}
            >
              <div className="space-y-1">
                <label htmlFor={`${prefix}-draft-reason`}>Draft reason</label>
                <textarea
                  id={`${prefix}-draft-reason`}
                  rows={2}
                  maxLength={2000}
                  required
                  disabled={busy}
                  className="block w-full rounded-md border bg-background p-2"
                  value={draftReason}
                  onChange={(event) => setDraftReason(event.target.value)}
                />
              </div>
              <Button type="submit" disabled={!canPrepare}>
                <Send className="h-4 w-4" />
                Prepare sourcing draft
              </Button>
            </form>
            {historyLoading && <p role="status">Loading draft history...</p>}
            {historyError && (
              <p role="alert" className="text-destructive">
                {historyError}
              </p>
            )}
            {history && (
              <p className="text-sm capitalize">Draft state: {history.state}</p>
            )}
            {history && !historyLoading && history.items.length === 0 && (
              <p>No sourcing drafts</p>
            )}
            {history && (
              <nav
                aria-label="Draft history pages"
                className="flex items-center gap-3"
              >
                <Button
                  variant="secondary"
                  title="Previous history page"
                  aria-label="Previous history page"
                  disabled={busy || historyLoading || historyPage === 1}
                  onClick={() => setHistoryPage((page) => page - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm">History page {historyPage}</span>
                <Button
                  variant="secondary"
                  title="Next history page"
                  aria-label="Next history page"
                  disabled={busy || historyLoading || history.items.length < 50}
                  onClick={() => setHistoryPage((page) => page + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </nav>
            )}
            {history && history.items.length > 0 && (
              <div className="space-y-1">
                <label htmlFor={`${prefix}-revision`}>Draft revision</label>
                <select
                  id={`${prefix}-revision`}
                  className="block w-full max-w-xl rounded-md border bg-background p-2"
                  value={revision}
                  onChange={(event) => setRevision(event.target.value)}
                >
                  {history.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      Revision {item.revision} - {item.created_at}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {snapshot && (
              <article className="min-w-0 space-y-3">
                <header>
                  <h3 className="text-base font-semibold">
                    {snapshot.snapshot.source_url ? (
                      <a
                        href={snapshot.snapshot.source_url}
                        className="underline underline-offset-2"
                      >
                        {snapshot.snapshot.title}
                      </a>
                    ) : (
                      snapshot.snapshot.title
                    )}
                  </h3>
                  <p className="text-sm">
                    Win probability:{" "}
                    {formatPercent(snapshot.snapshot.probability) ?? "Unknown"}
                  </p>
                  <p className="text-sm">
                    {snapshot.snapshot.complete
                      ? "Ready for review"
                      : "Incomplete"}
                  </p>
                  <p className="text-sm">{snapshot.reason}</p>
                  <p className="text-sm text-muted-foreground">
                    {snapshot.created_at}
                  </p>
                </header>
                {snapshot.snapshot.missing.length > 0 && (
                  <div className="space-y-2 text-sm">
                    <p className="text-amber-700">Missing: {missingText(snapshot.snapshot.missing)}</p>
                    <div className="flex flex-wrap gap-4">
                      <a href="/people" className="underline underline-offset-2">Review supply</a>
                      <a href={snapshot.snapshot.source_url ?? "/people/demand"} className="underline underline-offset-2">Review source demand</a>
                      <a href={`#${prefix}-rules`} className="underline underline-offset-2">Edit lead-time rules</a>
                    </div>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1100px] text-left text-sm">
                    <thead>
                      <tr className="border-b">
                        {[
                          "Capability",
                          "Dates (end exclusive)",
                          "People",
                          "Retained",
                          "Incremental",
                          "Matched",
                          "Total gap",
                          "Continuity gap",
                          "Incremental gap",
                          "Gap FTE",
                          "Source by",
                        ].map((heading) => (
                          <th
                            key={heading}
                            scope="col"
                            className="p-2 text-xs font-medium"
                          >
                            {heading}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {snapshot.snapshot.rows.map((row) => (
                        <tr
                          key={`${row.id}-${row.start}`}
                          className="border-b align-top"
                        >
                          <td className="max-w-56 break-words p-2">
                            <strong>{row.role || "Unknown role"}</strong>
                            <div>
                              {row.level || "Level unknown"} /{" "}
                              {row.location || "Location unknown"}
                            </div>
                            <div>
                              {row.skills.join(", ") || "Skills unknown"}
                            </div>
                            <div>{row.timezone}</div>
                            {row.missing.length > 0 && (
                              <div className="text-amber-700">
                                Missing: {missingText(row.missing)}
                              </div>
                            )}
                          </td>
                          <td className="p-2">
                            {row.start} to {row.end_exclusive}
                          </td>
                          {[
                            row.quantity,
                            row.retained_quantity,
                            row.incremental_quantity,
                            row.matched_quantity,
                            row.gap_quantity,
                            row.continuity_gap_quantity,
                            row.incremental_gap_quantity,
                            row.gap_fte,
                          ].map((value, index) => (
                            <td key={index} className="p-2 tabular-nums">
                              {value ?? "Unknown"}
                            </td>
                          ))}
                          <td className="p-2">
                            {row.sourcing_by ?? "Not scheduled"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
            )}
          </section>
        </>
      )}
    </main>
  );
}
