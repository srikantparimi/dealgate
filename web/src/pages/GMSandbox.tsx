/**
 * GM sandbox — M1 sign-off screen (S2-E4).
 *
 * Finance validates the six-template math here against their Excel before
 * Sales sees any GM UI. No business math lives in this file: every keystroke
 * debounces into `POST /gm/sandbox`, and the "Export to Excel" button just
 * hands the same payload to `POST /gm/sandbox/export`.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  computeGm,
  exportGmXlsx,
  getGmSchema,
  type EngagementType,
  type SandboxField,
  type SandboxRequest,
  type SandboxResponse,
  type SandboxSchema,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";

const ENGAGEMENTS: { value: EngagementType; label: string }[] = [
  { value: "fixed_price", label: "Fixed price" },
  { value: "staff_aug", label: "Staff augmentation" },
  { value: "single_resource", label: "Single resource" },
  { value: "assessment", label: "Assessment / discovery" },
  { value: "tm", label: "Time & materials" },
  { value: "managed_service", label: "Managed service" },
];

/** A row in the resources table. All fields are strings so the browser never
 *  coerces Decimals to floats. */
interface ResourceRow {
  role: string;
  seniority: string;
  location: "US" | "India";
  allocation_pct: string;
  start: string;
  end: string;
  hours_billable: string;
  hourly_bill_rate: string;
  hourly_cost: string;
}

function blankResource(location: "US" | "India" = "US"): ResourceRow {
  return {
    role: "",
    seniority: "",
    location,
    allocation_pct: "1",
    start: "2026-01-01",
    end: "2026-06-30",
    hours_billable: "0",
    hourly_bill_rate: "0",
    hourly_cost: "",
  };
}

/**
 * The §7 discounted worked example — US $90k/$65k, India $55k/$30k. Fills
 * the form so Finance can verify against the ratified test in one click.
 */
function sampleDiscountedInputs(): FormState {
  return {
    total_price: "145000",
    revenue_us: "90000",
    revenue_india: "55000",
    resources: [
      {
        role: "Engineer",
        seniority: "Sr",
        location: "US",
        allocation_pct: "1",
        start: "2026-01-01",
        end: "2026-06-30",
        hours_billable: "1000",
        hourly_bill_rate: "0",
        hourly_cost: "65",
      },
      {
        role: "Engineer",
        seniority: "Sr",
        location: "India",
        allocation_pct: "1",
        start: "2026-01-01",
        end: "2026-06-30",
        hours_billable: "600",
        hourly_bill_rate: "0",
        hourly_cost: "50",
      },
    ],
    scalars: {},
    deliverable: "",
    revenue_cap: "",
    monthly_fee_us: "",
    monthly_fee_india: "",
    term_months: "",
    replacement_obligation: false,
  };
}

interface FormState {
  total_price: string;
  revenue_us: string;
  revenue_india: string;
  resources: ResourceRow[];
  scalars: Record<string, string>;
  deliverable: string;
  revenue_cap: string;
  monthly_fee_us: string;
  monthly_fee_india: string;
  term_months: string;
  replacement_obligation: boolean;
}

function blankForm(): FormState {
  return {
    total_price: "",
    revenue_us: "",
    revenue_india: "",
    resources: [],
    scalars: {},
    deliverable: "",
    revenue_cap: "",
    monthly_fee_us: "",
    monthly_fee_india: "",
    term_months: "",
    replacement_obligation: false,
  };
}

/** Translate the FormState into the JSON payload the API expects. */
function toInputs(engagement: EngagementType, form: FormState): Record<string, unknown> {
  const resourceObjs = form.resources.map((r) => {
    const obj: Record<string, unknown> = {
      role: r.role,
      seniority: r.seniority,
      location: r.location,
      allocation_pct: r.allocation_pct || "1",
      start: r.start,
      end: r.end,
      hours_billable: r.hours_billable || "0",
      hourly_bill_rate: r.hourly_bill_rate || "0",
    };
    // Empty hourly_cost means "not yet supplied" — the API treats that as
    // missing (blueprint §2: never treat as zero).
    if (r.hourly_cost.trim() !== "") {
      obj.hourly_cost = r.hourly_cost;
    }
    return obj;
  });
  switch (engagement) {
    case "fixed_price":
      return {
        total_price: form.total_price || "0",
        revenue_us: form.revenue_us || "0",
        revenue_india: form.revenue_india || "0",
        resources: resourceObjs,
      };
    case "assessment":
      return {
        deliverable: form.deliverable,
        total_price: form.total_price || "0",
        revenue_us: form.revenue_us || "0",
        revenue_india: form.revenue_india || "0",
        resources: resourceObjs,
      };
    case "staff_aug":
      return {
        resources: resourceObjs,
        replacement_obligation: form.replacement_obligation,
      };
    case "single_resource":
      return { resource: resourceObjs[0] };
    case "tm":
      return {
        resources: resourceObjs,
        ...(form.revenue_cap.trim() !== ""
          ? { revenue_cap: form.revenue_cap }
          : {}),
      };
    case "managed_service":
      return {
        monthly_fee_us: form.monthly_fee_us || "0",
        monthly_fee_india: form.monthly_fee_india || "0",
        term_months: form.term_months || "0",
        resources: resourceObjs,
      };
  }
}

// --- formatting helpers ----------------------------------------------------

function fmtPct(v: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${(n * 100).toFixed(2)}%`;
}

function fmtMoney(v: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function passTone(present: boolean, pass: boolean, complete: boolean): "ok" | "block" | "neutral" {
  if (!present) return "neutral";
  if (!complete) return "neutral";
  return pass ? "ok" : "block";
}

// --- the page --------------------------------------------------------------

export function GMSandboxPage() {
  const [engagement, setEngagement] = useState<EngagementType>("fixed_price");
  const [schema, setSchema] = useState<SandboxSchema | null>(null);
  const [form, setForm] = useState<FormState>(blankForm);
  const [result, setResult] = useState<SandboxResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    getGmSchema(engagement)
      .then((s) => {
        if (!cancelled) setSchema(s);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [engagement]);

  // Debounced live-compute. Rebuild the payload on every state change and
  // POST once the user pauses for 250ms. The API is the only source of
  // truth for GM numbers.
  useEffect(() => {
    if (debounceRef.current !== undefined) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      const req: SandboxRequest = {
        engagement_type: engagement,
        inputs: toInputs(engagement, form),
      };
      setPending(true);
      setError(null);
      computeGm(req)
        .then((res) => {
          setResult(res);
        })
        .catch((err) => {
          setError(err);
        })
        .finally(() => setPending(false));
    }, 250);
    return () => {
      if (debounceRef.current !== undefined) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [engagement, form]);

  const onSample = useCallback(() => {
    setEngagement("fixed_price");
    setForm(sampleDiscountedInputs());
  }, []);

  const onReset = useCallback(() => {
    setForm(blankForm());
    setResult(null);
    setError(null);
  }, []);

  const onExport = useCallback(async () => {
    setExportError(null);
    setExporting(true);
    try {
      const blob = await exportGmXlsx({
        engagement_type: engagement,
        inputs: toInputs(engagement, form),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gm_sandbox_${engagement}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err);
    } finally {
      setExporting(false);
    }
  }, [engagement, form]);

  const schemaFieldNames = useMemo(
    () => new Set(schema?.fields.map((f) => f.name) ?? []),
    [schema],
  );

  return (
    <div>
      <PageHeader
        title="GM sandbox"
        subtitle="M1 sign-off screen — Finance validates the six-template math against Excel before Sales sees any GM UI."
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={onSample} data-testid="sample-btn" style={btnGhost}>
              Sample: §7 worked example
            </button>
            <button type="button" onClick={onReset} data-testid="reset-btn" style={btnGhost}>
              Reset
            </button>
            <button
              type="button"
              onClick={onExport}
              disabled={exporting || result === null}
              data-testid="export-btn"
              style={btnPrimary}
            >
              {exporting ? "Exporting…" : "Export to Excel"}
            </button>
          </div>
        }
      />
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 24 }}>
        <section aria-label="Inputs">
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>
              Engagement type
              <select
                value={engagement}
                aria-label="Engagement type"
                onChange={(e) => {
                  setEngagement(e.target.value as EngagementType);
                  setForm(blankForm());
                }}
                style={inputStyle}
              >
                {ENGAGEMENTS.map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {schema ? (
            <TemplateFields
              engagement={engagement}
              schema={schema}
              form={form}
              onChange={setForm}
            />
          ) : (
            <EmptyState title="Loading schema" hint="Fetching template fields." />
          )}
          {exportError ? (
            <div style={{ marginTop: 12 }}>
              <ErrorState error={exportError} />
            </div>
          ) : null}
          <div style={{ marginTop: 8, fontSize: 12, color: "#6b7280" }} data-testid="field-count">
            {schemaFieldNames.size} template fields
          </div>
        </section>

        <aside aria-label="Live result">
          <ResultPanel result={result} error={error} pending={pending} />
        </aside>
      </div>
    </div>
  );
}

// --- Template-specific form -----------------------------------------------

function TemplateFields({
  engagement,
  schema,
  form,
  onChange,
}: {
  engagement: EngagementType;
  schema: SandboxSchema;
  form: FormState;
  onChange: (next: FormState) => void;
}) {
  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    onChange({ ...form, [key]: value });
  };
  const fieldByName = new Map(schema.fields.map((f) => [f.name, f]));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {fieldByName.has("deliverable") ? (
        <TextField
          label={fieldByName.get("deliverable")!}
          value={form.deliverable}
          onChange={(v) => setField("deliverable", v)}
        />
      ) : null}

      {fieldByName.has("total_price") ? (
        <MoneyField
          label={fieldByName.get("total_price")!}
          value={form.total_price}
          onChange={(v) => setField("total_price", v)}
          testId="input-total_price"
        />
      ) : null}
      {fieldByName.has("revenue_us") ? (
        <MoneyField
          label={fieldByName.get("revenue_us")!}
          value={form.revenue_us}
          onChange={(v) => setField("revenue_us", v)}
          testId="input-revenue_us"
        />
      ) : null}
      {fieldByName.has("revenue_india") ? (
        <MoneyField
          label={fieldByName.get("revenue_india")!}
          value={form.revenue_india}
          onChange={(v) => setField("revenue_india", v)}
          testId="input-revenue_india"
        />
      ) : null}
      {fieldByName.has("monthly_fee_us") ? (
        <MoneyField
          label={fieldByName.get("monthly_fee_us")!}
          value={form.monthly_fee_us}
          onChange={(v) => setField("monthly_fee_us", v)}
          testId="input-monthly_fee_us"
        />
      ) : null}
      {fieldByName.has("monthly_fee_india") ? (
        <MoneyField
          label={fieldByName.get("monthly_fee_india")!}
          value={form.monthly_fee_india}
          onChange={(v) => setField("monthly_fee_india", v)}
          testId="input-monthly_fee_india"
        />
      ) : null}
      {fieldByName.has("term_months") ? (
        <MoneyField
          label={fieldByName.get("term_months")!}
          value={form.term_months}
          onChange={(v) => setField("term_months", v)}
          testId="input-term_months"
        />
      ) : null}
      {fieldByName.has("revenue_cap") ? (
        <MoneyField
          label={fieldByName.get("revenue_cap")!}
          value={form.revenue_cap}
          onChange={(v) => setField("revenue_cap", v)}
          testId="input-revenue_cap"
        />
      ) : null}
      {fieldByName.has("replacement_obligation") ? (
        <BoolField
          label={fieldByName.get("replacement_obligation")!}
          value={form.replacement_obligation}
          onChange={(v) => setField("replacement_obligation", v)}
        />
      ) : null}

      {fieldByName.has("resources") || fieldByName.has("resource") ? (
        <ResourceTable
          singleOnly={engagement === "single_resource"}
          rows={form.resources}
          onChange={(rows) => setField("resources", rows)}
        />
      ) : null}
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: SandboxField;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label style={labelStyle}>
      {label.label}
      <input
        type="text"
        value={value}
        aria-label={label.label}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        style={inputStyle}
      />
    </label>
  );
}

function MoneyField({
  label,
  value,
  onChange,
  testId,
}: {
  label: SandboxField;
  value: string;
  onChange: (v: string) => void;
  testId?: string;
}) {
  return (
    <label style={labelStyle}>
      {label.label}
      <input
        type="text"
        inputMode="decimal"
        value={value}
        aria-label={label.label}
        data-testid={testId}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        style={inputStyle}
      />
      {label.help ? <span style={helpStyle}>{label.help}</span> : null}
    </label>
  );
}

function BoolField({
  label,
  value,
  onChange,
}: {
  label: SandboxField;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: 8 }}>
      <input
        type="checkbox"
        checked={value}
        aria-label={label.label}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
      />
      <span>{label.label}</span>
    </label>
  );
}

function ResourceTable({
  singleOnly,
  rows,
  onChange,
}: {
  singleOnly: boolean;
  rows: ResourceRow[];
  onChange: (rows: ResourceRow[]) => void;
}) {
  const patch = (i: number, delta: Partial<ResourceRow>) => {
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...delta } : r)));
  };
  const remove = (i: number) => onChange(rows.filter((_, idx) => idx !== i));
  const add = (loc: "US" | "India") => {
    if (singleOnly) {
      onChange([blankResource(loc)]);
    } else {
      onChange([...rows, blankResource(loc)]);
    }
  };
  return (
    <fieldset style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: 12 }}>
      <legend style={{ padding: "0 6px", fontSize: 13, color: "#374151" }}>
        {singleOnly ? "Resource" : "Resources"}
      </legend>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f9fafb", textAlign: "left" }}>
            <th style={cellStyle}>Role</th>
            <th style={cellStyle}>Seniority</th>
            <th style={cellStyle}>Location</th>
            <th style={cellStyle}>Hours</th>
            <th style={cellStyle}>Bill $/h</th>
            <th style={cellStyle}>Cost $/h</th>
            <th style={cellStyle}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} data-testid={`resource-row-${i}`}>
              <td style={cellStyle}>
                <input
                  aria-label={`role ${i}`}
                  value={r.role}
                  onChange={(e) => patch(i, { role: e.target.value })}
                  style={cellInput}
                />
              </td>
              <td style={cellStyle}>
                <input
                  aria-label={`seniority ${i}`}
                  value={r.seniority}
                  onChange={(e) => patch(i, { seniority: e.target.value })}
                  style={cellInput}
                />
              </td>
              <td style={cellStyle}>
                <select
                  aria-label={`location ${i}`}
                  value={r.location}
                  onChange={(e) =>
                    patch(i, { location: e.target.value as "US" | "India" })
                  }
                  style={cellInput}
                >
                  <option value="US">US</option>
                  <option value="India">India</option>
                </select>
              </td>
              <td style={cellStyle}>
                <input
                  aria-label={`hours ${i}`}
                  value={r.hours_billable}
                  onChange={(e) => patch(i, { hours_billable: e.target.value })}
                  style={cellInput}
                />
              </td>
              <td style={cellStyle}>
                <input
                  aria-label={`bill ${i}`}
                  value={r.hourly_bill_rate}
                  onChange={(e) => patch(i, { hourly_bill_rate: e.target.value })}
                  style={cellInput}
                />
              </td>
              <td style={cellStyle}>
                <input
                  aria-label={`cost ${i}`}
                  value={r.hourly_cost}
                  onChange={(e) => patch(i, { hourly_cost: e.target.value })}
                  style={cellInput}
                />
              </td>
              <td style={cellStyle}>
                <button
                  type="button"
                  aria-label={`remove row ${i}`}
                  onClick={() => remove(i)}
                  style={{
                    color: "#991b1b",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" onClick={() => add("US")} style={btnGhost}>
          + Add US
        </button>
        <button type="button" onClick={() => add("India")} style={btnGhost}>
          + Add India
        </button>
      </div>
    </fieldset>
  );
}

// --- result panel ----------------------------------------------------------

function ResultPanel({
  result,
  error,
  pending,
}: {
  result: SandboxResponse | null;
  error: unknown;
  pending: boolean;
}) {
  if (error) return <ErrorState error={error} />;
  if (!result) {
    return (
      <EmptyState
        title={pending ? "Computing…" : "Live result"}
        hint="Fill in the inputs to see US / India / blended GM."
      />
    );
  }
  const usPresent = Number(result.revenue_us) > 0;
  const indiaPresent = Number(result.revenue_india) > 0;
  return (
    <div
      data-testid="result-panel"
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <strong>Live result</strong>
        {pending ? (
          <span style={{ fontSize: 12, color: "#6b7280" }}>Recomputing…</span>
        ) : (
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {result.geography} · {result.policy.source}
          </span>
        )}
      </div>

      <ComponentRow
        label="US"
        revenue={result.revenue_us}
        cost={result.cost_us}
        gm={result.gm_us}
        minPrice={result.min_price_us}
        present={usPresent}
        floor={result.policy.us_floor}
        pass={result.policy.us_pass}
        complete={result.complete}
      />
      <ComponentRow
        label="India"
        revenue={result.revenue_india}
        cost={result.cost_india}
        gm={result.gm_india}
        minPrice={result.min_price_india}
        present={indiaPresent}
        floor={result.policy.india_floor}
        pass={result.policy.india_pass}
        complete={result.complete}
      />

      <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 8 }}>
        <div style={{ fontSize: 12, color: "#6b7280" }}>Blended GM (informational)</div>
        <div data-testid="gm-blended" style={{ fontSize: 24, fontWeight: 700 }}>
          {fmtPct(result.gm_blended)}
        </div>
      </div>

      {!result.complete ? (
        <div
          data-testid="incomplete-banner"
          style={{ background: "#fef3c7", padding: 8, borderRadius: 6, fontSize: 12 }}
        >
          <strong>Incomplete inputs.</strong> Missing:{" "}
          {result.missing.map((m) => (
            <code key={m} style={{ marginRight: 6 }}>
              {m}
            </code>
          ))}
        </div>
      ) : null}

      {result.policy.requires_ceo ? (
        <div data-testid="ceo-required">
          <StatusChip tone="block">CEO approval required</StatusChip>
        </div>
      ) : null}
    </div>
  );
}

function ComponentRow({
  label,
  revenue,
  cost,
  gm,
  minPrice,
  present,
  floor,
  pass,
  complete,
}: {
  label: "US" | "India";
  revenue: string;
  cost: string;
  gm: string | null;
  minPrice: string | null;
  present: boolean;
  floor: string;
  pass: boolean;
  complete: boolean;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <StatusChip tone={passTone(present, pass, complete)}>
          {!present
            ? "not present"
            : !complete
              ? "N/A"
              : pass
                ? `pass ≥ ${fmtPct(floor)}`
                : `fail < ${fmtPct(floor)}`}
        </StatusChip>
      </div>
      <div
        data-testid={`gm-${label.toLowerCase()}`}
        style={{ fontSize: 28, fontWeight: 700 }}
      >
        {fmtPct(gm)}
      </div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>
        Revenue {fmtMoney(revenue)} · Cost {fmtMoney(cost)}
        {minPrice ? <> · Min price {fmtMoney(minPrice)}</> : null}
      </div>
    </div>
  );
}

// --- styles ---------------------------------------------------------------

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  padding: 6,
  border: "1px solid #e5e7eb",
  borderRadius: 4,
  fontSize: 13,
};

const helpStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
};

const cellStyle: React.CSSProperties = {
  padding: "4px 6px",
  borderBottom: "1px solid #f3f4f6",
};

const cellInput: React.CSSProperties = {
  width: "100%",
  padding: 4,
  border: "1px solid #e5e7eb",
  borderRadius: 3,
  fontSize: 12,
};

const btnGhost: React.CSSProperties = {
  padding: "6px 12px",
  border: "1px solid #e5e7eb",
  background: "white",
  color: "#111827",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
};

const btnPrimary: React.CSSProperties = {
  padding: "6px 12px",
  border: "none",
  background: "#111827",
  color: "white",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
};
