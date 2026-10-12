/**
 * Forecast tab (S22 P2-2), as the prototype: the "monthly required" line, the
 * all-resources block, one block per assignment (hourly types), per-person
 * revenue by month. Every cell is a server value from GET /engagements/{id}/forecast;
 * the "Total" column uses the engine's totals, never a browser sum.
 */

import type { ReactNode } from "react";
import { EMPLOYMENT_TYPE_LABEL, HOURLY_TYPES, type AllocationMonth } from "../../../api/engagements";
import { cn } from "../../../lib/cn";
import type { EngagementData } from "./EngagementPage";
import { duration, hours, money, monthLabel, pct } from "./format";
import { headCell, headCellNum, numCell, table, tableWrap, textCell, totalsRow } from "./shared";

export function ForecastTab({ data }: { data: EngagementData }) {
  const { engagement, forecast, allocations } = data;
  const hourly = HOURLY_TYPES.has(engagement.type);
  const months = forecast.months;
  const floor = forecast.project_floor_pct;
  const under = (value: number | null | undefined) => value !== null && value !== undefined && floor !== null && value < floor;

  const head = (first: string) => (
    <thead>
      <tr>
        <th className={headCell}>{first}</th>
        {months.map((m) => (
          <th key={m.month} className={headCellNum}>
            {monthLabel(m.month)}
          </th>
        ))}
        <th className={headCellNum}>Total</th>
      </tr>
    </thead>
  );

  const line = (label: ReactNode, cells: ReactNode[], total: ReactNode, className?: string, redFlags?: boolean[]) => (
    <tr className={className}>
      <td className={textCell}>{label}</td>
      {cells.map((cell, index) => (
        <td key={months[index]?.month ?? index} className={cn(numCell, redFlags?.[index] && "font-semibold text-danger")}>
          {cell}
        </td>
      ))}
      <td className={cn(numCell, "font-semibold")}>{total}</td>
    </tr>
  );

  const byMonth = (allocationId: string): Record<string, AllocationMonth> =>
    Object.fromEntries(forecast.allocation_months.filter((am) => am.allocation_id === allocationId).map((am) => [am.month, am]));

  return (
    <div className="flex flex-col gap-4">
      <p className="text-secondary text-text-secondary" data-testid="monthly-required">
        {forecast.monthly_required
          ? `Monthly view required — ${duration(forecast.duration_months, 1)} months.`
          : `Short engagement (${duration(forecast.duration_months, 1)} months) — the summary is enough, monthly shown for completeness.`}{" "}
        Partial months prorated by days.
      </p>

      <div className={tableWrap}>
        <table className={table} aria-label="All resources by month">
          {head("All resources")}
          <tbody>
            {line("People", months.map((m) => m.people), "")}
            {line("Hours", months.map((m) => hours(m.hours)), hours(forecast.totals.hours))}
            {line("Revenue", months.map((m) => money(m.total_revenue)), money(forecast.totals.total_revenue))}
            {line("Labour + burden", months.map((m) => money(m.loaded_cost)), money(forecast.totals.loaded_cost))}
            {line("Additional costs", months.map((m) => money(m.additional_costs)), money(forecast.totals.additional_costs))}
            {line("Total cost", months.map((m) => money(m.total_cost)), money(forecast.totals.total_cost))}
            {line("Gross margin $", months.map((m) => money(m.gm)), money(forecast.totals.gm), totalsRow)}
            {line(
              <b>Gross margin %</b>,
              months.map((m) => pct(m.gm_pct)),
              pct(forecast.totals.gm_pct),
              undefined,
              months.map((m) => under(m.gm_pct)),
            )}
          </tbody>
        </table>
      </div>

      {hourly
        ? Object.keys(forecast.by_assignment)
            .sort()
            .map((assignment) => {
              const lines = forecast.by_assignment[assignment];
              const totals = forecast.by_assignment_totals?.[assignment];
              const get = <K extends keyof (typeof lines)[string]>(key: K) => months.map((m) => lines[m.month]?.[key]);
              return (
                <section key={assignment} aria-label={`${assignment} by month`}>
                  <h2 className="mb-2 mt-2 text-section font-semibold">{assignment}</h2>
                  <div className={tableWrap}>
                    <table className={table} aria-label={`${assignment} by month`}>
                      {head("Assignment")}
                      <tbody>
                        {line("People", get("people").map((v) => v ?? 0), totals?.people ?? "")}
                        {line("Hours", get("hours").map((v) => (v === undefined ? "—" : hours(v))), totals ? hours(totals.hours) : "")}
                        {line("Revenue", get("revenue").map((v) => (v === undefined ? "—" : money(v))), totals ? money(totals.revenue) : "")}
                        {line(
                          "Loaded cost",
                          get("loaded_cost").map((v) => (v === undefined ? "—" : money(v))),
                          totals?.loaded_cost === undefined ? "—" : money(totals.loaded_cost),
                        )}
                        {line(
                          <b>Gross margin %</b>,
                          get("gm_pct").map((v) => (v === undefined ? "—" : pct(v))),
                          totals?.gm_pct === undefined ? "—" : pct(totals.gm_pct),
                          undefined,
                          get("gm_pct").map((v) => under(v)),
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              );
            })
        : null}

      <section aria-label="Per person by month">
        <h2 className="mb-2 mt-2 text-section font-semibold">Per person · {hourly ? "revenue" : "hours"} by month</h2>
        <div className={tableWrap}>
          <table className={table} aria-label="Per person by month">
            {head("Person")}
            <tbody>
              {allocations.map((row) => {
                const cells = byMonth(row.id);
                return line(
                  <span>
                    {row.resource_name}
                    {row.role ? ` · ${row.role}` : ""}
                    {row.assignment ? ` · ${row.assignment}` : ""}{" "}
                    <span className="text-secondary text-text-secondary">
                      {row.location} {EMPLOYMENT_TYPE_LABEL[row.employment_type].split(" ")[0]}
                    </span>
                  </span>,
                  months.map((m) => {
                    const cell = cells[m.month];
                    if (!cell) return "";
                    return hourly ? money(cell.revenue) : hours(cell.hours);
                  }),
                  hourly ? money(row.totals.revenue) : hours(row.totals.hours),
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-secondary text-text-secondary">
          {hourly ? "Revenue per person" : "Hours per person (fixed-fee types carry no per-person revenue)"}. A blank cell is a month with nobody billing.
        </p>
      </section>
    </div>
  );
}
