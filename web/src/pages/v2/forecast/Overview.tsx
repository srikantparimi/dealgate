import { Link } from "react-router-dom";
import type {
  ForecastOutlook,
  ForecastPlans,
  ForecastRow,
} from "../../../api/forecast";
import { formatPercent } from "../sow-workspace/format";

function value(amount: string | null | undefined) {
  return amount === undefined
    ? "Restricted"
    : amount === null
      ? "Unresolved"
      : amount;
}

export function ForecastOverview({
  data,
  plans,
  rows,
  onSource,
  onAccount,
}: {
  data: ForecastOutlook;
  plans: ForecastPlans | null;
  rows: ForecastRow[];
  onSource: (row: ForecastRow) => void;
  onAccount: (account: string) => void;
}) {
  return (
    <section aria-label="Forecast overview" className="space-y-5">
      <h2 className="text-lg font-semibold">Overview</h2>
      <div className="grid gap-5 border-b border-divider pb-5 sm:grid-cols-3">
        {(
          [
            ["Current month", data.current_month],
            ["Current quarter", data.current_quarter],
            [`Next ${data.future_quarters} full quarters`, data.future],
          ] as const
        ).map(([title, period]) => (
          <section key={title} className="min-w-0 space-y-2">
            <h3 className="font-medium">{title}</h3>
            <p className="text-secondary">
              {period.start} to {period.end_exclusive} (exclusive)
            </p>
            <p className="break-words text-xl font-semibold tabular-nums">
              {data.currency} {period.revenue}
            </p>
            <dl className="grid grid-cols-2 gap-2 text-secondary">
              <dt>Signed schedule</dt>
              <dd className="break-words text-right">{period.signed}</dd>
              <dt>Potential / {data.scenario}</dt>
              <dd className="break-words text-right">{period.potential}</dd>
            </dl>
          </section>
        ))}
      </div>
      <section
        className="space-y-2 border-b border-divider pb-5"
        aria-label="Future planning basis"
      >
        <h3 className="font-medium">Future planning basis</h3>
        <p className="text-secondary">
          {data.future.start} to {data.future.end_exclusive} (exclusive) /{" "}
          {data.currency} / {data.scenario} / Service schedule
        </p>
        <dl className="grid grid-cols-2 gap-x-5 gap-y-2 text-secondary sm:grid-cols-4">
          <dt>Estimated delivery cost</dt>
          <dd>{value(data.future.cost)}</dd>
          <dt>Planning GM</dt>
          <dd>
            {data.future.gm === undefined
              ? "Restricted"
              : (formatPercent(data.future.gm) ?? "Unassessed")}
          </dd>
          <dt>Signed coverage / Expected basis</dt>
          <dd>{data.future.signed_coverage === null ? "N/A" : formatPercent(data.future.signed_coverage) ?? "Unavailable"}</dd>
          <dt>Needs review subtotal</dt>
          <dd>{data.future.provisional ?? "Unavailable"}</dd>
        </dl>
      </section>
      <section aria-label="Overview decisions" className="space-y-3">
        <h3 className="font-medium">Decisions and source readiness</h3>
        {plans && (
          <p className="text-secondary">
            {plans.items.length} of {plans.total} planning sources / Page{" "}
            {plans.page}
          </p>
        )}
        {plans?.items.map((plan) => (
          <article
            key={plan.version_id}
            className="space-y-1 border-l-2 border-divider pl-3"
          >
            <h4 className="font-medium">
              {plan.opportunity_id ? (
                <Link
                  className="text-primary underline"
                  to={`/deals/${plan.opportunity_id}`}
                >
                  {plan.title}
                </Link>
              ) : (
                plan.title
              )}
            </h4>
            <p className="text-secondary">
              {plan.account_name ?? "Account unavailable"} /{" "}
              {plan.lifecycle.replaceAll("_", " ")} / {plan.source_status} /
              Version {plan.version}
            </p>
            <p className="text-secondary">
              Win probability: {formatPercent(plan.probability) ?? "Unresolved"}
            </p>
            {plan.assumptions.map((assumption, index) => (
              <p key={index} className="text-secondary">
                {assumption}
              </p>
            ))}
            {plan.job?.last_error && (
              <p className="text-danger">{plan.job.last_error}</p>
            )}
          </article>
        ))}
        {plans?.total === 0 && (
          <p className="text-secondary">No planning sources in this scope.</p>
        )}
        {data.pending_sources.map((id) => (
          <p key={id} className="break-all text-warning">
            Calculation pending: {id}
          </p>
        ))}
        {data.unresolved_sources.map((source) => (
          <div key={source.source_version} className="space-y-1 text-warning">
            <h4 className="font-medium">{source.name}</h4>
            {source.reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
          </div>
        ))}
      </section>
      <section
        aria-label="Continuity evidence"
        className="space-y-2 border-y border-divider py-4"
      >
        <h3 className="font-medium">
          Continuity and assessment-to-project journey
        </h3>
        <p className="text-secondary">
          Expiry risk unavailable: contract end dates and renewal decisions are
          not supplied in this outlook.
        </p>
        <p className="text-secondary">
          Assessment-to-project linkage unavailable: source and follow-on
          relationships are not supplied in this outlook.
        </p>
      </section>
      <section aria-label="Overview sources" className="space-y-3">
        <h3 className="font-medium">Source schedules</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-body [&_th]:whitespace-nowrap [&_th]:p-3 [&_td]:p-3 [&_td]:align-top [&_tbody_tr]:border-t [&_tbody_tr]:border-divider">
            <thead>
              <tr>
                {[
                  "Account",
                  "Source",
                  "Service month",
                  "Status",
                  "Signed",
                  "Potential",
                  "Scenario revenue",
                ].map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.row_id}>
                  <td>
                    <button
                      className="text-primary underline"
                      onClick={() => onAccount(row.account_id)}
                    >
                      {data.accounts.find(
                        (account) => account.account_id === row.account_id,
                      )?.name ?? "Account unavailable"}
                    </button>
                  </td>
                  <td>
                    <button
                      className="text-primary underline"
                      onClick={() => onSource(row)}
                    >
                      {row.source_name ??
                        (row.lifecycle === "signed"
                          ? "Signed schedule"
                          : "Planning source")}
                    </button>
                  </td>
                  <td className="whitespace-nowrap">{row.month}</td>
                  <td>{row.lifecycle.replaceAll("_", " ")}</td>
                  <td>{row.signed}</td>
                  <td>{row.potential}</td>
                  <td>{row.revenue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <p className="text-secondary">
            No eligible source rows for this period.
          </p>
        )}
      </section>
    </section>
  );
}
