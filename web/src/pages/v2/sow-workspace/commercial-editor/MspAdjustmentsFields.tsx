import type {
  CommercialPricing,
  MspAdjustment,
  MspUsage,
} from "../../../../api/commercial";
import { Rows } from "./Fields";

export function MspAdjustmentsFields({
  pricing,
  onChange,
}: {
  pricing: CommercialPricing;
  onChange: (pricing: CommercialPricing) => void;
}) {
  return (
    <div className="space-y-4">
      <Rows<MspAdjustment>
        title="Contractual credits and overages"
        rows={pricing.adjustments ?? []}
        columns={[
          { key: "month", label: "Adjustment month", type: "date" },
          {
            key: "location",
            label: "Adjustment location",
            options: ["US", "India"],
          },
          {
            key: "kind",
            label: "Adjustment kind",
            options: ["credit", "overage"],
          },
          { key: "amount", label: "Adjustment amount", type: "decimal" },
        ]}
        create={() => ({
          source_id: crypto.randomUUID(),
          month: "",
          location: "",
          kind: "",
          amount: null,
        })}
        onChange={(adjustments) => onChange({ ...pricing, adjustments })}
        addLabel="Add credit or overage"
      />
      <Rows<MspUsage>
        title="Usage and included units"
        rows={pricing.usage ?? []}
        columns={[
          { key: "month", label: "Usage month", type: "date" },
          {
            key: "location",
            label: "Usage location",
            options: ["US", "India"],
          },
          { key: "unit", label: "Usage unit" },
          { key: "quantity", label: "Actual units", type: "decimal" },
          {
            key: "included_quantity",
            label: "Included units",
            type: "decimal",
          },
          { key: "unit_rate", label: "Overage unit rate", type: "decimal" },
        ]}
        create={() => ({
          source_id: crypto.randomUUID(),
          month: "",
          location: "",
          unit: "",
          quantity: null,
          included_quantity: null,
          unit_rate: null,
        })}
        onChange={(usage) => onChange({ ...pricing, usage })}
        addLabel="Add usage terms"
      />
    </div>
  );
}
