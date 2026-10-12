/**
 * Settings → Forecast calendar (S22 P2-5), the sheet's Settings tab:
 * 1 · hours per working day + project GM floor, 2 · burden % and resource
 * floor by location (+ add location), 3 · cost rate card, 4 · holidays by
 * location. Saved as one document with PUT /settings/forecast; the server
 * then re-runs every active engagement so the numbers move everywhere.
 *
 * Everything the engine runs with is here and nowhere else.
 */

import { useEffect, useState } from "react";
import { Plus, Save } from "lucide-react";
import {
  EMPLOYMENT_TYPE_LABEL,
  SENIORITIES,
  getForecastSettings,
  missingFrom,
  putForecastSettings,
  type EmploymentType,
  type ForecastCalendar,
  type Seniority,
} from "../../../api/engagements";
import { ApiError } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { cn } from "../../../lib/cn";
import { fractionToPercentText } from "../portfolio/format";
import { Panel, Problems, SETTINGS_WRITE_ROLES, cellInput, errorText, hasAny, headCell, headCellNum, numCell, table, tableWrap, textCell, useGroups } from "../portfolio/shared";

/** Editable mirror of the calendar: percentages as text ("36.0") so typing is natural; converted on save. */
interface Draft {
  hours_per_day: string;
  project_floor_pct: string;
  locations: { name: string; burden_pct_w2: string; burden_pct_1099: string; resource_floor_pct: string }[];
  rate_card: Record<string, string>; // `${seniority}|${location}|${employment}` -> cost text
  holidays: Record<string, string>; // location -> one date per line
}

function toDraft(calendar: ForecastCalendar): Draft {
  return {
    hours_per_day: String(calendar.hours_per_day),
    project_floor_pct: fractionToPercentText(calendar.project_floor_pct),
    locations: calendar.locations.map((l) => ({
      name: l.name,
      burden_pct_w2: fractionToPercentText(l.burden_pct_w2),
      burden_pct_1099: fractionToPercentText(l.burden_pct_1099),
      resource_floor_pct: fractionToPercentText(l.resource_floor_pct),
    })),
    rate_card: Object.fromEntries(calendar.rate_card.map((c) => [`${c.seniority}|${c.location}|${c.employment_type}`, c.cost_per_hour])),
    holidays: Object.fromEntries(calendar.locations.map((l) => [l.name, (calendar.holidays[l.name] ?? []).join("\n")])),
  };
}

function fromDraft(draft: Draft): ForecastCalendar {
  const rate_card: ForecastCalendar["rate_card"] = [];
  for (const [key, cost] of Object.entries(draft.rate_card)) {
    if (cost.trim() === "") continue;
    const [seniority, location, employment_type] = key.split("|");
    rate_card.push({ seniority: seniority as Seniority, location, employment_type: employment_type as EmploymentType, cost_per_hour: cost.trim() });
  }
  return {
    hours_per_day: Number(draft.hours_per_day),
    project_floor_pct: Number(draft.project_floor_pct) / 100,
    locations: draft.locations.map((l) => ({
      name: l.name.trim(),
      burden_pct_w2: Number(l.burden_pct_w2) / 100,
      burden_pct_1099: Number(l.burden_pct_1099) / 100,
      resource_floor_pct: Number(l.resource_floor_pct) / 100,
    })),
    rate_card,
    holidays: Object.fromEntries(
      draft.locations.map((l) => [l.name.trim(), (draft.holidays[l.name] ?? "").split(/\s+/).filter((x) => /^\d{4}-\d{2}-\d{2}$/.test(x))]),
    ),
  };
}

const EMPLOYMENTS: EmploymentType[] = ["w2_employee", "contractor_1099"];

export function ForecastSettingsSection() {
  const groups = useGroups();
  const editable = hasAny(groups, SETTINGS_WRITE_ROLES);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<Draft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newLocation, setNewLocation] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);
    getForecastSettings()
      .then((calendar) => {
        if (!active) return;
        const d = toDraft(calendar);
        setDraft(d);
        setSaved(d);
      })
      .catch((cause) => active && setError(cause));
    return () => {
      active = false;
    };
  }, [attempt]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <EmptyState title="You don't have access to the forecast calendar." description="The cost rate card is individual cost. Ask Finance or a SystemAdmin." />;
    }
    return <ErrorState title="We couldn't load the forecast calendar." description={errorText(error, "Retry to try again.")} onRetry={() => setAttempt((n) => n + 1)} />;
  }
  if (!draft) {
    return (
      <p role="status" className="text-body text-text-secondary">
        Loading forecast calendar…
      </p>
    );
  }

  const changed = JSON.stringify(draft) !== JSON.stringify(saved);
  const locations = draft.locations.map((l) => l.name);
  const disabled = !editable || saving;

  function edit(next: Draft) {
    setDraft(next);
    setStatus(null);
    setProblems(null);
  }

  function editLocation(index: number, patch: Partial<Draft["locations"][number]>) {
    const locationsNext = draft!.locations.map((l, i) => (i === index ? { ...l, ...patch } : l));
    edit({ ...draft!, locations: locationsNext });
  }

  function addLocation() {
    const name = newLocation.trim();
    if (!name || locations.includes(name)) return;
    edit({
      ...draft!,
      locations: [...draft!.locations, { name, burden_pct_w2: "0.0", burden_pct_1099: "0.0", resource_floor_pct: "35.0" }],
      holidays: { ...draft!.holidays, [name]: "" },
    });
    setNewLocation("");
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setProblems(null);
    setStatus(null);
    try {
      const calendar = await putForecastSettings(fromDraft(draft));
      const d = toDraft(calendar);
      setDraft(d);
      setSaved(d);
      setStatus("Forecast calendar saved — every active engagement was re-run.");
    } catch (cause) {
      const missing = missingFrom(cause);
      if (missing) setProblems(missing);
      else setStatus(errorText(cause, "The calendar was not saved."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Forecast calendar"
        subtitle="The sheet's Settings tab. Everything the engine runs with is here and nowhere else."
        actions={
          editable ? (
            <Button onClick={() => void save()} disabled={saving || !changed}>
              <Save className="mr-1 h-4 w-4" aria-hidden /> {saving ? "Saving…" : "Save calendar"}
            </Button>
          ) : undefined
        }
      />
      <Problems problems={problems} />
      {status ? (
        <p role="status" className="text-secondary text-text-secondary">
          {status}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="1 · General" hint="The project passes at or above the project floor. Each location also has a resource floor below, shown as a check.">
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
            <label className="text-secondary text-text-secondary" htmlFor="fc-hpd">
              Hours per working day
            </label>
            <input id="fc-hpd" type="number" min={1} step="0.5" className={cn(cellInput, "w-24 text-right")} disabled={disabled} value={draft.hours_per_day} onChange={(e) => edit({ ...draft, hours_per_day: e.target.value })} />
            <label className="text-secondary text-text-secondary" htmlFor="fc-floor">
              Project GM floor %
            </label>
            <input id="fc-floor" type="number" min={0} max={100} step="0.5" className={cn(cellInput, "w-24 text-right")} disabled={disabled} value={draft.project_floor_pct} onChange={(e) => edit({ ...draft, project_floor_pct: e.target.value })} />
          </div>
        </Panel>

        <Panel title="2 · Burden % and resource floor by location">
          <div className={tableWrap}>
            <table className={table} aria-label="Burden and floors by location">
              <thead>
                <tr>
                  <th className={headCell}>Location</th>
                  <th className={headCellNum}>W-2 / Employee</th>
                  <th className={headCellNum}>1099 / Contractor</th>
                  <th className={headCellNum}>Resource floor</th>
                </tr>
              </thead>
              <tbody>
                {draft.locations.map((l, index) => (
                  <tr key={l.name}>
                    <td className={textCell}>{l.name}</td>
                    <td className={numCell}>
                      <input aria-label={`${l.name} burden W-2 %`} type="number" step="0.5" min={0} max={100} className={cn(cellInput, "w-20 text-right")} disabled={disabled} value={l.burden_pct_w2} onChange={(e) => editLocation(index, { burden_pct_w2: e.target.value })} />%
                    </td>
                    <td className={numCell}>
                      <input aria-label={`${l.name} burden 1099 %`} type="number" step="0.5" min={0} max={100} className={cn(cellInput, "w-20 text-right")} disabled={disabled} value={l.burden_pct_1099} onChange={(e) => editLocation(index, { burden_pct_1099: e.target.value })} />%
                    </td>
                    <td className={numCell}>
                      <input aria-label={`${l.name} resource floor %`} type="number" step="0.5" min={0} max={100} className={cn(cellInput, "w-20 text-right")} disabled={disabled} value={l.resource_floor_pct} onChange={(e) => editLocation(index, { resource_floor_pct: e.target.value })} />%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editable ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input aria-label="New location" className={cn(cellInput, "w-40")} placeholder="New location" value={newLocation} onChange={(e) => setNewLocation(e.target.value)} />
              <Button type="button" size="sm" variant="secondary" onClick={addLocation} disabled={saving || !newLocation.trim()}>
                <Plus className="mr-1 h-4 w-4" aria-hidden /> Add location
              </Button>
            </div>
          ) : null}
        </Panel>
      </div>

      <Panel title="3 · Cost rate card — our hourly cost before burden" hint="Pre-fills a person's cost/hour by seniority × location × employment type. Typing on the row overrides it. Placeholder values until you set yours.">
        <div className={tableWrap}>
          <table className={table} aria-label="Cost rate card">
            <thead>
              <tr>
                <th className={headCell}>Seniority</th>
                {locations.map((loc) =>
                  EMPLOYMENTS.map((emp) => (
                    <th key={`${loc}|${emp}`} className={headCellNum}>
                      {loc} · {EMPLOYMENT_TYPE_LABEL[emp].split(" ")[0]}
                    </th>
                  )),
                )}
              </tr>
            </thead>
            <tbody>
              {SENIORITIES.map((seniority) => (
                <tr key={seniority}>
                  <td className={textCell}>{seniority}</td>
                  {locations.map((loc) =>
                    EMPLOYMENTS.map((emp) => {
                      const key = `${seniority}|${loc}|${emp}`;
                      return (
                        <td key={key} className={numCell}>
                          <input
                            aria-label={`${seniority} ${loc} ${EMPLOYMENT_TYPE_LABEL[emp]} cost per hour`}
                            type="number"
                            min={0}
                            className={cn(cellInput, "w-24 text-right")}
                            disabled={disabled}
                            value={draft.rate_card[key] ?? ""}
                            onChange={(e) => edit({ ...draft, rate_card: { ...draft.rate_card, [key]: e.target.value } })}
                          />
                        </td>
                      );
                    }),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="4 · Holidays by location" hint="One date per line (YYYY-MM-DD). Weekends are removed automatically; list weekday holidays. US = federal observed 2026–27; India = national days — add Holi, Diwali and company days.">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {locations.map((loc) => (
            <div key={loc}>
              <label className="text-secondary text-text-secondary" htmlFor={`fc-hol-${loc}`}>
                {loc}
              </label>
              <textarea
                id={`fc-hol-${loc}`}
                rows={8}
                className={cn(cellInput, "mt-1 w-full font-mono text-secondary")}
                disabled={disabled}
                value={draft.holidays[loc] ?? ""}
                onChange={(e) => edit({ ...draft, holidays: { ...draft.holidays, [loc]: e.target.value } })}
              />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
