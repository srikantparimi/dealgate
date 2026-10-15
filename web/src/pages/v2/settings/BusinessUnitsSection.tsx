/**
 * Settings → Business units (S23-PL2 F18, API B3).
 *
 * Deals carry HubSpot region values, not business units. This map says which
 * business unit each value belongs to and which region is shown beside it.
 * US holds two business units (ST21 and IT Avalon), so a business unit is
 * never shown without its region. The server applies a saved map to every
 * deal immediately (no resync) and lists the region values that appear on
 * live deals without a mapping, with their deal counts.
 */

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import {
  ApiError,
  getBusinessUnitMap,
  saveBusinessUnitMap,
  type RegionMap,
  type RegionMapBusinessUnit,
  type RegionMapRow,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";

interface DraftRow {
  /** React key; stable for the life of the row. */
  key: number;
  /** How controls name the row: its HubSpot value when it appeared, or "new row N". */
  label: string;
  hubspot_value: string;
  business_unit: RegionMapBusinessUnit | "";
  region: string;
  note: string;
}

const TH = "px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide";
const SELECT =
  "h-10 w-full rounded-control border border-input-border bg-surface px-2 text-body text-text " +
  "focus-visible:outline-focus disabled:opacity-60";

function toDraft(rows: RegionMapRow[]): DraftRow[] {
  return rows.map((row, index) => ({
    key: index,
    label: row.hubspot_value,
    hubspot_value: row.hubspot_value,
    business_unit: row.business_unit,
    region: row.region,
    note: row.note ?? "",
  }));
}

function toRows(rows: DraftRow[]): RegionMapRow[] {
  return rows.map((row) => ({
    hubspot_value: row.hubspot_value.trim(),
    business_unit: row.business_unit as RegionMapBusinessUnit,
    region: row.region.trim(),
    note: row.note.trim() || null,
  }));
}

/** What must be fixed before the map can be saved (the server checks the same). */
function problems(rows: DraftRow[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const twice = new Set<string>();
  for (const row of rows) {
    const value = row.hubspot_value.trim();
    if (!value) {
      out.push(`Enter the HubSpot value for ${row.label}.`);
      continue;
    }
    if (seen.has(value) && !twice.has(value)) {
      twice.add(value);
      out.push(`“${value}” is listed twice.`);
    }
    seen.add(value);
    if (!row.business_unit) out.push(`Choose the business unit for “${value}”.`);
    if (!row.region.trim()) out.push(`Enter the region shown beside the business unit for “${value}”.`);
  }
  return out;
}

/** How deals with this HubSpot value show their business unit. */
function shownAs(row: DraftRow): string {
  if (!row.business_unit) return "Business unit not chosen";
  return [row.business_unit, row.region.trim() || "region not set", row.note.trim()]
    .filter(Boolean)
    .join(" · ");
}

function dealCount(n: number): string {
  return n === 1 ? "1 deal" : `${n.toLocaleString("en-US")} deals`;
}

export function BusinessUnitsSection() {
  const [data, setData] = useState<RegionMap | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [nextKey, setNextKey] = useState(10_000);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    setLoadError(null);
    getBusinessUnitMap()
      .then((map) => {
        setData(map);
        setRows(toDraft(map.rows));
      })
      .catch((err: unknown) => setLoadError(err));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const issues = useMemo(() => problems(rows), [rows]);
  const changed = data !== null && JSON.stringify(toRows(rows)) !== JSON.stringify(data.rows);

  function edit(key: number, patch: Partial<DraftRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    setSaved(false);
    setSaveError(null);
  }

  function add(value: string) {
    if (value && rows.some((row) => row.hubspot_value.trim() === value)) return;
    let n = rows.length + 1;
    while (rows.some((row) => row.label === `new row ${n}`)) n += 1;
    setRows([
      ...rows,
      { key: nextKey, label: value || `new row ${n}`, hubspot_value: value, business_unit: "", region: "", note: "" },
    ]);
    setNextKey(nextKey + 1);
    setSaved(false);
  }

  function remove(key: number) {
    setRows((current) => current.filter((row) => row.key !== key));
    setSaved(false);
    setSaveError(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (issues.length > 0 || !changed) return;
    setSaving(true);
    setSaveError(null);
    try {
      const map = await saveBusinessUnitMap(toRows(rows));
      setData(map);
      setRows(toDraft(map.rows));
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "The business units could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    if (loadError instanceof ApiError && loadError.status === 403) {
      return (
        <EmptyState
          title="You don't have access to this section."
          description="Ask a SystemAdmin if a HubSpot region needs a business unit."
        />
      );
    }
    return (
      <ErrorState
        title="We couldn't load the business units."
        description="Retry to try again."
        onRetry={load}
      />
    );
  }
  if (!data) {
    return <EmptyState title="Loading" description="Fetching the business unit map." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Business units"
        subtitle={
          "Which business unit each HubSpot region value belongs to, and the region shown beside it. " +
          "A saved change shows on every deal immediately, with no resync."
        }
      />
      <p className="rounded-panel border border-divider bg-primary-subtle/20 px-4 py-3 text-body text-text">
        US covers two different business units, ST21 and IT Avalon, so a business unit is always shown with its
        region.
      </p>

      {data.unmapped_on_deals.length > 0 && (
        <section
          aria-labelledby="bu-unmapped-heading"
          className="flex flex-col gap-3 rounded-panel border border-divider bg-warning-surface p-4"
        >
          <h2 id="bu-unmapped-heading" className="text-section text-text">
            Unmapped HubSpot values
          </h2>
          <p className="text-secondary text-text-secondary">
            These region values are on live deals but have no business unit yet. Until they are mapped, those deals
            show an unmapped region on the Pipeline.
          </p>
          <ul className="flex flex-col gap-2">
            {data.unmapped_on_deals.map((item) => (
              <li key={item.hubspot_value} className="flex flex-wrap items-center gap-3">
                <span className="font-medium text-text">{item.hubspot_value}</span>
                <span className="tnum text-text-secondary">{dealCount(item.deals)}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  aria-label={`Map ${item.hubspot_value}`}
                  onClick={() => add(item.hubspot_value)}
                >
                  Map
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {data.deals_without_region > 0 && (
        <p className="text-secondary text-text-secondary">
          {`${data.deals_without_region === 1 ? "1 deal has" : `${dealCount(data.deals_without_region)} have`} ` +
            "no HubSpot region. Set the region on the deal in HubSpot."}
        </p>
      )}

      <form aria-labelledby="bu-map-heading" className="flex flex-col gap-3" onSubmit={(e) => void save(e)}>
        <h2 id="bu-map-heading" className="text-section text-text">
          Mapping
        </h2>
        <div className="overflow-x-auto rounded-panel border border-divider">
          <table className="w-full border-collapse text-body">
            <thead className="bg-primary-subtle/30">
              <tr>
                <th scope="col" className={TH}>HubSpot value</th>
                <th scope="col" className={TH}>Business unit</th>
                <th scope="col" className={TH}>Region</th>
                <th scope="col" className={TH}>Note</th>
                <th scope="col" className={TH}>Shown on deals as</th>
                <th scope="col" className={TH}>
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} aria-label={`Mapping for ${row.label}`} className="border-t border-divider align-top">
                  <td className="px-3 py-2">
                    <Input
                      aria-label={`HubSpot value for ${row.label}`}
                      value={row.hubspot_value}
                      maxLength={255}
                      disabled={saving}
                      onChange={(e) => edit(row.key, { hubspot_value: e.target.value })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <select
                      aria-label={`Business unit for ${row.label}`}
                      className={SELECT}
                      value={row.business_unit}
                      disabled={saving}
                      onChange={(e) => edit(row.key, { business_unit: e.target.value as RegionMapBusinessUnit })}
                    >
                      <option value="" disabled>
                        Choose a business unit
                      </option>
                      {data.business_units.map((bu) => (
                        <option key={bu} value={bu}>
                          {bu}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <Input
                      aria-label={`Region for ${row.label}`}
                      value={row.region}
                      maxLength={64}
                      disabled={saving}
                      onChange={(e) => edit(row.key, { region: e.target.value })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <Input
                      aria-label={`Note for ${row.label}`}
                      value={row.note}
                      maxLength={128}
                      placeholder="Optional"
                      disabled={saving}
                      onChange={(e) => edit(row.key, { note: e.target.value })}
                    />
                  </td>
                  <td className="px-3 py-2 pt-4 text-text-secondary">{shownAs(row)}</td>
                  <td className="px-3 py-2">
                    <Button
                      type="button"
                      variant="tertiary"
                      size="sm"
                      aria-label={`Remove the mapping for ${row.label}`}
                      disabled={saving}
                      onClick={() => remove(row.key)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <p className="text-secondary text-text-secondary">
            No mappings. Every deal will show an unmapped region until a HubSpot value is mapped.
          </p>
        )}
        {issues.length > 0 && (
          <ul aria-label="Fix before saving" className="flex flex-col gap-1 text-secondary text-danger">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" disabled={saving} onClick={() => add("")}>
            <Plus className="h-4 w-4" aria-hidden /> Add mapping
          </Button>
          <Button type="submit" size="sm" disabled={saving || issues.length > 0 || !changed}>
            <Save className="h-4 w-4" aria-hidden /> {saving ? "Saving…" : "Save mapping"}
          </Button>
        </div>
        {saveError && (
          <p role="alert" className="text-secondary text-danger">
            {saveError}
          </p>
        )}
        {saved && (
          <p role="status" className="text-secondary text-text-secondary">
            Saved. Every deal shows the new business units now.
          </p>
        )}
      </form>
    </div>
  );
}
