import type { FinanceSummary, SowConfirmationFloors } from "../../../../api/client";
import { FloorBar } from "../../../../ui-v2/FloorBar";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { formatPercent, formatUsd } from "../format";

export type FinanceGmResult = Partial<SowConfirmationFloors> & { finance_summary?: FinanceSummary };

export function FinanceGmPanel({ result, locations = [], state = "draft" }: {
  result: FinanceGmResult | null | undefined;
  locations?: string[];
  state?: "draft" | "saved" | "review snapshot";
}) {
  const c = result ?? {};
  const summary = c.finance_summary;
  const components = [
    { name: "US", value: c.gm_us, floor: c.us_floor ?? "0.35", pass: c.us_pass, delta: c.us_delta, applicable: c.us_applicable ?? (locations.length ? locations.includes("US") : c.gm_us != null) },
    { name: "India", value: c.gm_india, floor: c.india_floor ?? "0.50", pass: c.india_pass, delta: c.india_delta, applicable: c.india_applicable ?? (locations.length ? locations.includes("India") : c.gm_india != null) },
  ];
  const active = components.filter((row) => row.applicable);
  const incomplete = c.complete === false;
  const missing = incomplete || !active.length || active.some((row) => row.value == null || row.pass == null);
  const failed = active.filter((row) => row.pass === false);
  const label = incomplete ? "Incomplete staffing costs" : missing ? "GM unavailable" : failed.length ? `Fails · ${failed.map((row) => row.name).join(", ")}` : active.length === 2 ? "Passes both floors" : `Passes ${active[0].name} floor`;
  return (
    <section aria-label="GM summary" className="min-w-0 space-y-5 border-l border-divider pl-4 text-secondary tnum">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-body font-semibold text-text">GM summary</h3>
        <span className="text-text-secondary">GM{c.gm_version ? ` v${c.gm_version}` : ""} · {state}</span>
      </header>
      <dl className="space-y-2">
        <MoneyRow label="Contract price" amount={summary?.revenue ?? c.revenue_total} />
        <MoneyRow label="Labor cost" amount={incomplete ? null : summary?.labor_cost} pct={incomplete ? null : summary?.labor_pct} cost />
        <MoneyRow label="Direct costs" amount={summary?.direct_cost} pct={summary?.direct_pct} cost />
        <MoneyRow label="Total delivery cost" amount={incomplete ? null : summary?.total_delivery_cost} pct={incomplete ? null : summary?.total_cost_pct} cost />
        <MoneyRow label="Gross profit" amount={incomplete ? null : summary?.gross_profit} />
        <div className="flex items-start justify-between gap-3 font-semibold"><dt>Gross margin</dt><dd>{incomplete ? "Unavailable" : formatPercent(c.gm_blended) ?? "Unavailable"}</dd></div>
      </dl>
      {components.map((row) => (
        <div key={row.name} className="space-y-4">
          <div className="flex flex-wrap justify-between gap-2">
            <span>{row.name}{row.applicable ? ` · floor ${formatPercent(row.floor, 0)}` : ""}</span>
            <span className={!row.applicable ? "text-text-muted" : row.pass === false ? "text-danger" : "text-text"}>{row.applicable ? incomplete ? "Unavailable" : formatPercent(row.value) ?? "Unavailable" : `Not applicable — no ${row.name} resources`}</span>
          </div>
          {row.applicable && row.value != null && !incomplete ? <FloorBar value={row.value} floor={row.floor} passes={row.pass} delta={row.delta} label={row.name} /> : null}
        </div>
      ))}
      <div className="flex flex-wrap justify-between gap-2 text-text-secondary"><span>Blended</span><span>{incomplete ? "Unavailable" : formatPercent(c.gm_blended) ?? "Unavailable"} · informational</span></div>
      <StatusBadge tone={missing ? "warning" : failed.length ? "danger" : "success"} label={label} data-testid="staffing-floor-summary" />
      {summary?.pass_through != null && Number(summary.pass_through) !== 0 ? <dl className="border-t border-divider pt-3"><MoneyRow label="Client-reimbursed (pass-through)" amount={summary.pass_through} /><dd className="mt-1 text-right text-text-muted">outside GM</dd></dl> : null}
    </section>
  );
}

function MoneyRow({ label, amount, pct, cost }: { label: string; amount?: string | null; pct?: string | null; cost?: boolean }) {
  return <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1"><dt className={cost ? "pl-2 text-text-secondary" : "font-medium"}>{label}</dt><dd className="flex flex-wrap justify-end gap-x-3"><span>{formatUsd(amount) ?? "Unavailable"}</span>{cost ? <span className="text-text-secondary">{formatPercent(pct) ?? "Unavailable"} of price</span> : null}</dd></div>;
}
