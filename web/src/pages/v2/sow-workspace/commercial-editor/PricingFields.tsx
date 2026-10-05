import type {
  CommercialComponent,
  CommercialMilestone,
  CommercialPricing,
  CommercialQuantity,
} from "../../../../api/commercial";
import { Field, Rows, Select, type Column } from "./Fields";
import { MspAdjustmentsFields } from "./MspAdjustmentsFields";

export const PROFILE_LABELS: Record<string, string> = {
  fixed_assignment: "Fixed assignment",
  recurring_msp: "Recurring MSP",
  milestone: "Milestone",
  unit: "Unit / story point",
  tm: "Time & materials",
  calendar_staff_aug: "Calendar staff augmentation",
  hybrid: "Hybrid",
};
export function emptyPricing(profile: string): CommercialPricing {
  switch (profile) {
    case "calendar_staff_aug":
      return { rates: [] };
    case "hybrid":
      return {
        components: [],
        shared_cost_allocations: [],
        allocation_basis: null,
        minor_unit: null,
        fx_rates: [],
      };
    case "milestone":
      return { milestones: [] };
    case "unit":
      return { rate: null, unit: "", quantities: [], contractual_basis: null };
    case "tm":
      return {
        rate: null,
        unit: "",
        estimates: [],
        approved_usage: [],
        cap: null,
        minimum: null,
        limit_allocation_basis: null,
        minor_unit: undefined,
        calendar_estimates: false,
      };
    case "recurring_msp":
      return {
        fees: [],
        proration: null,
        included_scope: null,
        adjustments: [],
        usage: [],
      };
    default:
      return {
        total_fee: null,
        allocations: [],
        allocation_basis: null,
        minor_unit: "",
      };
  }
}
export function PricingFields({
  component,
  onChange,
}: {
  component: CommercialComponent;
  onChange: (pricing: CommercialPricing) => void;
}) {
  const pricing = component.pricing ?? {};
  const patch = (key: keyof CommercialPricing, value: unknown) =>
    onChange({ ...pricing, [key]: value });
  const quantity = (): CommercialQuantity => ({
    source_id: crypto.randomUUID(),
    month: "",
    location: "",
    quantity: null,
  });
  const columns = (label: string): Column<CommercialQuantity>[] => [
    { key: "month", label: "Service month", type: "date" },
    { key: "location", label: "Location", options: ["US", "India"] },
    { key: "quantity", label, type: "decimal" },
  ];
  if (component.profile === "fixed_assignment")
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field
            label="Total fee"
            type="decimal"
            value={pricing.total_fee}
            onChange={(value) => patch("total_fee", value || null)}
          />
          <Field
            label="Allocation basis"
            value={pricing.allocation_basis}
            onChange={(value) => patch("allocation_basis", value || null)}
          />
          <Field
            label="Rounding unit (advanced — 0.01 = cents)"
            type="decimal"
            value={pricing.minor_unit}
            onChange={(value) => patch("minor_unit", value)}
          />
        </div>
        <Rows
          title="Service-month allocations (each month's share of the fee — weights must add to 1)"
          rows={pricing.allocations ?? []}
          columns={[
            { key: "month", label: "Allocation month", type: "date" },
            {
              key: "location",
              label: "Allocation location",
              options: ["US", "India"],
            },
            { key: "weight", label: "Weight (1 = 100%)", type: "decimal" },
          ]}
          create={() => ({ month: "", location: "", weight: "" })}
          onChange={(value) => patch("allocations", value)}
          addLabel="Add allocation"
        />
        <AllocationSummary
          totalFee={pricing.total_fee}
          allocations={pricing.allocations ?? []}
        />
      </div>
    );
  if (component.profile === "recurring_msp")
    return (
      <div className="space-y-4">
        <Select
          label="Proration"
          value={pricing.proration}
          options={["calendar_days", "full_month"]}
          onChange={(value) => patch("proration", value || null)}
        />
        <Field
          label="Included scope"
          value={pricing.included_scope}
          onChange={(value) => patch("included_scope", value || null)}
        />
        <Rows
          title="Recurring fees"
          rows={pricing.fees ?? []}
          columns={[
            {
              key: "location",
              label: "Fee location",
              options: ["US", "India"],
            },
            { key: "amount", label: "Monthly fee", type: "decimal" },
          ]}
          create={() => ({ location: "", amount: null })}
          onChange={(value) => patch("fees", value)}
          addLabel="Add monthly fee"
        />
        <MspAdjustmentsFields pricing={pricing} onChange={onChange} />
      </div>
    );
  if (component.profile === "milestone")
    return (
      <Rows<CommercialMilestone>
        title="Milestones"
        rows={pricing.milestones ?? []}
        onChange={(rows) => patch("milestones", rows)}
        addLabel="Add milestone"
        create={() => ({
          milestone_id: crypto.randomUUID(),
          planned_date: null,
          location: "",
          amount: null,
          acceptance_conditions: null,
          approved_invoice_ref: null,
          recognized_revenue_ref: null,
        })}
        columns={[
          { key: "planned_date", label: "Planned date", type: "date" },
          { key: "location", label: "Location", options: ["US", "India"] },
          { key: "amount", label: "Milestone amount", type: "decimal" },
          { key: "acceptance_conditions", label: "Acceptance conditions" },
          {
            key: "approved_invoice_ref",
            label: "Approved invoice",
            readonly: true,
          },
          {
            key: "recognized_revenue_ref",
            label: "Recognized revenue",
            readonly: true,
          },
        ]}
      />
    );
  if (!["unit", "tm"].includes(component.profile)) return null;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Unit rate"
          value={pricing.rate}
          type="decimal"
          onChange={(value) => patch("rate", value || null)}
        />
        {component.profile === "tm" ? (
          <Select
            label="Billing unit"
            value={pricing.unit}
            options={
              pricing.calendar_estimates
                ? ["hour"]
                : ["hour", "day", "week", "month", "unit"]
            }
            onChange={(value) => patch("unit", value)}
          />
        ) : (
          <Field
            label="Billing unit"
            value={pricing.unit}
            onChange={(value) => patch("unit", value)}
          />
        )}
      </div>
      {component.profile === "unit" ? (
        <>
          <Field
            label="Contractual quantity basis"
            value={pricing.contractual_basis}
            onChange={(value) => patch("contractual_basis", value || null)}
          />
          <Rows
            title="Contract quantities"
            rows={pricing.quantities ?? []}
            columns={columns("Quantity")}
            onChange={(rows) => patch("quantities", rows)}
            create={quantity}
            addLabel="Add quantity"
          />
        </>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Contract cap"
              value={pricing.cap}
              type="decimal"
              onChange={(value) => patch("cap", value || null)}
            />
            <Field
              label="Contract minimum"
              value={pricing.minimum}
              type="decimal"
              onChange={(value) => patch("minimum", value || null)}
            />
            <Field
              label="Limit allocation basis"
              value={pricing.limit_allocation_basis}
              onChange={(value) =>
                patch("limit_allocation_basis", value || null)
              }
            />
            <Field
              label="Currency minor unit"
              value={pricing.minor_unit}
              type="decimal"
              onChange={(value) => patch("minor_unit", value || null)}
            />
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={pricing.calendar_estimates ?? false}
              onChange={(e) => patch("calendar_estimates", e.target.checked)}
            />
            Calendar-derived estimates
          </label>
          <Rows
            title="Estimated quantities"
            rows={pricing.estimates ?? []}
            columns={columns("Estimated quantity")}
            onChange={(rows) => patch("estimates", rows)}
            create={quantity}
            addLabel="Add estimate"
          />
          <Rows
            title="Approved usage"
            rows={pricing.approved_usage ?? []}
            columns={columns("Approved quantity")}
            onChange={(rows) => patch("approved_usage", rows)}
            create={quantity}
            addLabel="Add approved usage"
          />
        </>
      )}
    </div>
  );
}

function AllocationSummary({
  totalFee,
  allocations,
}: {
  totalFee: string | null | undefined;
  allocations: { weight?: string | null }[];
}) {
  const weights = allocations.map((a) => Number(a.weight ?? 0));
  if (!weights.length || weights.some((w) => Number.isNaN(w))) return null;
  const sum = weights.reduce((a, b) => a + b, 0);
  const fee = Number(totalFee ?? 0);
  const ok = Math.abs(sum - 1) < 0.0005;
  return (
    <p
      data-testid="allocation-summary"
      className={ok ? "text-secondary text-text-secondary" : "text-danger"}
    >
      {allocations
        .map((a) => {
          const w = Number(a.weight ?? 0);
          const pct = (w * 100).toFixed(2).replace(/\.00$/, "");
          return fee > 0
            ? `${pct}% ≈ $${Math.round(w * fee).toLocaleString()}`
            : `${pct}%`;
        })
        .join(" · ")}
      {" — "}
      {ok
        ? "weights add to 100%."
        : `weights add to ${(sum * 100).toFixed(2)}% — they must total 100%.`}
    </p>
  );
}
