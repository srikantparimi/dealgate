import { Plus, Trash2 } from "lucide-react";
import type { PeriodCost } from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";

export function AdditionalCostsEditor({
  rows,
  serviceStart,
  onChange,
}: {
  rows: PeriodCost[];
  serviceStart: string | null;
  onChange: (rows: PeriodCost[]) => void;
}) {
  const month = serviceStart ? `${serviceStart.slice(0, 7)}-01` : "";
  const update = (index: number, patch: Partial<PeriodCost>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <section aria-label="Additional costs" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-body font-semibold">Additional costs</h3>
          <p className="text-secondary text-text-secondary">
            Travel, software, subcontractors or any other delivery cost outside the team.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() =>
            onChange([
              ...rows,
              {
                source_id: crypto.randomUUID(),
                description: "",
                month,
                location: "US",
                amount: null,
              },
            ])
          }
        >
          <Plus className="h-4 w-4" /> Add cost
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className="text-secondary text-text-muted">No additional costs.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-secondary">
            <thead className="bg-surface-2 text-text-secondary">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Description</th>
                <th className="px-3 py-2 text-left font-medium">Amount</th>
                <th className="px-3 py-2 text-left font-medium">Location</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.source_id} className="border-t border-border">
                  <td className="p-2">
                    <Input aria-label={`Additional cost description ${index + 1}`} value={row.description ?? ""} onChange={(event) => update(index, { description: event.target.value })} />
                  </td>
                  <td className="p-2">
                    <Input inputMode="decimal" aria-label={`Additional cost amount ${index + 1}`} value={row.amount ?? ""} onChange={(event) => update(index, { amount: event.target.value || null })} />
                  </td>
                  <td className="p-2">
                    <select aria-label={`Additional cost location ${index + 1}`} className="h-9 rounded-md border border-border bg-surface px-2" value={row.location} onChange={(event) => update(index, { location: event.target.value })}>
                      <option value="US">US</option><option value="India">India</option>
                    </select>
                  </td>
                  <td className="p-2 text-right">
                    <Button variant="ghost" size="icon" aria-label={`Remove additional cost ${index + 1}`} title="Remove cost" onClick={() => onChange(rows.filter((_, i) => i !== index))}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
