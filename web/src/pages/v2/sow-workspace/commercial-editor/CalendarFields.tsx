import { Plus, Trash2 } from "lucide-react";
import type {
  CommercialComponent,
  CommercialStaffing,
  CommercialStaffingRate,
} from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";

function pricingWithRate(
  component: CommercialComponent,
  row: CommercialStaffing,
  billRate: string | null,
) {
  if (component.profile !== "calendar_staff_aug") return component.pricing;
  const rates = component.pricing?.rates ?? [];
  const current: CommercialStaffingRate = rates.find(
    (rate) => rate.assignment_id === row.assignment_id,
  ) ?? {
    assignment_id: row.assignment_id,
    basis: "hourly",
    rate: null,
    version: null,
    hours_per_day: null,
    proration: null,
  };
  return {
    ...component.pricing,
    rates: [
      ...rates.filter((rate) => rate.assignment_id !== row.assignment_id),
      { ...current, rate: billRate, version: billRate ? "manual" : null },
    ],
  };
}

/** A single staffing grid; monthly Forecast rows are derived server-side. */
export function CalendarFields({
  component,
  onChange,
}: {
  component: CommercialComponent;
  onChange: (component: CommercialComponent) => void;
}) {
  const assignments = component.staffing;
  const update = (index: number, value: CommercialStaffing) =>
    onChange({
      ...component,
      staffing: assignments.map((row, i) => (i === index ? value : row)),
    });

  return (
    <section aria-label="Staffing plan" className="min-w-0 space-y-4">
      <div>
        <h3 className="text-body font-semibold">Resources</h3>
        <p className="text-secondary text-text-secondary" data-testid="team-contract-term">
          Contract term: {component.service_start || "start not set"} to{" "}
          {component.service_end || "end not set"}. Role dates default to the
          contract term and remain editable.
        </p>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[78rem] text-secondary">
          <thead className="bg-surface-2 text-text-secondary">
            <tr>
              {[
                "Role",
                "Seniority",
                "Location",
                "People",
                "Utilization %",
                "Hours",
                "Bill rate",
                "Cost / hour",
                "Start",
                "End",
                "",
              ].map((label) => (
                <th key={label} className="px-3 py-2 text-left font-medium">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {assignments.map((row, index) => {
              const patch = (changes: Partial<CommercialStaffing>) =>
                update(index, { ...row, ...changes });
              return (
                <tr
                  key={row.assignment_id}
                  data-staffing-row={index + 1}
                  className="border-t border-border align-top"
                >
                  <td className="p-2">
                    <Input aria-label={`Role ${index + 1}`} value={row.role} onChange={(event) => patch({ role: event.target.value })} />
                  </td>
                  <td className="p-2">
                    <Input aria-label={`Seniority ${index + 1}`} value={row.seniority ?? ""} onChange={(event) => patch({ seniority: event.target.value || null })} />
                  </td>
                  <td className="p-2">
                    <select aria-label={`Location ${index + 1}`} className="h-9 rounded-md border border-border bg-surface px-2" value={row.location ?? ""} onChange={(event) => patch({ location: event.target.value || null })}>
                      <option value="">Select</option><option value="US">US</option><option value="India">India</option>
                    </select>
                  </td>
                  <td className="p-2">
                    <Input type="number" min="1" step="1" aria-label={`People ${index + 1}`} value={row.quantity || ""} onChange={(event) => patch({ quantity: Number(event.target.value) || 0 })} />
                  </td>
                  <td className="p-2">
                    <Input inputMode="decimal" aria-label={`Utilization ${index + 1}`} value={row.allocation ? String(Number(row.allocation) * 100) : ""} onChange={(event) => { const value = event.target.value; patch({ allocation: value === "" ? "" : String(Number(value) / 100) }); }} />
                  </td>
                  <td className="p-2">
                    <Input inputMode="decimal" aria-label={`Hours ${index + 1}`} value={row.hours_billable ?? ""} onChange={(event) => patch({ hours_billable: event.target.value || null, calendar: null })} />
                  </td>
                  <td className="p-2">
                    {component.profile === "fixed_assignment" ? <span className="inline-flex h-9 items-center whitespace-nowrap text-text-muted">Fixed fee</span> : (
                      <Input inputMode="decimal" aria-label={`Bill rate ${index + 1}`} value={row.bill_rate ?? ""} onChange={(event) => { const value = event.target.value || null; onChange({ ...component, staffing: assignments.map((item, i) => i === index ? { ...row, bill_rate: value, rate_version: value ? "manual" : null } : item), pricing: pricingWithRate(component, row, value) }); }} />
                    )}
                  </td>
                  <td className="p-2">
                    <Input inputMode="decimal" aria-label={`Cost per hour ${index + 1}`} value={row.cost_rate ?? ""} onChange={(event) => { const value = event.target.value || null; patch({ cost_rate: value, cost_rate_basis: "hourly", cost_version: value ? "manual" : null }); }} />
                  </td>
                  <td className="p-2">
                    <Input type="date" aria-label={`Start ${index + 1}`} value={row.start ?? ""} onChange={(event) => patch({ start: event.target.value || null })} />
                  </td>
                  <td className="p-2">
                    <Input type="date" aria-label={`End ${index + 1}`} value={row.end ?? ""} onChange={(event) => patch({ end: event.target.value || null })} />
                  </td>
                  <td className="p-2">
                    <Button variant="ghost" size="icon" aria-label={`Remove role ${index + 1}`} title="Remove role" onClick={() => onChange({ ...component, staffing: assignments.filter((_, i) => i !== index), pricing: component.profile === "calendar_staff_aug" ? { ...component.pricing, rates: (component.pricing?.rates ?? []).filter((rate) => rate.assignment_id !== row.assignment_id) } : component.pricing })}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Button variant="secondary" onClick={() => onChange({ ...component, staffing: [...assignments, {
        assignment_id: crypto.randomUUID(), source_id: component.source_id,
        source_version: component.source_version, component_id: component.component_id,
        profile_version: component.profile_version, policy_version: component.policy_version,
        role: "", seniority: "", location: null,
        timezone: component.timezone ?? "America/Los_Angeles", currency: component.currency,
        quantity: 1, allocation: "1", hours_billable: null, calendar: null,
        bill_rate: null, cost_rate: null, rate_version: null, cost_version: null,
        cost_rate_basis: "hourly", start: component.service_start, end: component.service_end,
      }] })}>
        <Plus className="h-4 w-4" /> Add role
      </Button>
    </section>
  );
}
