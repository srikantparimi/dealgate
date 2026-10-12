/**
 * /portfolio — Portfolio forecast (S22 P3-1 … P3-3), copied from the prototype.
 *
 * Month picker, type and client filters, the four signal cards, the table
 * with its totals row (totals come from the server, before any paging), the
 * roll-offs and bench panels (names, never ids), CSV export. Every number is
 * the engine's, served by GET /portfolio/forecast.
 *
 * Cards deep-link to the list they count: Portfolio GM → the totals row,
 * Below floor → the table filtered to BELOW FLOOR rows, Roll-offs → the
 * roll-offs panel, Bench → the bench panel.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Download, Plus, Settings2 } from "lucide-react";
import {
  ENGAGEMENT_TYPE_LABEL,
  EMPLOYMENT_TYPE_LABEL,
  downloadPortfolioCsv,
  getPortfolioForecast,
  listClientOptions,
  listEngagements,
  type ClientOption,
  type EngagementType,
  type PortfolioForecast,
} from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { cn } from "../../../lib/cn";
import { currentMonthKey, money, monthLabel, monthsBetween, pct } from "./format";
import {
  Panel,
  StatusPill,
  WRITE_ROLES,
  errorText,
  hasAny,
  headCell,
  headCellNum,
  numCell,
  table,
  tableWrap,
  textCell,
  totalsRow,
  useGroups,
} from "./shared";

type Focus = "" | "gm" | "below_floor" | "rolloffs" | "bench";

export function PortfolioPage() {
  const navigate = useNavigate();
  const groups = useGroups();
  const canWrite = hasAny(groups, WRITE_ROLES);
  const [params, setParams] = useSearchParams();
  const month = params.get("month") ?? currentMonthKey();
  const type = (params.get("type") ?? "") as EngagementType | "";
  const clientId = params.get("client_id") ?? "";
  const focus = (params.get("focus") ?? "") as Focus;

  const [view, setView] = useState<PortfolioForecast | null>(null);
  const [clients, setClients] = useState<ClientOption[]>([]);
  const [months, setMonths] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params);
      if (value) next.set(key, value);
      else next.delete(key);
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  useEffect(() => {
    let cancelled = false;
    listClientOptions().then((rows) => !cancelled && setClients(rows)).catch(() => undefined);
    listEngagements({ page_size: 100 })
      .then((page) => {
        if (cancelled || page.items.length === 0) return;
        const starts = page.items.map((e) => e.start.slice(0, 7)).sort();
        const ends = page.items.map((e) => e.end.slice(0, 7)).sort();
        const span = monthsBetween(starts[0], ends[ends.length - 1]);
        setMonths(span.includes(month) ? span : [...span, month].sort());
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [month]);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPortfolioForecast({ month, type, client_id: clientId })
      .then((data) => !cancelled && setView(data))
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [month, type, clientId]);

  useEffect(load, [load]);

  const rows = useMemo(() => {
    if (!view) return [];
    return focus === "below_floor" ? view.rows.filter((r) => r.status === "BELOW FLOOR") : view.rows;
  }, [view, focus]);

  const monthOptions = months.length ? months : [month];
  const floor = view?.project_floor_pct ?? null;
  const under = (value: number | null) => value !== null && floor !== null && value < floor;

  async function exportCsv() {
    setExporting(true);
    try {
      await downloadPortfolioCsv({ month, type, client_id: clientId });
    } catch (cause) {
      setError(cause);
    } finally {
      setExporting(false);
    }
  }

  function card(key: Focus, label: string, value: string, detail: string, negative = false) {
    const active = focus === key;
    return (
      <button
        type="button"
        key={key}
        data-testid={`card-${key}`}
        aria-pressed={active}
        onClick={() => {
          setParam("focus", active ? "" : key);
          const target = key === "rolloffs" ? "rolloffs" : key === "bench" ? "bench" : key === "gm" ? "totals" : "portfolio-table";
          document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
        className={cn(
          "rounded-card border bg-surface p-4 text-left transition-motion hover:border-primary focus-visible:outline-focus",
          active ? "border-primary" : "border-divider",
        )}
      >
        <div className="text-label uppercase tracking-wide text-text-secondary">{label}</div>
        <div className={cn("mt-1 font-display text-metric tnum", negative && "text-danger")}>{value}</div>
        <div className="mt-1 text-secondary text-text-secondary">{detail}</div>
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Portfolio forecast"
        subtitle={
          view
            ? `${view.rows.length} engagements · ${monthLabel(month)} · every number is computed by the forecast engine from the allocations ledger`
            : "Every number is computed by the forecast engine from the allocations ledger"
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-secondary text-text-secondary" htmlFor="pf-month">
              Month
            </label>
            <select
              id="pf-month"
              className="min-h-control rounded-control border border-input-border bg-surface px-2 text-body"
              value={month}
              onChange={(event) => setParam("month", event.target.value)}
            >
              {monthOptions.map((m) => (
                <option key={m} value={m}>
                  {monthLabel(m)}
                </option>
              ))}
            </select>
            <label className="text-secondary text-text-secondary" htmlFor="pf-type">
              Type
            </label>
            <select
              id="pf-type"
              className="min-h-control rounded-control border border-input-border bg-surface px-2 text-body"
              value={type}
              onChange={(event) => setParam("type", event.target.value)}
            >
              <option value="">All</option>
              {(Object.keys(ENGAGEMENT_TYPE_LABEL) as EngagementType[]).map((t) => (
                <option key={t} value={t}>
                  {ENGAGEMENT_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
            <label className="text-secondary text-text-secondary" htmlFor="pf-client">
              Client
            </label>
            <select
              id="pf-client"
              className="min-h-control rounded-control border border-input-border bg-surface px-2 text-body"
              value={clientId}
              onChange={(event) => setParam("client_id", event.target.value)}
            >
              <option value="">All</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={() => void exportCsv()} disabled={exporting || !view}>
              <Download className="mr-1 h-4 w-4" aria-hidden /> {exporting ? "Exporting…" : "Export CSV"}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => navigate("/settings/forecast")}>
              <Settings2 className="mr-1 h-4 w-4" aria-hidden /> Settings
            </Button>
            {canWrite ? (
              <Button size="sm" onClick={() => navigate("/engagements/new")}>
                <Plus className="mr-1 h-4 w-4" aria-hidden /> New engagement
              </Button>
            ) : null}
          </div>
        }
      />

      {error ? (
        <ErrorState title="We couldn't load the portfolio forecast." description={errorText(error, "Retry to try again.")} onRetry={load} />
      ) : loading && !view ? (
        <p role="status" className="text-body text-text-secondary">
          Loading portfolio forecast…
        </p>
      ) : view ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {card(
              "gm",
              `Portfolio GM · ${monthLabel(month)}`,
              pct(view.cards.portfolio_gm_pct),
              `${money(view.totals.revenue)} revenue · ${money(view.totals.cost)} cost`,
              under(view.cards.portfolio_gm_pct),
            )}
            {card(
              "below_floor",
              "Below floor",
              String(view.cards.below_floor),
              `engagements under ${pct(floor)} over their term`,
              view.cards.below_floor > 0,
            )}
            {card("rolloffs", "Roll-offs · next 60 days", String(view.cards.rolloffs_60d), "allocations ending with nothing after")}
            {card("bench", `Bench · ${monthLabel(month)}`, String(view.cards.bench), "active people with no allocation")}
          </div>

          {focus === "below_floor" ? (
            <p className="text-secondary text-text-secondary">
              Showing the {rows.length} engagement{rows.length === 1 ? "" : "s"} below the project floor.{" "}
              <button type="button" className="text-primary underline" onClick={() => setParam("focus", "")}>
                Show all
              </button>
            </p>
          ) : null}

          {view.rows.length === 0 ? (
            <EmptyState
              title={`No engagements in ${monthLabel(month)}`}
              description="Create an engagement, or pick another month."
              action={canWrite ? <Button onClick={() => navigate("/engagements/new")}>New engagement</Button> : undefined}
            />
          ) : (
            <div id="portfolio-table" className={tableWrap}>
              <table className={table} aria-label="Portfolio forecast">
                <thead>
                  <tr>
                    <th className={headCell}>Client</th>
                    <th className={headCell}>Engagement</th>
                    <th className={headCell}>Type</th>
                    <th className={headCell}>Term</th>
                    <th className={headCellNum}>People</th>
                    <th className={headCellNum}>Revenue · month</th>
                    <th className={headCellNum}>Cost · month</th>
                    <th className={headCellNum}>GM % · month</th>
                    <th className={headCellNum}>GM % · term</th>
                    <th className={headCell}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.engagement_id}
                      className="cursor-pointer hover:bg-primary-subtle"
                      onClick={() => navigate(`/engagements/${row.engagement_id}/forecast`)}
                    >
                      <td className={cn(textCell, "font-semibold")}>
                        <Link to={`/engagements/${row.engagement_id}/forecast`} className="text-text hover:underline" onClick={(e) => e.stopPropagation()}>
                          {row.client_name}
                        </Link>
                      </td>
                      <td className={textCell}>{row.name}</td>
                      <td className={textCell}>{ENGAGEMENT_TYPE_LABEL[row.type]}</td>
                      <td className={cn(textCell, "text-secondary text-text-secondary")}>
                        {row.start} → {row.end}
                      </td>
                      <td className={numCell}>{row.people}</td>
                      <td className={numCell}>{money(row.revenue_month)}</td>
                      <td className={numCell}>{money(row.cost_month)}</td>
                      <td className={cn(numCell, under(row.gm_pct_month) && "font-semibold text-danger")}>{pct(row.gm_pct_month)}</td>
                      <td className={cn(numCell, under(row.gm_pct_term) && "font-semibold text-danger")}>{pct(row.gm_pct_term)}</td>
                      <td className={textCell}>
                        <StatusPill status={row.status} />
                      </td>
                    </tr>
                  ))}
                  <tr id="totals" className={totalsRow} data-testid="portfolio-totals">
                    <td className={textCell} colSpan={4}>
                      Portfolio · {monthLabel(month)}
                    </td>
                    <td className={numCell}>{view.totals.people}</td>
                    <td className={numCell}>{money(view.totals.revenue)}</td>
                    <td className={numCell}>{money(view.totals.cost)}</td>
                    <td className={cn(numCell, under(view.totals.gm_pct) && "text-danger")}>{pct(view.totals.gm_pct)}</td>
                    <td className={numCell} />
                    <td className={textCell} />
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Panel
              id="rolloffs"
              title="Roll-offs in the next 60 days"
              hint="An allocation ending with no later allocation for the same person. Extend it, or plan the bench."
            >
              {view.rolloffs.length === 0 ? (
                <p className="text-secondary text-text-secondary">None in this window.</p>
              ) : (
                <div className={tableWrap}>
                  <table className={table} aria-label="Roll-offs">
                    <thead>
                      <tr>
                        <th className={headCell}>Client</th>
                        <th className={headCell}>Person</th>
                        <th className={headCell}>Role</th>
                        <th className={headCell}>Assignment</th>
                        <th className={headCell}>Ends</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.rolloffs.map((r) => (
                        <tr key={r.allocation_id} className="cursor-pointer hover:bg-primary-subtle" onClick={() => navigate(`/engagements/${r.engagement_id}/allocations`)}>
                          <td className={textCell}>{r.client}</td>
                          <td className={textCell}>{r.resource}</td>
                          <td className={textCell}>{r.role}</td>
                          <td className={textCell}>{r.assignment ?? "—"}</td>
                          <td className={cn(textCell, "text-secondary text-text-secondary")}>{r.end}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            <Panel id="bench" title={`Bench · ${monthLabel(month)}`} hint="People with no allocation in the month.">
              {view.bench_list.length === 0 ? (
                <p className="text-secondary text-text-secondary">Everyone is allocated this month.</p>
              ) : (
                <div className={tableWrap}>
                  <table className={table} aria-label="Bench">
                    <thead>
                      <tr>
                        <th className={headCell}>Person</th>
                        <th className={headCell}>Location</th>
                        <th className={headCell}>Type</th>
                        <th className={headCell}>Seniority</th>
                        <th className={headCell}>Free from</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.bench_list.map((b) => (
                        <tr key={b.resource_id}>
                          <td className={textCell}>{b.resource}</td>
                          <td className={textCell}>{b.location}</td>
                          <td className={textCell}>{EMPLOYMENT_TYPE_LABEL[b.employment_type]}</td>
                          <td className={textCell}>{b.seniority ?? "—"}</td>
                          <td className={cn(textCell, "text-secondary text-text-secondary")}>{b.free_from}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
