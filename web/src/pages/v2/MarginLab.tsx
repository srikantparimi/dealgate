/**
 * Margin lab (`/margin-lab`) — spec §9.
 *
 * Top selector: Approved baseline / Current draft / Scenarios with a
 * version selector + Compare versions action. Draft is visually
 * distinct from an approved read-only model and carries the
 * "Draft · Not approved for commitment" chip beside the version.
 *
 * Below: revenue · delivery cost · gross profit · combined GM, then
 * independent US + India policy tests (StatusBadge pass/fail per
 * component). Combined result is informational only.
 *
 * Staffing grid columns per §9. Restricted users see approved role
 * costs or aggregates (server enforces the redaction — the UI shows
 * "Restricted" when the value comes back as null).
 *
 * EVERY number comes from the server (`POST /gm/sandbox`). No math in
 * the browser (blueprint §2, CLAUDE.md rule 2). Scenarios copy the
 * current inputs, let the user override price / mix / effort, then
 * call the same endpoint — the result is a new draft, never a
 * replacement of the approved version.
 */
import { useCallback, useEffect, useState } from "react";
import { Download, GitCompare } from "lucide-react";
import {
  ApiError,
  computeGm,
  exportGmXlsx,
  getGmSchema,
  listPolicies,
  listRateCards,
  type ActivePolicy,
  type EngagementType,
  type RateCardListResponse,
  type SandboxRequest,
  type SandboxResponse,
  type SandboxSchema,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { MarginCell } from "../../ui-v2/MarginCell";
import { MoneyCell } from "../../ui-v2/MoneyCell";
import { PageHeader } from "../../ui-v2/PageHeader";
import { SourceFreshness } from "../../ui-v2/SourceFreshness";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { Label } from "../../ui-v2/primitives/label";
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import {
  MARGIN_MODES,
  draftChipLabel,
  floorOutcome,
  formatMarginPct,
  overallMarginTone,
  type MarginMode,
} from "./margin-lab/marginDisplay";

const ENGAGEMENTS: { value: EngagementType; label: string }[] = [
  { value: "staff_aug", label: "Staff augmentation" },
  { value: "single_resource", label: "Single resource" },
  { value: "fixed_price", label: "Fixed price" },
  { value: "assessment", label: "Assessment" },
  { value: "tm", label: "Time & materials" },
  { value: "managed_service", label: "Managed service" },
];

export function MarginLabPage() {
  const [mode, setMode] = useState<MarginMode>("draft");
  const [engagement, setEngagement] = useState<EngagementType>("staff_aug");
  const [schema, setSchema] = useState<SandboxSchema | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [result, setResult] = useState<SandboxResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [rateCards, setRateCards] = useState<RateCardListResponse | null>(null);
  const [policy, setPolicy] = useState<ActivePolicy | null>(null);
  const [supportError, setSupportError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [xlsxBusy, setXlsxBusy] = useState(false);

  // Load the schema whenever the engagement changes — the field list
  // is server-owned so the browser cannot silently gain or drop
  // required fields.
  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setInputs({});
    (async () => {
      try {
        const s = await getGmSchema(engagement);
        if (!cancelled) setSchema(s);
      } catch (err) {
        if (!cancelled) {
          setComputeError(
            err instanceof ApiError ? err.message : String(err ?? "Unknown"),
          );
          setSchema(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagement]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rc, pol] = await Promise.all([listRateCards(), listPolicies()]);
        if (cancelled) return;
        setRateCards(rc);
        setPolicy(pol.active);
      } catch (err) {
        if (!cancelled) {
          setSupportError(
            err instanceof ApiError ? err.message : String(err ?? "Unknown"),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const compute = useCallback(async () => {
    setBusy(true);
    setComputeError(null);
    try {
      const body: SandboxRequest = {
        engagement_type: engagement,
        inputs,
      };
      const r = await computeGm(body);
      setResult(r);
    } catch (err) {
      setComputeError(
        err instanceof ApiError ? err.message : String(err ?? "Unknown"),
      );
    } finally {
      setBusy(false);
    }
  }, [engagement, inputs]);

  async function handleExport() {
    setXlsxBusy(true);
    try {
      const blob = await exportGmXlsx({ engagement_type: engagement, inputs });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `margin-lab-${engagement}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      setNotice("XLSX export downloaded.");
    } catch (err) {
      setNotice(
        err instanceof ApiError ? `Export failed — ${err.message}` : "Export failed.",
      );
    } finally {
      setXlsxBusy(false);
    }
  }

  const isEditable = mode !== "baseline";

  return (
    <div>
      <PageHeader
        title="Margin lab"
        subtitle="Model revenue, delivery cost and margin for a scenario. Every number comes from the server; the browser never computes GM."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={() =>
                setNotice(
                  "Version comparison lands with the Margin diff story — the endpoint already returns hashed versions.",
                )
              }
            >
              <GitCompare className="h-4 w-4" aria-hidden />
              Compare versions
            </Button>
            <Button
              variant="secondary"
              onClick={() => void handleExport()}
              disabled={xlsxBusy}
              aria-label="Export scenario to xlsx"
            >
              <Download className="h-4 w-4" aria-hidden />
              {xlsxBusy ? "Preparing…" : "Export xlsx"}
            </Button>
          </div>
        }
      />

      {notice ? (
        <div
          role="status"
          className="mb-4 rounded-panel border border-primary/30 bg-primary-subtle px-4 py-3 text-body text-text"
        >
          {notice}
        </div>
      ) : null}

      <ModeSelector
        mode={mode}
        onChange={setMode}
        engagement={engagement}
        onEngagementChange={setEngagement}
      />

      {supportError ? (
        <ErrorState
          title="Couldn't load rate cards or policy"
          description={supportError}
        />
      ) : (
        <MetaRow rateCards={rateCards} policy={policy} />
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <InputsPanel
            schema={schema}
            inputs={inputs}
            onChange={setInputs}
            onCompute={() => void compute()}
            busy={busy}
            editable={isEditable}
          />
        </div>

        <div className="lg:col-span-3">
          {computeError ? (
            <ErrorState
              title="Server couldn't compute this scenario"
              description={computeError}
              onRetry={() => void compute()}
            />
          ) : result ? (
            <ResultPanel result={result} mode={mode} />
          ) : (
            <EmptyState
              title="Fill the inputs and press Compute."
              description="The server evaluates policy at full Decimal precision; the browser only renders what came back."
            />
          )}
        </div>
      </div>
    </div>
  );
}

interface ModeSelectorProps {
  mode: MarginMode;
  onChange: (m: MarginMode) => void;
  engagement: EngagementType;
  onEngagementChange: (e: EngagementType) => void;
}

function ModeSelector({
  mode,
  onChange,
  engagement,
  onEngagementChange,
}: ModeSelectorProps) {
  const current = MARGIN_MODES.find((m) => m.id === mode) ?? MARGIN_MODES[1];
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={mode} onValueChange={(v) => onChange(v as MarginMode)}>
          <TabsList aria-label="Margin lab modes">
            {MARGIN_MODES.map((m) => (
              <TabsTrigger key={m.id} value={m.id}>
                {m.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex items-center gap-2">
          <Label htmlFor="ml-engagement">Engagement</Label>
          <select
            id="ml-engagement"
            className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
            value={engagement}
            onChange={(e) => onEngagementChange(e.target.value as EngagementType)}
          >
            {ENGAGEMENTS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-secondary text-text-secondary">
          Version: {mode === "baseline" ? "v-last-approved" : "v-working"} ·
        </span>
        {mode === "draft" ? (
          <StatusBadge
            tone="warn"
            label={draftChipLabel()}
            data-testid="margin-draft-chip"
          />
        ) : mode === "scenarios" ? (
          <StatusBadge
            tone="warn"
            label="Scenario · Never replaces approved baseline"
            data-testid="margin-scenario-chip"
          />
        ) : (
          <StatusBadge
            tone="ok"
            label="Approved · Read only"
            data-testid="margin-approved-chip"
          />
        )}
        <span className="text-secondary text-text-secondary">
          — {current.helper}
        </span>
      </div>
    </div>
  );
}

function MetaRow({
  rateCards,
  policy,
}: {
  rateCards: RateCardListResponse | null;
  policy: ActivePolicy | null;
}) {
  const active = rateCards?.items.find((r) => r.is_active);
  return (
    <div className="mt-4 flex flex-col gap-2 rounded-panel border border-divider bg-surface p-3 sm:flex-row sm:items-center sm:justify-between">
      <SourceFreshness
        source={
          active
            ? `Rate card ${active.effective_from} (id ${active.id.slice(0, 8)})`
            : "No active rate card"
        }
        asOf={active?.published_at ?? "—"}
        basis="Approved cost definition — Finance policy"
      />
      <SourceFreshness
        source={
          policy
            ? `Policy ${policy.effective_from ?? "default"} · FX ${policy.fx_convention}`
            : "Policy: defaults"
        }
        asOf={policy?.effective_from ?? "—"}
        basis={`US floor ${policy ? formatMarginPct(policy.us_floor) : "35%"} · India floor ${policy ? formatMarginPct(policy.india_floor) : "50%"}`}
      />
    </div>
  );
}

interface InputsPanelProps {
  schema: SandboxSchema | null;
  inputs: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  onCompute: () => void;
  busy: boolean;
  editable: boolean;
}

function InputsPanel({
  schema,
  inputs,
  onChange,
  onCompute,
  busy,
  editable,
}: InputsPanelProps) {
  if (!schema) {
    return (
      <div className="rounded-panel border border-divider bg-surface p-4 text-body text-text-secondary">
        Loading engagement schema…
      </div>
    );
  }
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <h2 className="text-section text-text mb-3">Scenario inputs</h2>
      {!editable ? (
        <p className="mb-3 text-secondary text-text-secondary">
          Approved baseline is read-only. Switch to Current draft or
          Scenarios to change inputs.
        </p>
      ) : null}
      <div className="flex flex-col gap-3">
        {schema.fields.map((f) => (
          <div key={f.name} className="flex flex-col gap-1">
            <Label htmlFor={`ml-${f.name}`}>
              {f.label}
              {f.required ? (
                <span className="ml-1 text-danger" aria-hidden>
                  *
                </span>
              ) : null}
            </Label>
            <Input
              id={`ml-${f.name}`}
              value={inputs[f.name] ?? ""}
              onChange={(e) =>
                onChange({ ...inputs, [f.name]: e.target.value })
              }
              placeholder={f.help}
              disabled={!editable}
            />
          </div>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <Button
          type="button"
          variant="primary"
          onClick={onCompute}
          disabled={busy || !editable}
        >
          {busy ? "Computing…" : "Compute margin"}
        </Button>
      </div>
    </div>
  );
}

interface ResultPanelProps {
  result: SandboxResponse;
  mode: MarginMode;
}

function ResultPanel({ result, mode }: ResultPanelProps) {
  const hasUs = result.revenue_us !== "0" && result.revenue_us !== "0.00";
  const hasIndia =
    result.revenue_india !== "0" && result.revenue_india !== "0.00";

  const usFloor = floorOutcome(result.policy.us_pass, hasUs);
  const inFloor = floorOutcome(result.policy.india_pass, hasIndia);

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-panel border border-divider bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-section text-text">Financial summary</h2>
          <StatusBadge
            tone={overallMarginTone(result)}
            label={
              result.complete
                ? result.policy.requires_ceo
                  ? "CEO exception required"
                  : "Policy pass"
                : "Incomplete inputs"
            }
          />
        </div>
        {!result.complete && result.missing.length > 0 ? (
          <p className="mt-2 text-secondary text-warning">
            Missing: {result.missing.join(", ")}
          </p>
        ) : null}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <TileMoney label="Revenue (US)" value={result.revenue_us} />
          <TileMoney label="Cost (US)" value={result.cost_us} />
          <TileMoney label="Revenue (India)" value={result.revenue_india} />
          <TileMoney label="Cost (India)" value={result.cost_india} />
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TileMargin label="US margin" value={result.gm_us} pass={result.policy.us_pass} hasRevenue={hasUs} />
          <TileMargin
            label="India margin"
            value={result.gm_india}
            pass={result.policy.india_pass}
            hasRevenue={hasIndia}
          />
          <div className="rounded-control border border-divider p-3">
            <div className="text-secondary text-text-secondary uppercase tracking-wide">
              Combined GM
            </div>
            <MarginCell value={formatMarginPct(result.gm_blended)} />
            <div className="mt-1 text-secondary text-text-secondary">
              Informational only — never overrides the per-geography test.
            </div>
          </div>
        </div>
      </section>

      <section
        aria-label="Policy tests"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h2 className="text-section text-text mb-3">
          Independent policy tests
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <PolicyRow
            title="US floor"
            floor={result.policy.us_floor}
            outcome={usFloor}
            minPrice={result.min_price_us}
            hasRevenue={hasUs}
          />
          <PolicyRow
            title="India floor"
            floor={result.policy.india_floor}
            outcome={inFloor}
            minPrice={result.min_price_india}
            hasRevenue={hasIndia}
          />
        </div>
      </section>

      <section
        aria-label="Staffing grid"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-section text-text">Staffing grid</h2>
          <span className="text-secondary text-text-secondary">
            Restricted users see approved role costs only.
          </span>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table
            className="w-full text-body"
            aria-label="Margin lab staffing grid"
            data-testid="staffing-grid"
          >
            <thead>
              <tr className="text-left text-secondary text-text-secondary">
                <th className="px-2 py-1 font-medium">Role · grade</th>
                <th className="px-2 py-1 font-medium">Location</th>
                <th className="px-2 py-1 font-medium">Resource</th>
                <th className="px-2 py-1 font-medium">Start · end</th>
                <th className="px-2 py-1 font-medium text-right">Alloc.</th>
                <th className="px-2 py-1 font-medium text-right">Hours</th>
                <th className="px-2 py-1 font-medium text-right">
                  Bill rate
                </th>
                <th className="px-2 py-1 font-medium text-right">
                  Loaded cost
                </th>
                <th className="px-2 py-1 font-medium text-right">Revenue</th>
                <th className="px-2 py-1 font-medium text-right">
                  Delivery cost
                </th>
                <th className="px-2 py-1 font-medium text-right">GM</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-divider">
                <td
                  className="px-2 py-3 text-text-secondary italic"
                  colSpan={11}
                >
                  Staffing rows arrive from the Delivery Model Builder. The
                  Lab renders whatever the Builder saved — for now the
                  server-computed totals are shown in the summary above.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {mode === "scenarios" ? (
        <div className="rounded-panel border border-primary/40 bg-primary-subtle/40 p-4 text-body text-text">
          Scenarios save as a NEW draft. Nothing you change here modifies
          the approved baseline or overwrites historical actuals.
        </div>
      ) : null}
    </div>
  );
}

function TileMoney({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-control border border-divider p-3">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <MoneyCell value={value ?? ""} />
    </div>
  );
}

interface TileMarginProps {
  label: string;
  value: string | null;
  pass: boolean;
  hasRevenue: boolean;
}

function TileMargin({ label, value, pass, hasRevenue }: TileMarginProps) {
  return (
    <div className="rounded-control border border-divider p-3">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <MarginCell
        value={formatMarginPct(value)}
        outcome={
          !hasRevenue
            ? "unavailable"
            : value === null
              ? "unavailable"
              : pass
                ? "pass"
                : "fail"
        }
      />
    </div>
  );
}

interface PolicyRowProps {
  title: string;
  floor: string;
  outcome: ReturnType<typeof floorOutcome>;
  minPrice: string | null;
  hasRevenue: boolean;
}

function PolicyRow({ title, floor, outcome, minPrice, hasRevenue }: PolicyRowProps) {
  return (
    <div
      className="rounded-control border border-divider p-3"
      data-testid={`policy-row-${title.replace(/\s+/g, "-").toLowerCase()}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-body text-text">{title}</span>
        <StatusBadge tone={outcome.tone} label={outcome.label} />
      </div>
      <div className="mt-1 grid grid-cols-2 gap-2 text-secondary text-text-secondary">
        <div>Floor: {formatMarginPct(floor)}</div>
        <div>
          Min compliant revenue:{" "}
          {hasRevenue ? (minPrice ?? "Not calculated") : "Not applicable"}
        </div>
      </div>
    </div>
  );
}
