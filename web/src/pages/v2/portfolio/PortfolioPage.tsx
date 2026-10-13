/**
 * /portfolio and /portfolio/:bu — Portfolio forecast (S22 P3-1 … P3-3, P5-5),
 * copied from the prototype (v4).
 *
 * Business-unit tabs above the cards (All business units / ST21 / IT Avalon /
 * Retro Rabbit, each its own URL). Month picker, type and client filters, the
 * five signal cards, the table — in the "All" view grouped by BU with a
 * subtotal row per BU (from the server's `groups`) and the grand total (from
 * `totals`); on a BU tab its rows and the one subtotal — the roll-offs and
 * bench panels (names, never ids), CSV export. Every number is the engine's,
 * served by GET /portfolio/forecast; the browser never adds anything up.
 *
 * Cards deep-link to the list they count: Portfolio GM → the totals row,
 * Below floor → the table filtered to BELOW FLOOR rows, Roll-offs → the
 * roll-offs panel, Bench → the bench panel. Billing loss has no list of its
 * own (actuals live on each engagement's Forecast tab), so it is a plain card.
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Download, Plus, Settings2 } from "lucide-react";
import {
  BUS,
  BU_FROM_SLUG,
  BU_SLUG,
  ENGAGEMENT_TYPE_LABEL,
  EMPLOYMENT_TYPE_LABEL,
  downloadPortfolioCsv,
  getPortfolioForecast,
  listClientOptions,
  listEngagements,
  type BusinessUnit,
  type ClientOption,
  type EngagementType,
  type PortfolioForecast,
  type PortfolioGroup,
  type PortfolioRow,
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

const COLUMNS = 10;

export function PortfolioPage() {
  const { bu: slug } = useParams<{ bu?: string }>();
  const bu: BusinessUnit | "" = slug ? (BU_FROM_SLUG[slug] ?? "") : "";
  if (slug && !bu) return <Navigate to="/portfolio" replace />;
  return <PortfolioView bu={bu} />;
}

function PortfolioView({ bu }: { bu: BusinessUnit | "" }) {
  const navigate = useNavigate();
  const groups = useGroups();
  const canWrite = hasAny(groups, WRITE_ROLES);
  const [params, setParams] = useSearchParams();
  const month = params.get("month") ?? currentMonthKey();
  const type = (params.get("type") ?? "") as EngagementType | "";
  const clientId = params.get("client_id") ?? "";
  const focus = (params.get("focus") ?? "") as Focus;

  const [view, setView] = useState<PortfolioForecast | null>(null);
  /** The all-BU response for the tab counts when a BU tab is open (same month/type/client). */
  const [allView, setAllView] = useState<PortfolioForecast | null>(null);
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

  function goToBu(next: BusinessUnit | "") {
    const query = params.toString();
    navigate(`${next ? `/portfolio/${BU_SLUG[next]}` : "/portfolio"}${query ? `?${query}` : ""}`);
  }

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
    getPortfolioForecast({ month, business_unit: bu, type, client_id: clientId })
      .then((data) => {
        if (cancelled) return;
        setView(data);
        if (!bu) setAllView(data);
      })
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setLoading(false));
    if (bu) {
      getPortfolioForecast({ month, type, client_id: clientId })
        .then((data) => !cancelled && setAllView(data))
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [month, bu, type, clientId]);

  useEffect(load, [load]);

  const rows = useMemo(() => {
    if (!view) return [];
    return focus === "below_floor" ? view.rows.filter((r) => r.status === "BELOW FLOOR") : view.rows;
  }, [view, focus]);

  const serverGroups: PortfolioGroup[] = view?.groups ?? [];
  const monthOptions = months.length ? months : [month];
  const floor = view?.project_floor_pct ?? null;
  const under = (value: number | null) => value !== null && floor !== null && value < floor;
  const billingLoss = view?.cards.billing_loss;

  /** Tab counts: the server's per-BU engagement counts; "All" is the number of rows it returned. */
  const tabCount = (unit: BusinessUnit | ""): string => {
    if (!allView) return "";
    if (!unit) return String(allView.rows.length);
    const group = allView.groups?.find((g) => g.business_unit === unit);
    return String(group?.engagements ?? 0);
  };

  async function exportCsv() {
    setExporting(true);
    try {
      await downloadPortfolioCsv({ month, business_unit: bu, type, client_id: clientId });
    } catch (cause) {
      setError(cause);
    } finally {
      setExporting(false);
    }
  }

  const cardFrame = "rounded-card border bg-surface p-4 text-left transition-motion";

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
        className={cn(cardFrame, "hover:border-primary focus-visible:outline-focus", active ? "border-primary" : "border-divider")}
      >
        <div className="text-label uppercase tracking-wide text-text-secondary">{label}</div>
        <div className={cn("mt-1 font-display text-metric tnum", negative && "text-danger")}>{value}</div>
        <div className="mt-1 text-secondary text-text-secondary">{detail}</div>
      </button>
    );
  }

  const rowHtml = (row: PortfolioRow) => (
    <tr
      key={row.engagement_id}
      data-testid="portfolio-row"
      data-bu={row.business_unit}
      className="cursor-pointer hover:bg-primary-subtle"
      onClick={() => navigate(`/engagements/${row.engagement_id}/forecast`)}
    >
      <td className={cn(textCell, "font-semibold")}>
        <Link to={`/engagements/${row.engagement_id}/forecast`} className="text-text hover:underline" onClick={(e) => e.stopPropagation()}>
          {row.client_name}
        </Link>
      </td>
      <td className={textCell}>
        {row.name}
        <div className="text-secondary text-text-secondary" data-testid="row-owners">
          {row.sales_owner ?? "—"} · {row.delivery_owner ?? "—"}
        </div>
      </td>
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
  );

  /** A BU's subtotal row — every number is the server's `groups` entry. */
  const subtotalRow = (group: PortfolioGroup, label: string, id?: string) => (
    <tr key={`sub-${group.business_unit}`} id={id} className={cn(totalsRow, "bg-surface-sunken/60")} data-testid="bu-subtotal" data-bu={group.business_unit}>
      <td className={textCell} colSpan={4}>
        {label}
      </td>
      <td className={numCell} data-testid="subtotal-people">
        {group.people}
      </td>
      <td className={numCell} data-testid="subtotal-revenue">
        {money(group.revenue)}
      </td>
      <td className={numCell} data-testid="subtotal-cost">
        {money(group.cost)}
      </td>
      <td className={cn(numCell, under(group.gm_pct) && "text-danger")} data-testid="subtotal-gm">
        {pct(group.gm_pct)}
      </td>
      <td className={cn(numCell, group.below_floor > 0 && "text-danger")} data-testid="subtotal-below-floor">
        {group.below_floor > 0 ? `${group.below_floor} below floor` : ""}
      </td>
      <td className={textCell} />
    </tr>
  );

  const grandTotalRow = (v: PortfolioForecast) => (
    <tr id="totals" className={totalsRow} data-testid="portfolio-total">
      <td className={textCell} colSpan={4}>
        All business units · {monthLabel(month)}
      </td>
      <td className={numCell} data-testid="total-people">
        {v.totals.people}
      </td>
      <td className={numCell} data-testid="total-revenue">
        {money(v.totals.revenue)}
      </td>
      <td className={numCell} data-testid="total-cost">
        {money(v.totals.cost)}
      </td>
      <td className={cn(numCell, under(v.totals.gm_pct) && "text-danger")} data-testid="total-gm">
        {pct(v.totals.gm_pct)}
      </td>
      <td className={numCell} />
      <td className={textCell} />
    </tr>
  );

  function tableBody(v: PortfolioForecast) {
    if (bu) {
      // One BU tab: its rows and the one subtotal (groups[0]); the subtotal is the GM card's target.
      const group = serverGroups.find((g) => g.business_unit === bu) ?? serverGroups[0];
      return (
        <>
          {rows.map(rowHtml)}
          {group ? subtotalRow(group, `${bu} · ${monthLabel(month)}`, "totals") : null}
        </>
      );
    }
    if (focus === "below_floor") {
      // The filtered list is flat — a BU subtotal would describe rows that are hidden.
      return (
        <>
          {rows.map(rowHtml)}
          {grandTotalRow(v)}
        </>
      );
    }
    return (
      <>
        {serverGroups.map((group) => {
          const groupRows = rows.filter((r) => r.business_unit === group.business_unit);
          return (
            <Fragment key={group.business_unit}>
              <tr className="bg-surface-sunken/40" data-testid="bu-group" data-bu={group.business_unit}>
                <td className={cn(textCell, "font-semibold")} colSpan={COLUMNS}>
                  {group.business_unit} <span className="font-normal text-text-secondary">· {group.engagements} engagement{group.engagements === 1 ? "" : "s"}</span>
                </td>
              </tr>
              {groupRows.map(rowHtml)}
              {subtotalRow(group, `${group.business_unit} subtotal · ${monthLabel(month)}`)}
            </Fragment>
          );
        })}
        {grandTotalRow(v)}
      </>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2" data-testid="bu-tabs" role="group" aria-label="Business units">
        {([["", "All business units"], ...BUS.map((b) => [b, b] as const)] as const).map(([value, label]) => {
          const selected = bu === value;
          return (
            <button
              key={value || "all"}
              type="button"
              data-testid="bu-tab"
              data-bu={value}
              aria-label={label}
              aria-pressed={selected}
              onClick={() => goToBu(value as BusinessUnit | "")}
              className={cn(
                "inline-flex min-h-control items-center gap-2 rounded-chip border px-3 text-body transition-motion focus-visible:outline-focus",
                selected ? "border-primary bg-primary text-primary-fg" : "border-input-border bg-surface text-text hover:bg-primary-subtle",
              )}
            >
              <span>{label}</span>
              <span className={cn("tnum text-secondary", selected ? "text-primary-fg/80" : "text-text-secondary")} data-testid="bu-tab-count">
                {tabCount(value as BusinessUnit | "")}
              </span>
            </button>
          );
        })}
      </div>

      <PageHeader
        title={bu ? `${bu} forecast` : "Portfolio forecast"}
        subtitle={
          view
            ? `${view.rows.length} engagements · the month columns show only ${monthLabel(month)}'s slice of each engagement (partial months prorated by days); "whole term" is the engagement's full GM`
            : "The month columns show only the selected month's slice of each engagement; \"whole term\" is the engagement's full GM"
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
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
            <div className={cn(cardFrame, "border-divider")} data-testid="card-billing-loss">
              <div className="text-label uppercase tracking-wide text-text-secondary">Billing loss · months with actuals</div>
              <div className={cn("mt-1 font-display text-metric tnum", billingLoss && billingLoss.engagements > 0 && Number(billingLoss.amount) > 0 && "text-danger")}>
                {billingLoss && billingLoss.engagements > 0 ? money(billingLoss.amount) : "—"}
              </div>
              <div className="mt-1 text-secondary text-text-secondary">
                {billingLoss && billingLoss.engagements > 0
                  ? `${money(billingLoss.forecast)} forecast vs ${money(billingLoss.billed)} billed · ${billingLoss.engagements} engagement${billingLoss.engagements === 1 ? "" : "s"} with actuals`
                  : "no actuals loaded yet"}
              </div>
            </div>
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
              title={`No ${bu ? `${bu} ` : ""}engagements in ${monthLabel(month)}`}
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
                    <th className={headCellNum}>Revenue · {monthLabel(month)}</th>
                    <th className={headCellNum}>Cost · {monthLabel(month)}</th>
                    <th className={headCellNum}>GM % · {monthLabel(month)}</th>
                    <th className={headCellNum}>GM % · whole term</th>
                    <th className={headCell}>Status</th>
                  </tr>
                </thead>
                <tbody>{tableBody(view)}</tbody>
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
