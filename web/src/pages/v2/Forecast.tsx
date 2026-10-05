import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  RefreshCw,
  X,
} from "lucide-react";
import {
  forecastCsv,
  getForecastOutlook,
  getForecastPlans,
  type ForecastFilters,
  type ForecastOutlook,
  type ForecastPeriod,
  type ForecastPlans,
  type ForecastRow,
} from "../../api/forecast";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { formatPercent } from "./sow-workspace/format";
import { RevenueChart } from "./forecast/RevenueChart";
import { ForecastOverview } from "./forecast/Overview";
import { NextOpportunities } from "./forecast/NextOpportunities";
import { ResourceDemand } from "./forecast/ResourceDemand";
import { CurrentEstimate } from "./forecast/CurrentEstimate";

function month(value: string) {
  return new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString(
    "en-US",
    { month: "long", year: "numeric", timeZone: "UTC" },
  );
}
function amount(value: string | null | undefined) {
  return value === undefined
    ? "Restricted"
    : value === null
      ? "Unresolved"
      : value;
}
function Table({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <div role="region" aria-label={label} className="overflow-x-auto">
      <table className="w-full text-left text-body [&_th]:whitespace-nowrap [&_th]:px-3 [&_th]:py-3 [&_th]:font-medium [&_td]:px-3 [&_td]:py-3 [&_td]:align-top [&_tbody_tr]:border-t [&_tbody_tr]:border-divider">
        {children}
      </table>
    </div>
  );
}

export function ForecastPage() {
  const [params, setParams] = useSearchParams();
  const scenario =
    params.get("scenario") === "committed"
      ? "committed"
      : params.get("scenario") === "upside"
        ? "upside"
        : "expected";
  const quarters =
    params.get("future_quarters") === "1"
      ? 1
      : params.get("future_quarters") === "4"
        ? 4
        : 2;
  const account = params.get("account_id") || undefined;
  const asOf = params.get("as_of") || undefined;
  const selectedMonth = params.get("month") || "";
  const view =
    params.get("view") === "revenue"
      ? "revenue"
      : params.get("view") === "overview"
        ? "overview"
        : params.get("view") === "resources"
          ? "resources"
        : params.get("view") === "opportunities"
          ? "opportunities"
          : "company";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const [data, setData] = useState<ForecastOutlook | null>(null);
  const [plans, setPlans] = useState<ForecastPlans | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [selectedSource, setSelectedSource] = useState<ForecastRow | null>(
    null,
  );
  useEffect(() => {
    setSelectedSource(null);
  }, [selectedMonth, view]);
  const filters = useMemo<ForecastFilters>(
    () => ({
      scenario,
      future_quarters: quarters,
      account_id: account,
      as_of: asOf,
    }),
    [scenario, quarters, account, asOf],
  );
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setLoading(true);
    setError("");
    setSelectedSource(null);
    Promise.all([
      getForecastOutlook(filters, controller.signal),
      getForecastPlans(
        { account_id: account, page, size: 50 },
        controller.signal,
      ),
    ])
      .then(([outlook, sources]) => {
        if (current) {
          setData(outlook);
          setPlans(sources);
        }
      })
      .catch((e) => {
        if (current) {
          setError(e instanceof Error ? e.message : "Forecast is unavailable");
          setData(null);
          setPlans(null);
        }
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [filters, account, page, revision]);
  useEffect(() => {
    if (loading || !data || !selectedMonth || data.months.some((month) => month.start === selectedMonth)) return;
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (next.get("month") === selectedMonth) next.delete("month");
      return next;
    }, { replace: true });
  }, [data, loading, selectedMonth, setParams]);
  function update(values: Record<string, string | undefined>) {
    setParams((old) => {
      const next = new URLSearchParams(old);
      Object.entries(values).forEach(([key, value]) =>
        value ? next.set(key, value) : next.delete(key),
      );
      return next;
    });
  }
  const rows =
    data?.rows.filter(
      (row) =>
        data.months.some((period) => period.start === row.month) &&
        (!selectedMonth || row.month === selectedMonth),
    ) ?? [];
  const accountName =
    data?.accounts.find((row) => row.account_id === account)?.name ?? account;
  function exportRows() {
    if (!data || loading) return;
    const url = URL.createObjectURL(
      new Blob([forecastCsv(rows, data)], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `forecast-${data.scenario}-${data.as_of.slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <main className="mx-auto min-w-0 max-w-[1600px] space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Forecast</h1>
          <p className="text-secondary text-text-secondary">
            {!loading && data ? data.scope_label : "Forecast outlook"}
            {accountName ? ` / ${accountName}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="icon"
            aria-label="Refresh forecast"
            title="Refresh forecast"
            disabled={loading}
            onClick={() => setRevision((v) => v + 1)}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button
            variant="secondary"
            disabled={!data || loading}
            onClick={exportRows}
          >
            <Download className="h-4 w-4" />
            Export rows
          </Button>
        </div>
      </header>
      <section
        aria-label="Forecast filters"
        className="flex flex-wrap items-end gap-4 border-y border-divider py-4"
      >
        <label className="min-w-44 text-secondary">
          Future quarters
          <select
            aria-label="Future quarters"
            value={quarters}
            onChange={(e) =>
              update({ future_quarters: e.target.value, page: undefined })
            }
            className="mt-1 block h-10 w-full rounded-md border border-divider bg-surface px-3"
          >
            <option value="1">Next quarter</option>
            <option value="2">Next 2 quarters</option>
            <option value="4">Next 4 quarters</option>
          </select>
        </label>
        <label className="min-w-44 text-secondary">
          As of (UTC)
          <Input
            type="date"
            aria-label="As of (UTC)"
            value={asOf?.slice(0, 10) ?? data?.as_of.slice(0, 10) ?? ""}
            onChange={(e) =>
              update({
                as_of: e.target.value
                  ? `${e.target.value}T00:00:00Z`
                  : undefined,
              })
            }
          />
        </label>
        <div
          className="flex flex-wrap gap-1"
          role="group"
          aria-label="Forecast scenario"
        >
          {(["committed", "expected", "upside"] as const).map((value) => (
            <Button
              key={value}
              variant={scenario === value ? "primary" : "secondary"}
              aria-pressed={scenario === value}
              onClick={() => update({ scenario: value })}
            >
              {value[0].toUpperCase() + value.slice(1)}
            </Button>
          ))}
        </div>
        {account && (
          <Button
            variant="tertiary"
            onClick={() => update({ account_id: undefined, page: undefined })}
          >
            <ArrowLeft className="h-4 w-4" />
            All accounts
          </Button>
        )}
        {selectedMonth && (
          <Button
            variant="tertiary"
            aria-label="Clear month filter"
            onClick={() => update({ month: undefined })}
          >
            {month(selectedMonth)}
            <X className="h-4 w-4" />
          </Button>
        )}
      </section>
      <nav
        className="flex flex-wrap gap-2 border-b border-divider pb-2"
        role="tablist"
        aria-label="Forecast views"
      >
        {(
          [
            ["company", "Company & accounts"],
            ["overview", "Overview"],
            ["revenue", "Revenue projection"],
            ["opportunities", "Next opportunities"],
            ["resources", "Resource demand"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            id={`forecast-${key}`}
            role="tab"
            aria-selected={view === key}
            aria-controls="forecast-view"
            variant={view === key ? "primary" : "tertiary"}
            onClick={() => update({ view: key })}
          >
            {label}
          </Button>
        ))}
      </nav>
      {error && (
        <p role="alert" className="border-l-4 border-danger p-3 text-danger">
          {error}
        </p>
      )}
      {loading && <p role="status">Loading forecast...</p>}
      {!loading && data && (
        <>
          <div className="flex flex-wrap justify-between gap-2 text-secondary text-text-secondary">
            <span>
              {data.currency} / {data.scenario} / {data.timezone}
            </span>
            <span>As of {data.as_of}</span>
            <span>
              {data.actuals_available
                ? data.actuals_basis
                : "Actuals unavailable"}
            </span>
          </div>
          {(data.pending_sources.length > 0 || data.unresolved_sources.length > 0 || data.excluded.length > 0) && <p role="status" className="text-secondary text-warning">Source coverage: {data.pending_sources.length} pending / {data.unresolved_sources.length} unresolved / {data.excluded.length} excluded</p>}
          {view !== "resources" && data.financial_actuals && (data.financial_actuals.totals.length > 0 || data.financial_actuals.excluded.length > 0) && (
            <section aria-label="Financial actuals" className="border-y border-divider py-4">
              <h2 className="font-semibold">Financial actuals</h2>
              <p className="text-secondary">Through {data.financial_actuals.cutoff} / Separate from service schedules</p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead><tr>{["Service month", "Measure", "Currency", "Amount"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead>
                  <tbody>{data.financial_actuals.totals.map(row => (
                    <tr key={`${row.period_month}:${row.measure}`} className="border-t border-divider">
                      <td className="p-2">{row.period_month}</td>
                      <td className="p-2">{({ recognized_revenue: "Recognized revenue", billed: "Billed", cash_collected: "Cash collected", delivery_cost: "Delivery cost" } as Record<string, string>)[row.measure] ?? row.measure}</td>
                      <td className="p-2">{row.currency}</td><td className="p-2 tabular-nums">{row.amount}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              {data.financial_actuals.excluded.map(row => <p key={row.id} role="status" className="text-secondary text-warning">{row.id}: {row.reason}</p>)}
            </section>
          )}
          {view !== "resources" && <CurrentEstimate data={data} />}
          {view !== "resources" && <RevenueChart
            months={data.months}
            currency={data.currency}
            onMonth={(value) => update({ view: "revenue", month: value })}
          />}
          <div
            role="tabpanel"
            id="forecast-view"
            aria-labelledby={`forecast-${view}`}
          >
            {view === "resources" ? (
              <ResourceDemand accountId={account} forecastSearch={params.toString()}
                period={data.months.find((month) => month.start === selectedMonth) ?? {
                  start: data.current_quarter.start, end_exclusive: data.future.end_exclusive,
                }} />
            ) : view === "opportunities" && plans ? (
              <NextOpportunities
                plans={plans}
                onSaved={() => setRevision(value => value + 1)}
              />
            ) : view === "overview" ? (
              <ForecastOverview
                data={data}
                plans={plans}
                rows={rows}
                onSource={setSelectedSource}
                onAccount={(account_id) =>
                  update({ account_id, page: undefined })
                }
              />
            ) : view === "company" ? (
              <>
                <div className="grid gap-6 border-b border-divider pb-5 md:grid-cols-3">
                  <Period
                    title="Current month"
                    period={data.current_month}
                    currency={data.currency}
                  />
                  <Period
                    title="Current quarter"
                    period={data.current_quarter}
                    currency={data.currency}
                  />
                  <Period
                    title={`Next ${data.future_quarters} full quarter${data.future_quarters === 1 ? "" : "s"}`}
                    period={data.future}
                    currency={data.currency}
                  />
                </div>
                <h2 className="mb-2 mt-5 text-lg font-semibold">Accounts</h2>
                <Table label="Account outlook">
                  <thead>
                    <tr>
                      <th>Account</th>
                      <th>Current month</th>
                      <th>Current quarter</th>
                      {data.quarters.slice(1).map((quarter) => (
                        <th key={quarter.start}>
                          Quarter from {quarter.start}
                        </th>
                      ))}
                      <th>Future signed</th>
                      <th>Future potential</th>
                      <th>Future total</th>
                      <th>Signed coverage</th>
                      <th>Future cost</th>
                      <th>Planning GM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.accounts.map((row) => (
                      <tr key={row.account_id}>
                        <td>
                          <button
                            className="text-primary underline underline-offset-4"
                            onClick={() =>
                              update({
                                account_id: row.account_id,
                                page: undefined,
                              })
                            }
                          >
                            {row.name}
                          </button>
                        </td>
                        <td>{row.current_month.revenue}</td>
                        <td>{row.current_quarter.revenue}</td>
                        {data.quarters.slice(1).map((quarter) => (
                          <td key={quarter.start}>
                            {row.quarters.find(
                              (value) => value.start === quarter.start,
                            )?.revenue ?? "Unavailable"}
                          </td>
                        ))}
                        <td>{row.future.signed}</td>
                        <td>{row.future.potential}</td>
                        <td>{row.future.revenue}</td>
                        <td>
                          {formatPercent(row.future.signed_coverage) ??
                            "Unassessed"}
                        </td>
                        <td>{amount(row.future.cost)}</td>
                        <td>
                          {row.future.gm === undefined
                            ? "Restricted"
                            : (formatPercent(row.future.gm) ?? "Unassessed")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {data.accounts.length === 0 && (
                  <p className="py-6 text-text-secondary">
                    No accounts in this scope.
                  </p>
                )}
              </>
            ) : (
              <>
                <h2 className="mb-3 text-lg font-semibold">
                  Monthly revenue / {data.currency}
                </h2>
                <Table label="Monthly revenue projection">
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Signed</th>
                      <th>Potential</th>
                      <th>{data.scenario} total</th>
                      <th>Estimated cost</th>
                      <th>Planning GM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.months.map((period) => (
                      <tr
                        key={period.start}
                        className={
                          period.start === selectedMonth
                            ? "bg-primary-subtle"
                            : ""
                        }
                      >
                        <td>
                          <button
                            className="whitespace-nowrap text-primary underline underline-offset-4"
                            onClick={() => update({ month: period.start })}
                          >
                            {month(period.start)}
                          </button>
                        </td>
                        <td>{period.signed}</td>
                        <td>{period.potential}</td>
                        <td>{period.revenue}</td>
                        <td>{amount(period.cost)}</td>
                        <td>
                          {period.gm === undefined
                            ? "Restricted"
                            : (formatPercent(period.gm) ?? "Unassessed")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <h2 className="mb-2 mt-5 text-lg font-semibold">
                  Source rows{selectedMonth ? ` / ${month(selectedMonth)}` : ""}
                </h2>
                <Table label="Forecast source rows">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Month</th>
                      <th>Status</th>
                      <th>Signed</th>
                      <th>Potential</th>
                      <th>Revenue</th>
                      <th>Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.row_id}>
                        <td>
                          <button
                            className="text-primary underline"
                            onClick={() => setSelectedSource(row)}
                          >
                            {row.source_name ??
                              plans?.items.find(
                                (plan) =>
                                  plan.id === row.source_id &&
                                  plan.version_id === row.source_version,
                              )?.title ??
                              (row.lifecycle === "signed"
                                ? "Signed schedule"
                                : "Planning source")}
                          </button>
                        </td>
                        <td className="whitespace-nowrap">
                          {month(row.month)}
                        </td>
                        <td>{row.lifecycle.replaceAll("_", " ")}</td>
                        <td>{row.signed}</td>
                        <td>{row.potential}</td>
                        <td>{row.revenue}</td>
                        <td>{amount(row.cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {rows.length === 0 && (
                  <p className="py-4 text-text-secondary">
                    No eligible source rows for this period.
                  </p>
                )}
              </>
            )}
          </div>
          {selectedSource && (
            <section
              aria-label="Source detail"
              className="border-y border-divider py-4"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Source detail</h2>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Close source detail"
                  onClick={() => setSelectedSource(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              {selectedSource.source_url?.startsWith("/") &&
                !selectedSource.source_url.startsWith("//") && (
                  <Link
                    className="text-primary underline"
                    to={selectedSource.source_url}
                  >
                    {selectedSource.source_name ?? "Open source"}
                  </Link>
                )}
              <dl className="grid gap-2 text-secondary sm:grid-cols-2">
                <dt>Source</dt>
                <dd className="break-all">{selectedSource.source_id}</dd>
                <dt>Source version</dt>
                <dd className="break-all">{selectedSource.source_version}</dd>
                <dt>Calculation version</dt>
                <dd>{selectedSource.calculation_version ?? "Unavailable"}</dd>
                <dt>Economic scope</dt>
                <dd className="break-all">{selectedSource.scope_id}</dd>
                <dt>Probability</dt>
                <dd>
                  {formatPercent(selectedSource.probability) ?? "Unavailable"}
                </dd>
                <dt>FX version</dt>
                <dd>{selectedSource.fx_version ?? "Not applied"}</dd>
                <dt>Original currency</dt>
                <dd>{selectedSource.original_currency ?? "Unavailable"}</dd>
                <dt>FX date</dt>
                <dd>{selectedSource.fx_date ?? "Not applied"}</dd>
              </dl>
              {(
                selectedSource.assumptions ??
                plans?.items.find(
                  (plan) =>
                    plan.id === selectedSource.source_id &&
                    plan.version_id === selectedSource.source_version,
                )?.assumptions
              )?.map((assumption, i) => (
                <p key={i} className="mt-2 text-secondary">
                  {assumption}
                </p>
              ))}
              {selectedSource.source_evidence?.map((evidence, i) => (
                <p key={i} className="mt-2 text-secondary">
                  {evidence}
                </p>
              ))}
            </section>
          )}
          <section
            aria-label="Forecast exceptions"
            className="border-t border-divider pt-4"
          >
            <h2 className="text-lg font-semibold">Source coverage</h2>
            <p className="text-secondary">{data.source_coverage}</p>
            {!data.legacy_sources_included && (
              <p className="text-secondary">Legacy schedules excluded</p>
            )}
            {data.stale && (
              <p className="text-warning">Source updates pending</p>
            )}
            {data.pending_sources.length > 0 && (
              <div className="mt-2">
                <h3 className="font-medium">Pending calculations</h3>
                {data.pending_sources.map((id) => (
                  <p key={id} className="break-all text-secondary">
                    {id}
                  </p>
                ))}
              </div>
            )}
            {data.unresolved_sources.map((source) => (
              <div key={source.source_version} className="mt-3">
                <h3 className="font-medium">{source.name}</h3>
                {source.reasons.map((reason) => (
                  <p key={reason} className="text-warning">
                    {reason}
                  </p>
                ))}
              </div>
            ))}
            {data.excluded.map((source) => (
              <div key={source.row_id} className="mt-3">
                <p className="break-all text-secondary">
                  Excluded / {source.month} /{" "}
                  {source.source_name ?? source.source_id}
                </p>
                {source.reasons.map((reason) => (
                  <p key={reason} className="text-warning">
                    {reason}
                  </p>
                ))}
              </div>
            ))}
          </section>
          {plans && (
            <section
              aria-label="Planning sources"
              className="border-t border-divider pt-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">
                  Planning sources / {plans.total}
                </h2>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Previous source page"
                    disabled={plans.page <= 1}
                    onClick={() => update({ page: String(plans.page - 1) })}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-secondary">Page {plans.page}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Next source page"
                    disabled={plans.page * plans.size >= plans.total}
                    onClick={() => update({ page: String(plans.page + 1) })}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <Table label="Versioned plans">
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Account</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Version</th>
                    <th>Calculation job</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.items.map((plan) => (
                    <tr key={plan.version_id}>
                      <td>{plan.title}</td>
                      <td>{plan.account_name ?? "Account unavailable"}</td>
                      <td>{plan.source_status}</td>
                      <td>{plan.lifecycle.replaceAll("_", " ")}</td>
                      <td>{plan.version}</td>
                      <td>
                        {plan.job?.status ?? "No job"}
                        {plan.job?.last_error && (
                          <p className="text-danger">{plan.job.last_error}</p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </section>
          )}
          <footer className="space-y-1 border-t border-divider pt-3 text-secondary text-text-secondary">
            <p>
              Service-month schedules / {data.source_count} sources /{" "}
              {data.schema_version}
            </p>
            <p className="break-all">Watermark {data.source_watermark}</p>
          </footer>
        </>
      )}
    </main>
  );
}

function Period({
  title,
  period,
  currency,
}: {
  title: string;
  period: ForecastPeriod;
  currency: string;
}) {
  return (
    <section className="min-w-0 space-y-2">
      <h2 className="font-semibold">{title}</h2>
      <p className="text-secondary text-text-secondary">
        {period.start} to {period.end_exclusive} (exclusive)
      </p>
      <p className="break-words text-2xl font-semibold">
        {currency} {period.revenue}
      </p>
      <dl className="grid grid-cols-2 gap-2 text-secondary">
        <dt>Signed</dt>
        <dd className="break-words text-right">{period.signed}</dd>
        <dt>Potential</dt>
        <dd className="break-words text-right">{period.potential}</dd>
        <dt>Needs review</dt>
        <dd className="break-words text-right">
          {period.provisional ?? "Unavailable"}
        </dd>
        <dt>Signed coverage</dt>
        <dd className="text-right">
          {period.signed_coverage === null ? "N/A" : formatPercent(period.signed_coverage) ?? "Unavailable"}
        </dd>
        <dt>Estimated cost</dt>
        <dd className="break-words text-right">{amount(period.cost)}</dd>
        <dt>Planning GM</dt>
        <dd className="text-right">
          {period.gm === undefined
            ? "Restricted"
            : (formatPercent(period.gm) ?? "Unassessed")}
        </dd>
      </dl>
    </section>
  );
}
