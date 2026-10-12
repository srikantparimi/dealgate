/**
 * Allocations grid (S22 P2-1): the prototype's columns, yellow editable
 * cells, cost/hour pre-filled from the rate card (blank = rate card, the
 * placeholder shows the card value), dates pre-filled from the engagement
 * window, row actions Leaves / Re-hire / remove, totals row, Row GM red under
 * the resource floor. Also the CSV importer entry point (P1-6).
 *
 * Every cell edit is a PATCH; the page reloads from the server. A leaver is
 * an End date; a re-hire is a new row; a rate change on a started row
 * supersedes it on the server (new row from today).
 */

import { useMemo, useRef, useState } from "react";
import { Plus, Upload } from "lucide-react";
import {
  EMPLOYMENT_TYPE_LABEL,
  HOURLY_TYPES,
  SENIORITIES,
  addAllocation,
  closeAllocation,
  createResource,
  deleteAllocation,
  importAllocations,
  listResources,
  missingFrom,
  patchAllocation,
  rehireAllocation,
  type Allocation,
  type EmploymentType,
  type Resource,
  type Seniority,
} from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { cn } from "../../../lib/cn";
import type { EngagementData } from "./EngagementPage";
import { hours, money, pct } from "./format";
import {
  CellInput,
  CellSelect,
  Problems,
  calcCell,
  cellInput,
  errorText,
  headCell,
  headCellNum,
  numCell,
  table,
  tableWrap,
  textCell,
  totalsRow,
} from "./shared";

interface DraftRow {
  resource_id: string;
  new_name: string;
  role: string;
  seniority: Seniority;
  location: string;
  employment_type: EmploymentType;
  assignment: string;
  utilization: string;
  bill_rate: string;
  cost_per_hour: string;
  start: string;
  end: string;
  hours_override: string;
}

function emptyDraft(location: string): DraftRow {
  return {
    resource_id: "",
    new_name: "",
    role: "",
    seniority: "Mid",
    location,
    employment_type: "w2_employee",
    assignment: "",
    utilization: "100",
    bill_rate: "",
    cost_per_hour: "",
    start: "",
    end: "",
    hours_override: "",
  };
}

function utilText(value: number): string {
  return String(Math.round(value * 100));
}

export function AllocationsTab({ data, canWrite, onChanged }: { data: EngagementData; canWrite: boolean; onChanged: () => Promise<void> }) {
  const { engagement, allocations, forecast, calendar } = data;
  const hourly = HOURLY_TYPES.has(engagement.type);
  const locations = useMemo(() => {
    const set = new Set<string>(calendar?.locations.map((l) => l.name) ?? []);
    allocations.forEach((a) => set.add(a.location));
    if (set.size === 0) ["US", "India"].forEach((l) => set.add(l));
    return [...set];
  }, [calendar, allocations]);
  const rateCard = (seniority: Seniority | null, location: string, employment: EmploymentType) =>
    calendar?.rate_card.find((c) => c.seniority === seniority && c.location === location && c.employment_type === employment)?.cost_per_hour ?? null;

  const [problems, setProblems] = useState<string[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<DraftRow | null>(null);
  const [resources, setResources] = useState<Resource[] | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function run(action: () => Promise<unknown>, successNotice?: string) {
    setBusy(true);
    setProblems(null);
    setNotice(null);
    try {
      await action();
      await onChanged();
      if (successNotice) setNotice(successNotice);
    } catch (cause) {
      const missing = missingFrom(cause);
      if (missing) setProblems(missing);
      else setNotice(errorText(cause, "The change was not saved."));
    } finally {
      setBusy(false);
    }
  }

  function commit(row: Allocation, patch: Record<string, unknown>) {
    void run(() => patchAllocation(row.id, patch));
  }

  async function openDraft() {
    if (resources === null) {
      try {
        setResources(await listResources());
      } catch {
        setResources([]);
      }
    }
    setDraft(emptyDraft(locations[0] ?? "US"));
  }

  function pickResource(id: string) {
    if (!draft) return;
    const res = resources?.find((r) => r.id === id);
    setDraft({
      ...draft,
      resource_id: id,
      ...(res
        ? { location: res.location, employment_type: res.employment_type, seniority: res.seniority ?? draft.seniority, role: draft.role || res.name }
        : {}),
    });
  }

  async function submitDraft() {
    if (!draft) return;
    await run(async () => {
      let resourceId = draft.resource_id;
      if (!resourceId) {
        if (!draft.new_name.trim()) throw new Error("Pick a person or type a new person's name.");
        const created = await createResource({
          name: draft.new_name.trim(),
          location: draft.location,
          employment_type: draft.employment_type,
          seniority: draft.seniority,
        });
        resourceId = created.id;
        setResources((prev) => (prev ? [...prev, created] : [created]));
      }
      await addAllocation(engagement.id, {
        resource_id: resourceId,
        role: draft.role.trim() || null,
        seniority: draft.seniority,
        location: draft.location,
        employment_type: draft.employment_type,
        assignment: hourly ? draft.assignment.trim() || null : null,
        utilization: draft.utilization.trim() === "" ? 1 : Number(draft.utilization) / 100,
        bill_rate: hourly && draft.bill_rate.trim() !== "" ? draft.bill_rate : null,
        cost_per_hour: draft.cost_per_hour.trim() !== "" ? draft.cost_per_hour : null,
        start: draft.start || null,
        end: draft.end || null,
        hours_override: draft.hours_override.trim() !== "" ? draft.hours_override : null,
      });
      setDraft(null);
    });
  }

  async function onImport(file: File | undefined) {
    if (!file) return;
    await run(() => importAllocations(engagement.id, file), `Imported ${file.name}.`);
    if (fileInput.current) fileInput.current.value = "";
  }

  const staffing = forecast.staffing_totals;
  const sameDates = engagement.same_dates_for_all;
  const colCount = 11 + (hourly ? 4 : 0) + 3; // person, role, seniority, location, employment, [assignment], util, [bill], cost, start, end, hours, override, burden, [revenue], loaded, [row gm], actions

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        {canWrite ? (
          <>
            <Button size="sm" onClick={() => void openDraft()} disabled={busy || draft !== null}>
              <Plus className="mr-1 h-4 w-4" aria-hidden /> Add person
            </Button>
            <Button size="sm" variant="secondary" onClick={() => fileInput.current?.click()} disabled={busy}>
              <Upload className="mr-1 h-4 w-4" aria-hidden /> Import staffing CSV
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              aria-label="Staffing CSV file"
              onChange={(event) => void onImport(event.target.files?.[0])}
            />
          </>
        ) : null}
        <span className="text-secondary text-text-secondary">
          Yellow cells are editable. Leave Start/End blank to use the engagement window
          {sameDates ? " (Same dates for everyone is ON — row dates are ignored)" : ""}. A leaver is an End date; a re-hire is a new row.
        </span>
      </div>
      <Problems problems={problems} />
      {notice ? (
        <p role="status" className="text-secondary text-text-secondary">
          {notice}
        </p>
      ) : null}

      <div className={tableWrap}>
        <table className={table} aria-label="Allocations">
          <thead>
            <tr>
              <th className={headCell}>Person</th>
              <th className={headCell}>Role</th>
              <th className={headCell}>Seniority</th>
              <th className={headCell}>Location</th>
              <th className={headCell}>Employment</th>
              {hourly ? <th className={headCell}>Assignment</th> : null}
              <th className={headCellNum}>Util %</th>
              {hourly ? <th className={headCellNum}>Bill rate</th> : null}
              <th className={headCellNum}>Our cost/hr</th>
              <th className={headCell}>Start</th>
              <th className={headCell}>End</th>
              <th className={headCellNum}>Hours</th>
              <th className={headCellNum}>Hours override</th>
              <th className={headCellNum}>Burden</th>
              {hourly ? <th className={headCellNum}>Revenue</th> : null}
              <th className={headCellNum}>Loaded cost</th>
              {hourly ? <th className={headCellNum}>Row GM</th> : null}
              <th className={headCell} />
            </tr>
          </thead>
          <tbody>
            {draft ? (
              <tr className="bg-primary-subtle" data-testid="draft-row">
                <td className={textCell}>
                  <div className="flex flex-col gap-1">
                    <select
                      aria-label="Person"
                      className={cn(cellInput, "w-40")}
                      value={draft.resource_id}
                      onChange={(e) => pickResource(e.target.value)}
                    >
                      <option value="">+ New person…</option>
                      {(resources ?? []).map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name} · {r.location}
                        </option>
                      ))}
                    </select>
                    {draft.resource_id === "" ? (
                      <input
                        aria-label="New person name"
                        className={cn(cellInput, "w-40")}
                        placeholder="New person's name"
                        value={draft.new_name}
                        onChange={(e) => setDraft({ ...draft, new_name: e.target.value })}
                      />
                    ) : null}
                  </div>
                </td>
                <td className={textCell}>
                  <input aria-label="Role" className={cn(cellInput, "w-32")} placeholder="Role" value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} />
                </td>
                <td className={textCell}>
                  <select aria-label="Seniority" className={cellInput} value={draft.seniority} onChange={(e) => setDraft({ ...draft, seniority: e.target.value as Seniority })}>
                    {SENIORITIES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td className={textCell}>
                  <select aria-label="Location" className={cellInput} value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })}>
                    {locations.map((l) => (
                      <option key={l}>{l}</option>
                    ))}
                  </select>
                </td>
                <td className={textCell}>
                  <select aria-label="Employment type" className={cellInput} value={draft.employment_type} onChange={(e) => setDraft({ ...draft, employment_type: e.target.value as EmploymentType })}>
                    {(Object.keys(EMPLOYMENT_TYPE_LABEL) as EmploymentType[]).map((k) => (
                      <option key={k} value={k}>
                        {EMPLOYMENT_TYPE_LABEL[k]}
                      </option>
                    ))}
                  </select>
                </td>
                {hourly ? (
                  <td className={textCell}>
                    <input aria-label="Assignment" className={cn(cellInput, "w-32")} placeholder="(unassigned)" value={draft.assignment} onChange={(e) => setDraft({ ...draft, assignment: e.target.value })} />
                  </td>
                ) : null}
                <td className={numCell}>
                  <input aria-label="Utilization %" type="number" min={0} max={100} step={5} className={cn(cellInput, "w-20 text-right")} value={draft.utilization} onChange={(e) => setDraft({ ...draft, utilization: e.target.value })} />
                </td>
                {hourly ? (
                  <td className={numCell}>
                    <input aria-label="Bill rate" type="number" min={0} className={cn(cellInput, "w-24 text-right")} value={draft.bill_rate} onChange={(e) => setDraft({ ...draft, bill_rate: e.target.value })} />
                  </td>
                ) : null}
                <td className={numCell}>
                  <input
                    aria-label="Our cost per hour"
                    type="number"
                    min={0}
                    className={cn(cellInput, "w-24 text-right")}
                    placeholder={rateCard(draft.seniority, draft.location, draft.employment_type) ?? ""}
                    title={`Blank = rate card ${rateCard(draft.seniority, draft.location, draft.employment_type) ?? "n/a"}`}
                    value={draft.cost_per_hour}
                    onChange={(e) => setDraft({ ...draft, cost_per_hour: e.target.value })}
                  />
                </td>
                <td className={textCell}>
                  <input aria-label="Start" type="date" className={cn(cellInput, "w-36")} disabled={sameDates} placeholder={engagement.start} value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
                </td>
                <td className={textCell}>
                  <input aria-label="End" type="date" className={cn(cellInput, "w-36")} disabled={sameDates} placeholder={engagement.end} value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} />
                </td>
                <td className={cn(numCell, calcCell)}>—</td>
                <td className={numCell}>
                  <input aria-label="Hours override" type="number" min={0} className={cn(cellInput, "w-24 text-right")} value={draft.hours_override} onChange={(e) => setDraft({ ...draft, hours_override: e.target.value })} />
                </td>
                <td className={cn(numCell, calcCell)}>—</td>
                {hourly ? <td className={cn(numCell, calcCell)}>—</td> : null}
                <td className={cn(numCell, calcCell)}>—</td>
                {hourly ? <td className={cn(numCell, calcCell)}>—</td> : null}
                <td className={textCell}>
                  <div className="flex gap-1">
                    <Button size="sm" onClick={() => void submitDraft()} disabled={busy}>
                      Add
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDraft(null)} disabled={busy}>
                      Cancel
                    </Button>
                  </div>
                </td>
              </tr>
            ) : null}
            {allocations.map((row) => {
              const card = rateCard(row.seniority, row.location, row.employment_type);
              const under = row.totals.under_resource_floor === true;
              return (
                <tr key={row.id} data-testid="allocation-row">
                  <td className={cn(textCell, "font-medium")}>{row.resource_name}</td>
                  <td className={textCell}>
                    <CellInput ariaLabel={`${row.resource_name} role`} value={row.role} onCommit={(v) => commit(row, { role: v })} disabled={!canWrite || busy} className="w-32" />
                  </td>
                  <td className={textCell}>
                    <CellSelect
                      ariaLabel={`${row.resource_name} seniority`}
                      value={row.seniority ?? ""}
                      options={[{ value: "", label: "—" }, ...SENIORITIES.map((s) => ({ value: s, label: s }))]}
                      onCommit={(v) => commit(row, { seniority: v || null })}
                      disabled={!canWrite || busy}
                    />
                  </td>
                  <td className={textCell}>
                    <CellSelect ariaLabel={`${row.resource_name} location`} value={row.location} options={locations.map((l) => ({ value: l, label: l }))} onCommit={(v) => commit(row, { location: v })} disabled={!canWrite || busy} />
                  </td>
                  <td className={textCell}>
                    <CellSelect
                      ariaLabel={`${row.resource_name} employment type`}
                      value={row.employment_type}
                      options={(Object.keys(EMPLOYMENT_TYPE_LABEL) as EmploymentType[]).map((k) => ({ value: k, label: EMPLOYMENT_TYPE_LABEL[k] }))}
                      onCommit={(v) => commit(row, { employment_type: v })}
                      disabled={!canWrite || busy}
                    />
                  </td>
                  {hourly ? (
                    <td className={textCell}>
                      <CellInput ariaLabel={`${row.resource_name} assignment`} value={row.assignment ?? ""} placeholder="(unassigned)" onCommit={(v) => commit(row, { assignment: v || null })} disabled={!canWrite || busy} className="w-32" />
                    </td>
                  ) : null}
                  <td className={numCell}>
                    <CellInput ariaLabel={`${row.resource_name} utilization %`} type="number" min={0} max={100} step={5} value={utilText(row.utilization)} onCommit={(v) => commit(row, { utilization: Number(v) / 100 })} disabled={!canWrite || busy} className="w-20" />
                  </td>
                  {hourly ? (
                    <td className={numCell}>
                      <CellInput ariaLabel={`${row.resource_name} bill rate`} type="number" min={0} value={row.bill_rate ?? ""} onCommit={(v) => commit(row, { bill_rate: v === "" ? null : v })} disabled={!canWrite || busy} />
                    </td>
                  ) : null}
                  <td className={numCell}>
                    {row.cost_per_hour === undefined ? (
                      <span className={calcCell}>restricted</span>
                    ) : (
                      <CellInput
                        ariaLabel={`${row.resource_name} cost per hour`}
                        type="number"
                        min={0}
                        value={row.cost_per_hour ?? ""}
                        placeholder={card ?? ""}
                        title={`Blank = rate card ${card ?? "n/a"}`}
                        onCommit={(v) => commit(row, { cost_per_hour: v === "" ? null : v })}
                        disabled={!canWrite || busy}
                      />
                    )}
                  </td>
                  <td className={textCell}>
                    <CellInput ariaLabel={`${row.resource_name} start`} type="date" value={row.start ?? ""} placeholder={engagement.start} onCommit={(v) => commit(row, { start: v || null })} disabled={!canWrite || busy || sameDates} />
                  </td>
                  <td className={textCell}>
                    <CellInput ariaLabel={`${row.resource_name} end`} type="date" value={row.end ?? ""} placeholder={engagement.end} onCommit={(v) => commit(row, { end: v || null })} disabled={!canWrite || busy || sameDates} />
                  </td>
                  <td className={cn(numCell, calcCell)}>{hours(row.totals.hours)}</td>
                  <td className={numCell}>
                    <CellInput ariaLabel={`${row.resource_name} hours override`} type="number" min={0} value={row.hours_override === null ? "" : String(row.hours_override)} onCommit={(v) => commit(row, { hours_override: v === "" ? null : v })} disabled={!canWrite || busy} />
                  </td>
                  <td className={cn(numCell, calcCell)}>{row.burden_pct === undefined ? "—" : pct(row.burden_pct)}</td>
                  {hourly ? <td className={cn(numCell, calcCell)}>{money(row.totals.revenue)}</td> : null}
                  <td className={cn(numCell, calcCell)}>{row.totals.loaded_cost === undefined ? "—" : money(row.totals.loaded_cost)}</td>
                  {hourly ? (
                    <td className={cn(numCell, under ? "font-semibold text-danger" : calcCell)} data-testid="row-gm">
                      {row.totals.row_gm_pct === undefined ? "—" : pct(row.totals.row_gm_pct)}
                    </td>
                  ) : null}
                  <td className={textCell}>
                    {canWrite ? (
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" title="Set End to this month's last day" disabled={busy} onClick={() => void run(() => closeAllocation(row.id))}>
                          Leaves
                        </Button>
                        <Button size="sm" variant="ghost" title="Copy as a new row starting the day after the end" disabled={busy} onClick={() => void run(() => rehireAllocation(row.id))}>
                          Re-hire
                        </Button>
                        <Button size="sm" variant="ghost" title="Remove row" aria-label={`Remove ${row.resource_name}`} disabled={busy} onClick={() => void run(() => deleteAllocation(row.id))}>
                          ✕
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
            {allocations.length === 0 && !draft ? (
              <tr>
                <td className={cn(textCell, "text-text-secondary")} colSpan={colCount}>
                  No one is allocated yet. Add a person or import the staffing sheet.
                </td>
              </tr>
            ) : null}
            <tr className={totalsRow} data-testid="allocations-totals">
              <td className={textCell} colSpan={hourly ? 10 : 8}>
                Total
              </td>
              <td className={numCell}>{hours(staffing?.hours ?? forecast.totals.hours)}</td>
              <td className={numCell} />
              <td className={numCell} />
              {hourly ? <td className={numCell}>{money(staffing?.revenue)}</td> : null}
              <td className={numCell}>{staffing?.loaded_cost === undefined ? "—" : money(staffing.loaded_cost)}</td>
              {hourly ? <td className={numCell}>{staffing?.gm_pct === undefined ? "—" : pct(staffing.gm_pct)}</td> : null}
              <td className={textCell} />
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
