/**
 * Setup & costs (S22 P2-3): the sheet's project block (client, name, owner,
 * currency, type, dates, price or fee, additional costs Y/N, same dates Y/N)
 * with type-driven greying, and the additional-costs table where frequency
 * and billed-to-client are required. Each change PATCHes the server; the
 * engine's validation strings come back verbatim as "Missing: …".
 */

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { getPipelineFacets, type PipelineOwnerFacet } from "../../../api/client";
import {
  CURRENCIES,
  ENGAGEMENT_TYPE_LABEL,
  FIXED_TYPES,
  addCost,
  deleteCost,
  listClientOptions,
  missingFrom,
  patchCost,
  patchEngagement,
  type ClientOption,
  type EngagementCost,
  type EngagementType,
} from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { cn } from "../../../lib/cn";
import type { EngagementData } from "./EngagementPage";
import { money } from "./format";
import { CellInput, CellSelect, Panel, Problems, cellInput, errorText, headCell, headCellNum, numCell, table, tableWrap, textCell } from "./shared";

const FREQUENCY_OPTIONS = [
  { value: "one_time", label: "One-time" },
  { value: "monthly", label: "Monthly" },
];
const BILLED_OPTIONS = [
  { value: "0", label: "No — we absorb" },
  { value: "1", label: "Yes — pass-through" },
];
const YES_NO = (yes: string, no: string) => [
  { value: "1", label: yes },
  { value: "0", label: no },
];

interface CostDraft {
  description: string;
  category: string;
  amount: string;
  frequency: "one_time" | "monthly";
  billed_to_client: "" | "0" | "1";
}

export function SetupTab({ data, canWrite, onChanged }: { data: EngagementData; canWrite: boolean; onChanged: () => Promise<void> }) {
  const { engagement, costs, forecast } = data;
  const [clients, setClients] = useState<ClientOption[]>([]);
  const [owners, setOwners] = useState<PipelineOwnerFacet[]>([]);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [costDraft, setCostDraft] = useState<CostDraft | null>(null);

  useEffect(() => {
    let cancelled = false;
    listClientOptions().then((rows) => !cancelled && setClients(rows)).catch(() => undefined);
    getPipelineFacets().then((f) => !cancelled && setOwners(f.owners)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setProblems(null);
    setNotice(null);
    try {
      await action();
      await onChanged();
    } catch (cause) {
      const missing = missingFrom(cause);
      if (missing) setProblems(missing);
      else setNotice(errorText(cause, "The change was not saved."));
    } finally {
      setBusy(false);
    }
  }

  const patch = (body: Record<string, unknown>) => void run(() => patchEngagement(engagement.id, body));
  const disabled = !canWrite || busy;
  const fixed = FIXED_TYPES.has(engagement.type);
  const msp = engagement.type === "msp";
  const ownerOptions = [
    { value: "", label: "—" },
    ...owners.map((o) => ({ value: o.id, label: o.name })),
    ...(engagement.owner_user_id && !owners.some((o) => o.id === engagement.owner_user_id)
      ? [{ value: engagement.owner_user_id, label: engagement.owner_name ?? "Current owner" }]
      : []),
  ];

  async function submitCost() {
    if (!costDraft) return;
    await run(async () => {
      if (costDraft.billed_to_client === "") throw Object.assign(new Error("billed to client is required"), { body: { detail: { missing: [`${costDraft.description || "cost"}: billed to client Y/N is required`] } } });
      await addCost(engagement.id, {
        description: costDraft.description,
        category: costDraft.category || null,
        amount: costDraft.amount,
        frequency: costDraft.frequency,
        billed_to_client: costDraft.billed_to_client === "1",
      });
      setCostDraft(null);
    });
  }

  const editCost = (row: EngagementCost, body: Record<string, unknown>) => void run(() => patchCost(row.id, body));

  return (
    <div className="flex flex-col gap-3">
      <Problems problems={problems} />
      {notice ? (
        <p role="status" className="text-secondary text-text-secondary">
          {notice}
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="Engagement — the sheet's project block">
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
            <label className="text-secondary text-text-secondary">Client</label>
            <CellSelect
              ariaLabel="Client"
              value={engagement.client_id}
              options={clients.length ? clients.map((c) => ({ value: c.id, label: c.name })) : [{ value: engagement.client_id, label: engagement.client_name }]}
              onCommit={(v) => patch({ client_id: v })}
              disabled={disabled}
            />
            <label className="text-secondary text-text-secondary">Engagement name</label>
            <CellInput ariaLabel="Engagement name" value={engagement.name} onCommit={(v) => patch({ name: v })} disabled={disabled} className="w-full" />
            <label className="text-secondary text-text-secondary">Owner</label>
            <CellSelect ariaLabel="Owner" value={engagement.owner_user_id ?? ""} options={ownerOptions} onCommit={(v) => patch({ owner_user_id: v || null })} disabled={disabled} />
            <label className="text-secondary text-text-secondary">Currency</label>
            <CellSelect ariaLabel="Currency" value={engagement.currency} options={CURRENCIES.map((c) => ({ value: c, label: c }))} onCommit={(v) => patch({ currency: v })} disabled={disabled} />
            <label className="text-secondary text-text-secondary">Type</label>
            <CellSelect
              ariaLabel="Type"
              value={engagement.type}
              options={(Object.keys(ENGAGEMENT_TYPE_LABEL) as EngagementType[]).map((t) => ({ value: t, label: ENGAGEMENT_TYPE_LABEL[t] }))}
              onCommit={(v) => patch({ type: v })}
              disabled={disabled}
            />
            <label className="text-secondary text-text-secondary">Start</label>
            <CellInput ariaLabel="Start" type="date" value={engagement.start} onCommit={(v) => patch({ start: v })} disabled={disabled} />
            <label className="text-secondary text-text-secondary">End</label>
            <CellInput ariaLabel="End" type="date" value={engagement.end} onCommit={(v) => patch({ end: v })} disabled={disabled} />
            <label className="text-secondary text-text-secondary">Total price</label>
            <CellInput
              ariaLabel="Total price"
              type="number"
              min={0}
              value={engagement.total_price ?? ""}
              onCommit={(v) => patch({ total_price: v === "" ? null : v })}
              disabled={disabled || !fixed}
              title={fixed ? undefined : "Fixed cost / Assessment only"}
            />
            <label className="text-secondary text-text-secondary">Monthly fee</label>
            <CellInput
              ariaLabel="Monthly fee"
              type="number"
              min={0}
              value={engagement.monthly_fee ?? ""}
              onCommit={(v) => patch({ monthly_fee: v === "" ? null : v })}
              disabled={disabled || !msp}
              title={msp ? undefined : "MSP only"}
            />
            <label className="text-secondary text-text-secondary">Same dates for everyone</label>
            <CellSelect
              ariaLabel="Same dates for everyone"
              value={engagement.same_dates_for_all ? "1" : "0"}
              options={YES_NO("Yes", "No — each person has their own")}
              onCommit={(v) => patch({ same_dates_for_all: v === "1" })}
              disabled={disabled}
            />
            <label className="text-secondary text-text-secondary">Additional costs?</label>
            <CellSelect
              ariaLabel="Additional costs"
              value={engagement.additional_costs_flag ? "1" : "0"}
              options={YES_NO("Yes", "No")}
              onCommit={(v) => patch({ additional_costs_flag: v === "1" })}
              disabled={disabled}
            />
          </div>
        </Panel>

        <Panel title="Additional costs">
          <div className={tableWrap}>
            <table className={table} aria-label="Additional costs">
              <thead>
                <tr>
                  <th className={headCell}>Description</th>
                  <th className={headCell}>Category</th>
                  <th className={headCellNum}>Amount</th>
                  <th className={headCell}>Frequency</th>
                  <th className={headCell}>Billed to client</th>
                  <th className={headCell} />
                </tr>
              </thead>
              <tbody>
                {costs.map((row) => (
                  <tr key={row.id} data-testid="cost-row">
                    <td className={textCell}>
                      <CellInput ariaLabel={`${row.description} description`} value={row.description} onCommit={(v) => editCost(row, { description: v })} disabled={disabled} className="w-40" />
                    </td>
                    <td className={textCell}>
                      <CellInput ariaLabel={`${row.description} category`} value={row.category ?? ""} onCommit={(v) => editCost(row, { category: v || null })} disabled={disabled} className="w-32" />
                    </td>
                    <td className={numCell}>
                      <CellInput ariaLabel={`${row.description} amount`} type="number" min={0} value={row.amount} onCommit={(v) => editCost(row, { amount: v })} disabled={disabled} />
                    </td>
                    <td className={textCell}>
                      <CellSelect ariaLabel={`${row.description} frequency`} value={row.frequency} options={FREQUENCY_OPTIONS} onCommit={(v) => editCost(row, { frequency: v })} disabled={disabled} />
                    </td>
                    <td className={textCell}>
                      <CellSelect ariaLabel={`${row.description} billed to client`} value={row.billed_to_client ? "1" : "0"} options={BILLED_OPTIONS} onCommit={(v) => editCost(row, { billed_to_client: v === "1" })} disabled={disabled} />
                    </td>
                    <td className={textCell}>
                      {canWrite ? (
                        <Button size="sm" variant="ghost" aria-label={`Remove ${row.description}`} disabled={busy} onClick={() => void run(() => deleteCost(row.id))}>
                          ✕
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {costDraft ? (
                  <tr className="bg-primary-subtle" data-testid="cost-draft">
                    <td className={textCell}>
                      <input aria-label="New cost description" className={cn(cellInput, "w-40")} placeholder="Description" value={costDraft.description} onChange={(e) => setCostDraft({ ...costDraft, description: e.target.value })} />
                    </td>
                    <td className={textCell}>
                      <input aria-label="New cost category" className={cn(cellInput, "w-32")} placeholder="Travel, licences…" value={costDraft.category} onChange={(e) => setCostDraft({ ...costDraft, category: e.target.value })} />
                    </td>
                    <td className={numCell}>
                      <input aria-label="New cost amount" type="number" min={0} className={cn(cellInput, "w-24 text-right")} value={costDraft.amount} onChange={(e) => setCostDraft({ ...costDraft, amount: e.target.value })} />
                    </td>
                    <td className={textCell}>
                      <select aria-label="New cost frequency" className={cellInput} value={costDraft.frequency} onChange={(e) => setCostDraft({ ...costDraft, frequency: e.target.value as "one_time" | "monthly" })}>
                        {FREQUENCY_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={textCell}>
                      <select aria-label="New cost billed to client" className={cellInput} value={costDraft.billed_to_client} onChange={(e) => setCostDraft({ ...costDraft, billed_to_client: e.target.value as "" | "0" | "1" })}>
                        <option value="">— required —</option>
                        {BILLED_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={textCell}>
                      <div className="flex gap-1">
                        <Button size="sm" disabled={busy || !costDraft.description.trim() || costDraft.amount.trim() === ""} onClick={() => void submitCost()}>
                          Add
                        </Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setCostDraft(null)}>
                          Cancel
                        </Button>
                      </div>
                    </td>
                  </tr>
                ) : null}
                {costs.length === 0 && !costDraft ? (
                  <tr>
                    <td className={cn(textCell, "text-text-secondary")} colSpan={6}>
                      {engagement.additional_costs_flag ? "Additional costs is Yes — add the travel, licences or subcontractor lines." : "No additional costs on this engagement."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {canWrite ? (
            <div className="mt-2 flex items-center gap-3">
              <Button size="sm" variant="secondary" disabled={busy || costDraft !== null} onClick={() => setCostDraft({ description: "", category: "", amount: "", frequency: "one_time", billed_to_client: "" })}>
                <Plus className="mr-1 h-4 w-4" aria-hidden /> Add cost
              </Button>
            </div>
          ) : null}
          <p className="mt-2 text-secondary text-text-secondary">
            Totals: {money(forecast.totals.additional_costs)} cost, {money(forecast.totals.pass_through_revenue)} billed through.
            {!engagement.additional_costs_flag && costs.length > 0 ? " Additional costs is No — these lines are not counted until it is Yes." : ""}
          </p>
        </Panel>
      </div>
    </div>
  );
}
