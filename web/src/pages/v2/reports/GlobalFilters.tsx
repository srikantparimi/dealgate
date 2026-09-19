/**
 * Global filters row shared across the five Reports tabs (spec §17).
 * Purely presentational — the parent owns state so filter changes can
 * re-fetch each report on its own cadence.
 */

import { Input } from "../../../ui-v2/primitives/input";

export interface GlobalFilterValues {
  period: string;
  businessUnit: string;
  geography: string;
  client: string;
  accountOwner: string;
  engagement: string;
  currency: string;
}

export interface GlobalFiltersProps {
  values: GlobalFilterValues;
  onChange: (patch: Partial<GlobalFilterValues>) => void;
}

export function emptyGlobalFilters(): GlobalFilterValues {
  return {
    period: "",
    businessUnit: "",
    geography: "",
    client: "",
    accountOwner: "",
    engagement: "",
    currency: "USD",
  };
}

export function GlobalFilters({ values, onChange }: GlobalFiltersProps) {
  return (
    <div
      className="grid grid-cols-2 gap-3 rounded-panel border border-divider bg-surface p-3 sm:grid-cols-4"
      aria-label="Global report filters"
    >
      <Field label="Period" value={values.period}>
        <Input
          id="rep-period"
          value={values.period}
          onChange={(e) => onChange({ period: e.target.value })}
          placeholder="e.g. 2026-Q3"
        />
      </Field>
      <Field label="Business unit" value={values.businessUnit}>
        <Input
          id="rep-bu"
          value={values.businessUnit}
          onChange={(e) => onChange({ businessUnit: e.target.value })}
          placeholder="Any"
        />
      </Field>
      <Field label="Geography" value={values.geography}>
        <select
          id="rep-geo"
          value={values.geography}
          onChange={(e) => onChange({ geography: e.target.value })}
          className="mt-1 h-10 w-full rounded-control border border-input-border bg-surface px-2 text-body text-text focus-visible:outline-focus"
        >
          <option value="">Any</option>
          <option value="US">US</option>
          <option value="India">India</option>
          <option value="Mixed">Mixed</option>
        </select>
      </Field>
      <Field label="Client" value={values.client}>
        <Input
          id="rep-client"
          value={values.client}
          onChange={(e) => onChange({ client: e.target.value })}
          placeholder="Any"
        />
      </Field>
      <Field label="Account owner" value={values.accountOwner}>
        <Input
          id="rep-owner"
          value={values.accountOwner}
          onChange={(e) => onChange({ accountOwner: e.target.value })}
          placeholder="Any"
        />
      </Field>
      <Field label="Engagement" value={values.engagement}>
        <Input
          id="rep-eng"
          value={values.engagement}
          onChange={(e) => onChange({ engagement: e.target.value })}
          placeholder="Any"
        />
      </Field>
      <Field label="Currency" value={values.currency}>
        <select
          id="rep-ccy"
          value={values.currency}
          onChange={(e) => onChange({ currency: e.target.value })}
          className="mt-1 h-10 w-full rounded-control border border-input-border bg-surface px-2 text-body text-text focus-visible:outline-focus"
        >
          <option value="USD">USD</option>
          <option value="INR">INR</option>
        </select>
      </Field>
    </div>
  );
}

function Field({
  label,
  value: _value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col text-secondary text-text-secondary">
      <span className="uppercase tracking-wide">{label}</span>
      {children}
    </label>
  );
}
