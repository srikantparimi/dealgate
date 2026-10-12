/**
 * Forecast tab (S22 P2-2), as the prototype: the "monthly required" line, the
 * all-resources block, one block per assignment (hourly types), per-person
 * revenue by month. Every cell is a server value from GET /engagements/{id}/forecast;
 * the "Total" column uses the engine's totals, never a browser sum.
 */

import { useState, type ReactNode } from "react";
import { Button } from "../../../ui-v2/primitives/button";
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
  // P4-2: a short engagement (≤ 2 months) is judged on the total; the month split is behind a button.
  const short = !forecast.monthly_required;
  const [showSplit, setShowSplit] = useState(false);
  const splitVisible = !short || showSplit;
  const peopleTotal = forecast.months.reduce((max, m) => Math.max(max, m.people), 0);

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
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-secondary text-text-secondary" data-testid="monthly-required">
          {short
            ? `Short engagement (${duration(forecast.duration_months)} months, ${engagement.start} → ${engagement.end}) — judged on the total.`
            : `Monthly view required — ${duration(forecast.duration_months, 1)} months.`}{" "}
          {splitVisible ? "Partial months are prorated by days; one-time costs spread across the term like the price." : ""}
        </p>
        {short ? (
          <Button size="sm" variant="secondary" onClick={() => setShowSplit((v) => !v)} data-testid="toggle-split">
            {showSplit ? "Hide month split" : "Show month split"}
          </Button>
        ) : null}
      </div>

      {short && !splitVisible ? (
        <div className={tableWrap} data-testid="term-summary">
          <table className={table} aria-label="All resources, whole term">
            <thead>
              <tr>
                <th className={headCell}>All resources</th>
                <th className={headCellNum}>
                  Total · {engagement.start} → {engagement.end}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr><td className={textCell}>People</td><td className={numCell}>{peopleTotal}</td></tr>
              <tr><td className={textCell}>Hours</td><td className={numCell}>{hours(forecast.totals.hours)}</td></tr>
              <tr><td className={textCell}>Revenue</td><td className={numCell}>{money(forecast.totals.total_revenue)}</td></tr>
              <tr><td className={textCell}>Labour + burden</td><td className={numCell}>{money(forecast.totals.loaded_cost)}</td></tr>
              <tr><td className={textCell}>Additional costs</td><td className={numCell}>{money(forecast.totals.additional_costs)}</td></tr>
              <tr><td className={textCell}>Total cost</td><td className={numCell}>{money(forecast.totals.total_cost)}</td></tr>
              <tr className={totalsRow}><td className={textCell}>Gross margin $</td><td className={numCell}>{money(forecast.totals.gm)}</td></tr>
              <tr><td className={textCell}><b>Gross margin %</b></td><td className={cn(numCell, "font-semibold", under(forecast.totals.gm_pct) && "text-danger")}>{pct(forecast.totals.gm_pct)}</td></tr>
            </tbody>
          </table>
        </div>
      ) : null}

      {splitVisible ? (
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
      ) : null}

      {hourly && splitVisible
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

      {splitVisible ? (
      <section aria-label="Per person by month">
        <h2 className="mb-2 mt-2 text-section font-semibold" data-testid="per-person-heading">Per person · {hourly ? "revenue" : "hours"} by month</h2>
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
      ) : null}
    </div>
  );
}
