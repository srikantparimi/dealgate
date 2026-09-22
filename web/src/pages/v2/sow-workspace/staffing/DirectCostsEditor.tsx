import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { getDirectCostCategories, type DeliveryCostLineInput, type DirectCostProposal } from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { formatQuantity, formatUsd } from "../format";

const DEFAULT_CATEGORIES = ["Travel", "Meals & lodging", "Software/licenses", "Subcontractor", "Equipment", "Other"];
export function proposalCosts(rows: DirectCostProposal[] = []): DeliveryCostLineInput[] {
  return rows.map((row) => ({ ...row, amount: row.amount ?? "", basis_value: row.basis_value ?? row.amount ?? "" }));
}
export function costsComplete(rows: DeliveryCostLineInput[]): boolean {
  return rows.every((row) => /^\d+(\.\d+)?$/.test(row.basis_value ?? row.amount));
}

export function DirectCostsEditor({ rows, onChange, disabled = false }: { rows: DeliveryCostLineInput[]; onChange?: (rows: DeliveryCostLineInput[]) => void; disabled?: boolean }) {
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [categoryError, setCategoryError] = useState(false);
  const loadCategories = useCallback(async () => {
    try { const res = await getDirectCostCategories(); setCategories(res.categories); setCategoryError(false); }
    catch { setCategoryError(true); }
  }, []);
  useEffect(() => { if (onChange) void loadCategories(); }, [Boolean(onChange), loadCategories]);
  function update(index: number, patch: Partial<DeliveryCostLineInput>) {
    onChange?.(rows.map((row, i) => i === index ? { ...row, ...patch, provenance: "manual" } : row));
  }
  return <fieldset disabled={disabled} className="min-w-0"><section aria-label="Direct costs" className="min-w-0 space-y-3">
    <div className="flex items-center justify-between gap-3"><h3 className="text-body font-semibold">Direct costs</h3>{onChange ? <Button variant="secondary" onClick={() => onChange([...rows, { category: categories[0] ?? "Other", note: "", amount: "", basis: "amount", basis_value: "", location: "proportional", reimbursable: false, provenance: "manual" }])}><Plus className="h-4 w-4" aria-hidden />Add cost</Button> : null}</div>
    {categoryError ? <div role="alert" className="flex flex-wrap items-center gap-2 text-secondary text-warning">Could not load cost categories.<Button variant="ghost" onClick={() => void loadCategories()}>Retry</Button></div> : null}
    {rows.length ? <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-secondary tnum"><thead className="border-b border-divider text-left text-text-secondary"><tr>{["Category", "Description", "Amount / basis", "Geography", "Reimbursable?", "Provenance", ""].map((title) => <th className="p-2 font-medium" key={title}>{title}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-b border-divider align-top">
      <td className="p-2">{onChange ? <select className="h-9 max-w-[150px] rounded-control border border-border bg-surface px-2" aria-label={`Cost category ${index + 1}`} value={row.category} onChange={(e) => update(index, { category: e.target.value })}>{Array.from(new Set([...categories, row.category])).map((category) => <option key={category}>{category}</option>)}</select> : row.category}</td>
      <td className="p-2">{onChange ? <Input className="min-w-[140px]" maxLength={240} aria-label={`Cost description ${index + 1}`} value={row.note ?? ""} onChange={(e) => update(index, { note: e.target.value })} /> : row.note || "—"}</td>
      <td className="min-w-[155px] p-2">{onChange ? <div className="space-y-1"><Input type="number" min="0" step="0.01" aria-label={`Cost value ${index + 1}`} value={row.basis_value ?? row.amount} onChange={(e) => update(index, { basis_value: e.target.value, amount: row.basis === "percent_revenue" ? row.amount : e.target.value })} /><select className="h-8 w-full rounded-control border border-border bg-surface px-1" aria-label={`Cost basis ${index + 1}`} value={row.basis ?? "amount"} onChange={(e) => update(index, { basis: e.target.value as "amount" | "percent_revenue" })}><option value="amount">USD amount</option><option value="percent_revenue">% of revenue</option></select></div> : <>{row.basis === "percent_revenue" ? `${formatQuantity(row.basis_value)}% of revenue · ` : ""}{formatUsd(row.amount) ?? "Amount needed"}</>}</td>
      <td className="p-2">{onChange ? <select className="h-9 max-w-[155px] rounded-control border border-border bg-surface px-2" aria-label={`Cost geography ${index + 1}`} value={row.location} onChange={(e) => update(index, { location: e.target.value as DeliveryCostLineInput["location"] })}><option>US</option><option>India</option><option value="proportional">Proportional to labor</option></select> : row.location === "proportional" ? "Proportional to labor" : row.location}</td>
      <td className="p-2">{onChange ? <label className="flex h-9 items-center gap-2"><input type="checkbox" aria-label={`Cost reimbursable ${index + 1}`} checked={row.reimbursable ?? false} onChange={(e) => update(index, { reimbursable: e.target.checked })} />{row.reimbursable ? "Yes" : "No"}</label> : row.reimbursable ? "Yes" : "No"}</td>
      <td className="p-2 text-text-secondary">{row.provenance ?? "manual"}{row.source_ref ? <span className="block text-xs">{row.source_ref}</span> : null}</td>
      <td className="p-2">{onChange ? <Button variant="ghost" size="icon" aria-label={`Remove cost ${index + 1}`} title="Remove cost" onClick={() => onChange(rows.filter((_, i) => i !== index))}><Trash2 className="h-4 w-4" /></Button> : null}</td>
    </tr>)}</tbody></table></div> : <p className="text-secondary text-text-muted">No direct costs.</p>}
  </section></fieldset>;
}
