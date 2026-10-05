import { useEffect, useId, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import { ApiError, getMe } from "../api/client";
import type { DemandLine, DemandSource } from "../api/people-demand";
import {
  getCoverage,
  getCoverageSources,
  saveCoverage,
  type CoverageMapping,
  type CoverageVersion,
} from "../api/people-coverage";
import { Button } from "../ui-v2/primitives/button";
import { Input } from "../ui-v2/primitives/input";

type Row = {
  key: string;
  planLine: string;
  projectLine: string;
  planStart: string;
  projectStart: string;
  count: string;
  start: string;
  end: string;
};
function fromMappings(mappings: CoverageMapping[]): Row[] {
  const rows: Row[] = [];
  for (const mapping of mappings) {
    let offset = 0;
    while (offset < mapping.plan_slots.length) {
      let count = 1;
      while (
        offset + count < mapping.plan_slots.length &&
        mapping.plan_slots[offset + count] ===
          mapping.plan_slots[offset] + count &&
        mapping.project_slots[offset + count] ===
          mapping.project_slots[offset] + count
      )
        count++;
      rows.push({
        key: crypto.randomUUID(),
        planLine: mapping.plan_line_key,
        projectLine: mapping.project_line_key,
        planStart: String(mapping.plan_slots[offset] + 1),
        projectStart: String(mapping.project_slots[offset] + 1),
        count: String(count),
        start: mapping.start_date,
        end: mapping.end_date,
      });
      offset += count;
    }
  }
  return rows;
}
const lineName = (line: DemandLine) =>
  `${line.role || "Unknown role"} / ${line.location || "Location unknown"} / ${line.level || "Level unknown"} (${line.quantity ?? "Unknown"} people)`;
function matching(left: DemandLine, right: DemandLine) {
  return (
    ["role", "level", "location", "timezone", "allocation"].every(
      (key) => left[key as keyof DemandLine] === right[key as keyof DemandLine],
    ) &&
    JSON.stringify([...left.skills].sort()) ===
      JSON.stringify([...right.skills].sort())
  );
}
function bounds(left?: DemandLine, right?: DemandLine) {
  const start =
    left?.start_date && right?.start_date
      ? [left.start_date, right.start_date].sort()[1]
      : "";
  const end =
    left?.end_date && right?.end_date
      ? [left.end_date, right.end_date].sort()[0]
      : "";
  return start && end && start > end ? { start: "", end: "" } : { start, end };
}
function failure(error: unknown) {
  if (error instanceof ApiError) {
    const detail = (error.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail
        .map(
          (item: { loc?: unknown[]; msg?: string }) =>
            `${item.loc?.join(".") ?? "Coverage"}: ${item.msg ?? "Invalid mapping"}`,
        )
        .join("\n");
  }
  return error instanceof Error ? error.message : "Coverage request failed";
}

export function CoverageEditor({
  plan,
  available,
  onSaved,
}: {
  plan: DemandSource;
  available: DemandSource[];
  onSaved: () => void | Promise<void>;
}) {
  const prefix = useId();
  const [allowed, setAllowed] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [basisPlan, setBasisPlan] = useState<DemandSource | null>(plan);
  const [basisSources, setBasisSources] = useState(available);
  const [current, setCurrent] = useState<CoverageVersion[]>([]);
  const [selected, setSelected] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<CoverageVersion[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historySelection, setHistorySelection] = useState("");
  const generation = useRef(0);
  const request = useRef({ body: "", key: "" });
  const projects = basisSources.filter(
    (source) =>
      source.source_kind === "project" &&
      source.account_id === basisPlan?.account_id &&
      source.publication_id,
  );
  const project = projects.find((source) => source.publication_id === selected);
  const mapping = current.find(
    (item) => item.project_publication_id === selected,
  );
  const sourceVersionKey = (source: DemandSource) =>
    JSON.stringify([
      source.source_kind,
      source.source_id,
      source.plan_id,
      source.project_id,
      source.publication_id,
      source.publication_version_id,
      source.source_version_id,
      source.state,
    ]);
  const propsVersion = JSON.stringify([
    sourceVersionKey(plan),
    available.map(sourceVersionKey).sort(),
  ]);
  useEffect(() => {
    setBasisPlan(plan);
    setBasisSources(available);
  }, [propsVersion]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setSelected("");
    setRows([]);
    setReason("");
    setError("");
    setNotice("");
    getMe()
      .then(async (me) => {
        if (!active) return;
        if (
          !me.groups.some((role) =>
            [
              "HR",
              "Delivery",
              "Finance",
              "CEO",
              "SystemAdmin",
              "Sales",
              "SalesLeader",
            ].includes(role),
          )
        ) {
          setLoadError("Demand planning permission required");
          setLoading(false);
          return;
        }
        setAllowed(true);
        setCanWrite(
          me.groups.some((role) => ["Delivery", "SystemAdmin"].includes(role)),
        );
        await reload(false);
      })
      .catch((caught) => {
        if (active) {
          setLoadError(failure(caught));
          setLoading(false);
        }
      });
    return () => {
      active = false;
      generation.current++;
    };
  }, [plan.publication_id]);
  useEffect(() => {
    setRows(
      fromMappings(
        current.find((item) => item.project_publication_id === selected)
          ?.mappings ?? [],
      ),
    );
    setReason("");
    setError("");
    setHistoryPage(1);
  }, [selected]);
  useEffect(() => {
    let active = true;
    setHistory([]);
    setHistorySelection("");
    setHistoryError("");
    if (!mapping || !basisPlan?.publication_id || !allowed) {
      setHistoryLoading(false);
      return;
    }
    setHistoryLoading(true);
    getCoverage(basisPlan.publication_id, mapping.id, historyPage)
      .then((next) => {
        if (active) {
          setHistory(next.items);
          setHistorySelection(next.items[0]?.version_id ?? "");
        }
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
  }, [
    mapping?.id,
    mapping?.version_id,
    basisPlan?.publication_id,
    historyPage,
    allowed,
  ]);
  async function reload(refreshSources: boolean) {
    const token = ++generation.current;
    setLoading(true);
    try {
      const allSources = refreshSources
        ? (await getCoverageSources()).items
        : available;
      const nextPlan = refreshSources
        ? (allSources.find(
            (source) =>
              source.publication_id === plan.publication_id &&
              source.source_kind !== "project",
          ) ?? null)
        : plan;
      if (!nextPlan?.publication_id)
        throw new Error("Plan publication unavailable");
      const versions: CoverageVersion[] = [];
      for (let page = 1; ; page++) {
        const result = await getCoverage(
          nextPlan.publication_id,
          undefined,
          page,
        );
        if (token !== generation.current) return;
        versions.push(...result.items);
        if (result.items.length < 50) break;
      }
      setBasisPlan(nextPlan);
      setBasisSources(allSources);
      setCurrent(versions);
      setLoadError("");
      const options = allSources.filter(
        (source) =>
          source.source_kind === "project" &&
          source.account_id === nextPlan.account_id &&
          source.publication_id,
      );
      setSelected((previous) =>
        options.some((source) => source.publication_id === previous) ||
        versions.some((item) => item.project_publication_id === previous)
          ? previous
          : (options[0]?.publication_id ?? versions[0]?.project_publication_id ?? ""),
      );
    } catch (caught) {
      if (token === generation.current) setLoadError(failure(caught));
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  function addRow() {
    const left = basisPlan?.lines[0];
    const right = left
      ? project?.lines.find((line) => matching(left, line))
      : undefined;
    setRows((currentRows) => [
      ...currentRows,
      {
        key: crypto.randomUUID(),
        planLine: left?.line_key ?? "",
        projectLine: right?.line_key ?? "",
        planStart: "1",
        projectStart: "1",
        count: "",
        ...bounds(left, right),
      },
    ]);
  }
  function change(row: Row, field: keyof Row, value: string) {
    const updated = { ...row, [field]: value };
    if (field === "planLine" || field === "projectLine")
      Object.assign(
        updated,
        bounds(
          basisPlan?.lines.find((line) => line.line_key === updated.planLine),
          project?.lines.find((line) => line.line_key === updated.projectLine),
        ),
      );
    setRows((currentRows) =>
      currentRows.map((item) => (item.key === row.key ? updated : item)),
    );
  }
  async function save(clear = false) {
    const projectPublication = clear ? mapping?.project_publication_id : project?.publication_id;
    const projectVersion = clear ? mapping?.project_version_id : project?.publication_version_id;
    const planVersion = clear ? mapping?.plan_version_id : basisPlan?.publication_version_id;
    if (
      !basisPlan?.publication_id ||
      !planVersion || !projectPublication || !projectVersion
    )
      return;
    setError("");
    setNotice("");
    const mappings: CoverageMapping[] = [];
    if (!clear)
      for (const row of rows) {
        const numbers = [row.planStart, row.projectStart, row.count].map(
          Number,
        );
        const [planStart, projectStart, count] = numbers;
        if (
          numbers.some(
            (value) =>
              !Number.isSafeInteger(value) || value < 1 || value > 10000,
          ) ||
          !row.planLine ||
          !row.projectLine ||
          !row.start ||
          !row.end ||
          row.start > row.end
        ) {
          setError(
            "Each mapping requires explicit lines, positive integer slots/count and inclusive dates",
          );
          return;
        }
        mappings.push({
          plan_line_key: row.planLine,
          project_line_key: row.projectLine,
          plan_slots: Array.from(
            { length: count },
            (_, index) => planStart - 1 + index,
          ),
          project_slots: Array.from(
            { length: count },
            (_, index) => projectStart - 1 + index,
          ),
          start_date: row.start,
          end_date: row.end,
        });
      }
    const body = {
      plan_publication_id: basisPlan.publication_id,
      project_publication_id: projectPublication,
      expected_plan_version_id: planVersion,
      expected_project_version_id: projectVersion,
      expected_mapping_version_id: mapping?.version_id ?? null,
      reason: reason.trim(),
      mappings,
    };
    const serialized = JSON.stringify(body);
    if (request.current.body !== serialized)
      request.current = { body: serialized, key: crypto.randomUUID() };
    setBusy(true);
    try {
      const saved = await saveCoverage({
        ...body,
        request_key: request.current.key,
      });
      setCurrent((versions) => [
        ...versions.filter(
          (item) =>
            item.project_publication_id !== saved.project_publication_id,
        ),
        saved,
      ]);
      setRows(fromMappings(saved.mappings));
      setHistoryPage(1);
      setReason("");
      setNotice(`Coverage revision ${saved.revision} saved`);
      await onSaved();
    } catch (caught) {
      setError(failure(caught));
    } finally {
      setBusy(false);
    }
  }
  const enabled =
    canWrite &&
    !busy &&
    !loading &&
    !loadError &&
    basisPlan?.state === "current" &&
    project?.state === "current" &&
    !!basisPlan.publication_id &&
    !!basisPlan.publication_version_id &&
    !!project.publication_id &&
    !!project.publication_version_id;
  const viewed = history.find((item) => item.version_id === historySelection);
  const clearEnabled = canWrite && !busy && !loading && !loadError && !!mapping;
  return (
    <section
      aria-label="Staffing coverage"
      className="min-w-0 space-y-4 border-t pt-4"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold">Staffing coverage</h3>
        {allowed && (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => void reload(true)}
          >
            <RefreshCw className="h-4 w-4" />
            Reload latest coverage
          </Button>
        )}
      </header>
      {loading && <p role="status">Loading coverage...</p>}
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
      {allowed && (
        <>
          <div className="space-y-1">
            <label htmlFor={`${prefix}-project`}>Replacement project</label>
            <select
              id={`${prefix}-project`}
              value={selected}
              disabled={busy || loading}
              className="block w-full max-w-xl rounded-md border bg-background p-2"
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Select a published project</option>
              {projects.map((item) => (
                <option key={item.publication_id} value={item.publication_id!}>
                  {item.title || "Untitled project"}
                </option>
              ))}
              {current.filter((item) => !projects.some((source) => source.publication_id === item.project_publication_id))
                .map((item) => <option key={item.project_publication_id} value={item.project_publication_id}>
                  Unavailable mapped project ({item.project_publication_id})
                </option>)}
            </select>
          </div>
          {project && (
            <p className="text-sm capitalize">
              {mapping
                ? `Coverage revision ${mapping.revision}: ${mapping.state}`
                : "Unmapped"}{" "}
              · Plan publication: {basisPlan?.state} · Project publication:{" "}
              {project.state}
            </p>
          )}
          {canWrite && project && (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void save();
              }}
            >
              <fieldset disabled={!enabled} className="space-y-3">
                {rows.map((row, index) => (
                  <div
                    key={row.key}
                    className="grid min-w-0 gap-2 border-b pb-3 sm:grid-cols-3"
                  >
                    {(["planLine", "projectLine"] as const).map((field) => {
                      const lines =
                        field === "planLine"
                          ? (basisPlan?.lines ?? [])
                          : project.lines;
                      return (
                        <div key={field} className="min-w-0 space-y-1">
                          <label htmlFor={`${prefix}-${row.key}-${field}`}>
                            {field === "planLine"
                              ? "Plan line"
                              : "Project line"}{" "}
                            {index + 1}
                          </label>
                          <select
                            id={`${prefix}-${row.key}-${field}`}
                            className="block w-full rounded-md border bg-background p-2"
                            required
                            value={row[field]}
                            onChange={(event) =>
                              change(row, field, event.target.value)
                            }
                          >
                            <option value="">Select a source line</option>
                            {row[field] &&
                              !lines.some(
                                (line) => line.line_key === row[field],
                              ) && (
                                <option value={row[field]}>
                                  Unavailable previous line
                                </option>
                              )}
                            {lines.map((line) => (
                              <option key={line.line_key} value={line.line_key}>
                                {lineName(line)}
                              </option>
                            ))}
                          </select>
                        </div>
                      );
                    })}
                    {(["planStart", "projectStart", "count"] as const).map(
                      (field) => (
                        <div key={field} className="space-y-1">
                          <label htmlFor={`${prefix}-${row.key}-${field}`}>
                            {field === "planStart"
                              ? "Plan first slot"
                              : field === "projectStart"
                                ? "Project first slot"
                                : "Slot count"}{" "}
                            {index + 1}
                          </label>
                          <Input
                            id={`${prefix}-${row.key}-${field}`}
                            type="number"
                            min={1}
                            max={10000}
                            step={1}
                            required
                            value={row[field]}
                            onChange={(event) =>
                              change(row, field, event.target.value)
                            }
                          />
                        </div>
                      ),
                    )}
                    {(["start", "end"] as const).map((field) => (
                      <div key={field} className="space-y-1">
                        <label htmlFor={`${prefix}-${row.key}-${field}`}>
                          {field === "start" ? "Start date" : "End date"}{" "}
                          {index + 1}
                        </label>
                        <Input
                          id={`${prefix}-${row.key}-${field}`}
                          type="date"
                          required
                          value={row[field]}
                          onChange={(event) =>
                            change(row, field, event.target.value)
                          }
                        />
                      </div>
                    ))}
                    <button
                      type="button"
                      className="flex h-9 w-9 items-center justify-center self-end rounded-md hover:bg-muted"
                      title={`Remove mapping ${index + 1}`}
                      aria-label={`Remove mapping ${index + 1}`}
                      onClick={() =>
                        setRows((currentRows) =>
                          currentRows.filter((item) => item.key !== row.key),
                        )
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
                <Button type="button" variant="secondary" onClick={addRow}>
                  <Plus className="h-4 w-4" />
                  Add mapping
                </Button>
              </fieldset>
                <div className="space-y-1">
                  <label htmlFor={`${prefix}-reason`}>Coverage reason</label>
                  <textarea
                    id={`${prefix}-reason`}
                    rows={2}
                    required
                    maxLength={2000}
                    disabled={!enabled && !clearEnabled}
                    className="block w-full rounded-md border bg-background p-2"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  disabled={!enabled || !reason.trim() || rows.length === 0}
                >
                  <Save className="h-4 w-4" />
                  Save coverage
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={!clearEnabled || !reason.trim()}
                  onClick={() => void save(true)}
                >
                  <Trash2 className="h-4 w-4" />
                  Clear coverage
                </Button>
              </div>
            </form>
          )}
          {canWrite && !project && mapping && <div className="space-y-3">
            <p className="text-sm">Coverage revision {mapping.revision}: {mapping.state}</p>
            <div className="space-y-1">
              <label htmlFor={`${prefix}-reason`}>Coverage reason</label>
              <textarea id={`${prefix}-reason`} rows={2} required maxLength={2000}
                disabled={!clearEnabled} className="block w-full rounded-md border bg-background p-2"
                value={reason} onChange={(event) => setReason(event.target.value)} />
            </div>
            <Button type="button" variant="secondary" disabled={!clearEnabled || !reason.trim()}
              onClick={() => void save(true)}><Trash2 className="h-4 w-4" />Clear coverage</Button>
          </div>}
          {historyLoading && <p role="status">Loading coverage history...</p>}
          {historyError && (
            <p role="alert" className="text-destructive">
              {historyError}
            </p>
          )}
          {mapping && !historyLoading && !historyError && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label htmlFor={`${prefix}-history`}>
                  Coverage history revision
                </label>
                <select
                  id={`${prefix}-history`}
                  value={historySelection}
                  className="block w-full max-w-xl rounded-md border bg-background p-2"
                  onChange={(event) => setHistorySelection(event.target.value)}
                >
                  {history.map((item) => (
                    <option key={item.version_id} value={item.version_id}>
                      Revision {item.revision} - {item.created_at}
                    </option>
                  ))}
                </select>
              </div>
              <nav
                aria-label="Coverage history pages"
                className="flex items-center gap-3"
              >
                <Button
                  variant="secondary"
                  title="Previous coverage page"
                  aria-label="Previous coverage page"
                  disabled={historyPage === 1 || busy}
                  onClick={() => setHistoryPage((page) => page - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span>History page {historyPage}</span>
                <Button
                  variant="secondary"
                  title="Next coverage page"
                  aria-label="Next coverage page"
                  disabled={history.length < 50 || busy}
                  onClick={() => setHistoryPage((page) => page + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </nav>
              {viewed && (
                <>
                  <p className="text-sm">{viewed.reason}</p>
                  {viewed.mappings.length === 0 ? (
                    <p className="text-sm">Coverage cleared</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[620px] text-left text-sm">
                        <thead>
                          <tr className="border-b">
                            {[
                              "Plan line",
                              "Project line",
                              "Plan slots",
                              "Project slots",
                              "Dates",
                            ].map((heading) => (
                              <th scope="col" key={heading} className="p-2">
                                {heading}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {viewed.mappings.map((item, index) => (
                            <tr key={index} className="border-b">
                              <td className="p-2">
                                {basisPlan?.lines.find(
                                  (line) =>
                                    line.line_key === item.plan_line_key,
                                )?.role || "Unavailable previous line"}
                              </td>
                              <td className="p-2">
                                {project?.lines.find(
                                  (line) =>
                                    line.line_key === item.project_line_key,
                                )?.role || "Unavailable previous line"}
                              </td>
                              <td className="max-w-40 break-words p-2">
                                {item.plan_slots
                                  .map((slot) => slot + 1)
                                  .join(", ")}
                              </td>
                              <td className="max-w-40 break-words p-2">
                                {item.project_slots
                                  .map((slot) => slot + 1)
                                  .join(", ")}
                              </td>
                              <td className="p-2">
                                {item.start_date} to {item.end_date}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
