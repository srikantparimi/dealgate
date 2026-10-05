import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type {
  CommercialComponent,
  PeriodCost,
} from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { CalendarFields } from "./CalendarFields";
import { Field, Rows, Select } from "./Fields";
import { emptyPricing, PricingFields, PROFILE_LABELS } from "./PricingFields";

export function HybridFields({
  component,
  onChange,
}: {
  component: CommercialComponent;
  onChange: (value: CommercialComponent) => void;
}) {
  const [newProfile, setNewProfile] = useState("fixed_assignment");
  const [pending, setPending] = useState<{
    componentId: string;
    profile: string;
  } | null>(null);
  const pricing = component.pricing ?? {};
  const children = pricing.components ?? [];
  const patch = (key: string, value: unknown) =>
    onChange({ ...component, pricing: { ...pricing, [key]: value } });
  const childChange = (index: number, value: CommercialComponent) =>
    patch(
      "components",
      children.map((child, i) => (i === index ? value : child)),
    );
  const profileOptions = Object.entries(PROFILE_LABELS)
    .filter(([key]) => key !== "hybrid")
    .map(([value, label]) => ({ value, label }));
  const sourceOptions = [
    ...component.costs.map((cost) => ({
      value: cost.source_id,
      label: `${cost.month} / ${cost.location} / ${cost.amount ?? "Unconfirmed"}`,
    })),
    ...component.staffing.map((row) => ({
      value: `calendar:${row.assignment_id}`,
      label: `${row.role || "Staffing"} / calendar cost`,
    })),
  ];
  return (
    <div className="space-y-5">
      {children.map((child, index) => (
        <section
          key={child.component_id}
          aria-label={`Component ${index + 1}`}
          className="space-y-4 border-y border-divider py-4"
        >
          <header className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-medium">
              {child.workstream_id || `Component ${index + 1}`}
            </h3>
            <Button
              variant="ghost"
              size="icon"
              title="Remove component from draft"
              aria-label={`Remove component ${index + 1}`}
              onClick={() => {
                if (pending?.componentId === child.component_id)
                  setPending(null);
                patch(
                  "components",
                  children.filter((_, i) => i !== index),
                );
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </header>
          <Select
            label="Component pricing profile"
            value={child.profile}
            options={profileOptions}
            onChange={(profile) => {
              if (profile)
                setPending({ componentId: child.component_id, profile });
            }}
          />
          {pending?.componentId === child.component_id && (
            <div className="space-y-2 border-l-4 border-warning p-3">
              <p>
                Replace this component's pricing rows? Its evidence, costs and
                staffing are retained.
              </p>
              <Button variant="secondary" onClick={() => setPending(null)}>
                Keep component model
              </Button>
              <Button
                onClick={() => {
                  childChange(index, {
                    ...child,
                    profile: pending.profile,
                    pricing: emptyPricing(pending.profile),
                  });
                  setPending(null);
                }}
              >
                Replace component pricing
              </Button>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(
              [
                ["workstream_id", "Component workstream"],
                ["service_start", "Component start"],
                ["service_end", "Component end"],
                ["currency", "Component currency"],
                ["timezone", "Component timezone"],
                ["billing_cadence", "Component billing cadence"],
                ["cost_basis", "Component cost basis"],
              ] as const
            ).map(([key, label]) => (
              <Field
                key={key}
                label={label}
                value={child[key]}
                type={
                  key === "service_start" || key === "service_end"
                    ? "date"
                    : "text"
                }
                onChange={(value) =>
                  childChange(index, { ...child, [key]: value || null })
                }
              />
            ))}
          </div>
          <label className="block text-secondary">
            Component source evidence
            <textarea
              className="mt-1 min-h-20 w-full rounded-md border border-divider bg-surface p-3"
              value={child.source_evidence.join("\n")}
              onChange={(e) =>
                childChange(index, {
                  ...child,
                  source_evidence: e.target.value.split("\n"),
                })
              }
            />
          </label>
          {child.profile === "hybrid" ? (
            <p className="text-warning">
              Nested hybrid requires a confirmed flattened component plan.
            </p>
          ) : (
            <PricingFields
              component={child}
              onChange={(value) =>
                childChange(index, { ...child, pricing: value })
              }
            />
          )}
          {(child.profile === "calendar_staff_aug" ||
            child.profile === "fixed_assignment" ||
            child.profile === "recurring_msp" ||
            child.pricing?.calendar_estimates ||
            child.staffing.length > 0) && (
            <CalendarFields
              component={child}
              onChange={(value) => childChange(index, value)}
            />
          )}
          <Rows<PeriodCost>
            title="Component period costs"
            rows={child.costs}
            columns={[
              { key: "month", label: "Cost month", type: "date" },
              {
                key: "location",
                label: "Cost location",
                options: ["US", "India"],
              },
              { key: "amount", label: "Loaded cost", type: "decimal" },
            ]}
            create={() => ({
              source_id: crypto.randomUUID(),
              month: "",
              location: "",
              amount: null,
            })}
            onChange={(value) => childChange(index, { ...child, costs: value })}
            addLabel="Add component cost"
          />
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={child.costs_confirmed}
              onChange={(e) =>
                childChange(index, {
                  ...child,
                  costs_confirmed: e.target.checked,
                })
              }
            />
            Component costs confirmed
          </label>
        </section>
      ))}
      <div className="flex flex-wrap items-end gap-3">
        <Select
          label="New component model"
          value={newProfile}
          options={profileOptions}
          onChange={setNewProfile}
        />
        <Button
          variant="secondary"
          disabled={!newProfile}
          onClick={() =>
            patch("components", [
              ...children,
              {
                ...component,
                component_id: crypto.randomUUID(),
                workstream_id: "",
                version: "1",
                profile: newProfile,
                profile_version: "1",
                pricing: emptyPricing(newProfile),
                costs: [],
                staffing: [],
                costs_confirmed: false,
              },
            ])
          }
        >
          <Plus className="h-4 w-4" />
          Add component
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Shared cost allocation basis"
          value={pricing.allocation_basis}
          onChange={(value) => patch("allocation_basis", value || null)}
        />
        <Field
          label="Shared cost minor unit"
          type="decimal"
          value={pricing.minor_unit}
          onChange={(value) => patch("minor_unit", value || null)}
        />
      </div>
      <Rows
        title="Shared cost allocations"
        rows={pricing.shared_cost_allocations ?? []}
        columns={[
          {
            key: "source_id",
            label: "Shared cost source",
            options: sourceOptions,
          },
          {
            key: "component_id",
            label: "Allocated component",
            options: children.map((child, index) => ({
              value: child.component_id,
              label: child.workstream_id || `Component ${index + 1}`,
            })),
          },
          { key: "weight", label: "Shared cost weight", type: "decimal" },
        ]}
        create={() => ({ source_id: "", component_id: "", weight: "" })}
        onChange={(value) => patch("shared_cost_allocations", value)}
        addLabel="Add shared cost allocation"
      />
      <Rows
        title="Reporting FX"
        rows={pricing.fx_rates ?? []}
        columns={[
          { key: "currency", label: "Source currency" },
          { key: "rate", label: "FX rate", type: "decimal" },
          { key: "version", label: "FX source version" },
          { key: "as_of", label: "FX date", type: "date" },
        ]}
        create={() => ({
          currency: "",
          rate: null,
          version: null,
          as_of: null,
        })}
        onChange={(value) => patch("fx_rates", value)}
        addLabel="Add currency conversion"
      />
    </div>
  );
}
