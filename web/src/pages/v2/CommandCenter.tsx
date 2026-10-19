import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  Download,
  RefreshCw,
  Search,
  Users,
  X,
} from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { getPipelineFacets, type PipelineFacets } from "../../api/client";
import {
  downloadCommandAccounts,
  getCommandAccounts,
  getCommandOverview,
  type CommandAccountRow,
  type CommandAccountsPage,
  type CommandFocus,
  type CommandOverview,
  type CommandPeriod,
  type CommandScope,
} from "../../api/commandCenter";
import { useAuth } from "../../auth/AuthProvider";
import { cn } from "../../lib/cn";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../ui-v2/primitives/sheet";

const button = "inline-flex min-h-9 items-center justify-center gap-2 rounded-control border border-border bg-surface px-3 text-body font-medium text-text transition-motion hover:border-primary focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50";
const panel = "min-w-0 overflow-hidden rounded-card border border-border bg-surface";

function money(value: string | null | undefined, currency: string, missing = "Not recorded"): string {
  if (value === null || value === undefined || value === "") return missing;
  const number = Number(value);
  if (!Number.isFinite(number)) return missing;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
    notation: Math.abs(number) >= 1_000_000 ? "compact" : "standard",
  }).format(number);
}

function percentage(value: string | null | undefined, missing = "Not calculated"): string {
  if (value === null || value === undefined || value === "") return missing;
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : missing;
}

function shortDate(value: string | null): string {
  if (!value) return "No due date recorded";
  const parsed = new Date(`${value}${value.length === 10 ? "T12:00:00" : ""}`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function monthLabel(value: string | null): string {
  if (!value) return "No actual month recorded";
  const [year, month] = value.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

function dateTimeLabel(value: string | null): string {
  if (!value) return "cutoff not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
}

function moneyChange(value: string | null, currency: string, basis: string): string {
  if (value === null) return basis;
  const amount = Number(value);
  return `${amount > 0 ? "+" : ""}${money(value, currency)} ${basis}`;
}

function SectionState({ text }: { text: string }) {
  return <div className="px-5 py-8 text-center text-body text-text-muted">{text}</div>;
}

function PanelHeader({ id, title, note, action }: { id?: string; title: string; note?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 pb-3 pt-5">
      <div>
        <h2 id={id} className="text-section font-semibold text-text">{title}</h2>
        {note ? <p className="mt-1 text-secondary text-text-muted">{note}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function CommandCenterPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [url, setUrl] = useSearchParams();
  const businessUnit = url.get("bu") ?? "";
  const ownerId = url.get("owner") ?? "";
  const period = (url.get("period") ?? "this_quarter") as CommandPeriod;
  const currency = url.get("currency") ?? "USD";
  const focus = (url.get("focus") ?? "leadership") as CommandFocus;
  const health = url.get("health") ?? "all";
  const search = url.get("search") ?? "";
  const pageNumber = Math.max(1, Number(url.get("page") ?? "1"));
  const scope = useMemo<CommandScope>(
    () => ({ business_unit: businessUnit || undefined, owner_id: ownerId || undefined, period, currency, focus }),
    [businessUnit, ownerId, period, currency, focus],
  );

  const [overview, setOverview] = useState<CommandOverview | null>(null);
  const [accounts, setAccounts] = useState<CommandAccountsPage | null>(null);
  const [facets, setFacets] = useState<PipelineFacets | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [selected, setSelected] = useState<CommandAccountRow | null>(null);
  const [queueMode, setQueueMode] = useState<"team" | "mine">("team");
  const [scenario, setScenario] = useState<"committed" | "expected" | "upside">("expected");

  const setParam = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(url);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setUrl(next, { replace: true });
  }, [setUrl, url]);

  const loadOverview = useCallback(() => {
    setOverviewLoading(true);
    setOverviewError(null);
    getCommandOverview(scope)
      .then(setOverview)
      .catch((error) => setOverviewError(error instanceof Error ? error.message : String(error)))
      .finally(() => setOverviewLoading(false));
  }, [scope]);
  const loadAccounts = useCallback(() => {
    setAccountsLoading(true);
    setAccountsError(null);
    getCommandAccounts(scope, { search: search || undefined, health, page: pageNumber, page_size: 25 })
      .then(setAccounts)
      .catch((error) => setAccountsError(error instanceof Error ? error.message : String(error)))
      .finally(() => setAccountsLoading(false));
  }, [scope, search, health, pageNumber]);

  useEffect(loadOverview, [loadOverview]);
  useEffect(loadAccounts, [loadAccounts]);
  useEffect(() => {
    getPipelineFacets({ include_closed: true })
      .then(setFacets)
      .catch(() => setFacets({ owners: [], business_units: [] }));
  }, []);

  const activeChips = [
    businessUnit ? { key: "bu", label: businessUnit } : null,
    ownerId ? { key: "owner", label: facets?.owners.find((owner) => owner.id === ownerId)?.name ?? "Selected owner" } : null,
    period !== "this_quarter" ? { key: "period", label: "Next two quarters" } : null,
    currency !== "USD" ? { key: "currency", label: currency } : null,
    focus !== "leadership" ? { key: "focus", label: `${focus} focus` } : null,
  ].filter(Boolean) as Array<{ key: string; label: string }>;
  const queue = (overview?.actions ?? []).filter((item) => queueMode === "team" || item.owner === user?.name);
  const maximumRevenue = Math.max(1, ...(overview?.revenue.months ?? []).map((row) => Number(
    scenario === "committed" ? row.committed_total : scenario === "expected" ? row.expected_total : row.upside_total,
  )));
  const returnTo = `${location.pathname}${location.search}`;

  return (
    <div className="flex flex-col gap-5 pb-8" data-testid="command-center">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase text-primary">
            {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
          </p>
          <h1 className="mt-1 text-[28px] font-semibold text-text">Command Center</h1>
          <p className="mt-1 text-body text-text-secondary">Know what needs you. See what comes next.</p>
        </div>
        <div className="flex items-center gap-2">
          <Link className={button} to="/settings/system-health">Data status</Link>
          <Link className={cn(button, "border-primary bg-primary text-white hover:text-white")} to="/sows/new">New SOW</Link>
        </div>
      </header>

      <section className={cn(panel, "overflow-visible p-3")} aria-label="Dashboard scope">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[1.25fr_1.25fr_1.4fr_1fr_1fr_auto]">
          <Filter label="Business unit" value={businessUnit} onChange={(value) => setParam("bu", value)}>
            <option value="">All business units</option>
            {(facets?.business_units ?? []).map((value) => <option key={value}>{value}</option>)}
          </Filter>
          <Filter label="Account owner" value={ownerId} onChange={(value) => setParam("owner", value)}>
            <option value="">All owners</option>
            {(facets?.owners ?? []).map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}
          </Filter>
          <Filter label="Financial period" value={period} onChange={(value) => setParam("period", value)}>
            <option value="this_quarter">This quarter</option><option value="next_two_quarters">Next two quarters</option>
          </Filter>
          <Filter label="Currency" value={currency} onChange={(value) => setParam("currency", value)}>
            <option value="USD">USD</option><option value="INR">INR</option><option value="EUR">EUR</option><option value="GBP">GBP</option>
          </Filter>
          <Filter label="Focus" value={focus} onChange={(value) => setParam("focus", value)}>
            <option value="leadership">Leadership</option><option value="delivery">Delivery</option><option value="sales">Sales</option><option value="finance">Finance</option>
          </Filter>
          <button className={button} onClick={() => { loadOverview(); loadAccounts(); }} aria-label="Refresh Command Center">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </section>

      <div className="flex min-h-7 flex-wrap items-center gap-2">
        {activeChips.map((chip) => (
          <button key={chip.key} className="inline-flex min-h-7 items-center gap-1 rounded-control bg-primary-subtle px-2 text-secondary font-medium text-primary" onClick={() => setParam(chip.key, "")}>
            {chip.label}<X className="h-3 w-3" aria-hidden />
          </button>
        ))}
        {activeChips.length ? (
          <button className="text-secondary font-medium text-primary" onClick={() => setUrl(new URLSearchParams(), { replace: true })}>Reset user filters</button>
        ) : <span className="text-secondary text-text-muted">All authorized business records</span>}
      </div>

      {overviewLoading ? <SectionState text="Loading business evidence…" /> : overviewError ? (
        <div className={panel}><SectionState text={`Could not load actions: ${overviewError}`} /></div>
      ) : overview ? <ActionTiles overview={overview} currency={currency} scoped={Boolean(businessUnit || ownerId)} /> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        <section className={panel} aria-labelledby="attention-title">
          <PanelHeader id="attention-title" title="Needs attention" note="Financial actions ranked by comparable impact, urgency and category" action={<Segment options={[["team", "Team"], ["mine", "Assigned to me"]]} value={queueMode} onChange={(value) => setQueueMode(value as "team" | "mine")} />} />
          {queue.length === 0 ? <SectionState text="No actions need attention in this scope." /> : (
            <div className="divide-y divide-divider">
              {queue.slice(0, 8).map((item) => (
                <Link key={item.id} to={item.href} state={{ from: returnTo }} className="grid grid-cols-[4px_minmax(0,1fr)_auto] items-center gap-3 px-5 py-3 hover:bg-canvas">
                  <span className={cn("h-10 rounded-full", item.rank <= 3 ? "bg-danger" : "bg-warning")} aria-hidden />
                  <span className="min-w-0">
                    <strong className="block truncate text-body text-text">{item.account} · {item.title}</strong>
                    <span className="block text-secondary text-text-secondary">{item.detail}</span>
                    <small className="mt-1 block text-text-muted">{item.owner ?? "Owner not recorded"} · {shortDate(item.due)}{item.period ? ` · ${item.period}` : ""}</small>
                  </span>
                  <span className="text-right">
                    <strong className="block text-body text-text">{item.impact ? money(item.impact, currency) : item.missing_input ?? "Impact not calculable"}</strong>
                    <small className="block text-text-muted">{item.impact_label ?? item.category}</small>
                    <span className="mt-1 inline-flex items-center gap-1 text-secondary font-medium text-primary">{item.action}<ArrowRight className="h-3 w-3" /></span>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </section>
        <aside className="rounded-card border border-primary/20 bg-primary-subtle p-5">
          <p className="text-[11px] font-semibold uppercase text-primary">Operating brief</p>
          <h2 className="mt-2 text-[18px] font-semibold text-text">Three facts to act on</h2>
          <div className="mt-5 space-y-4 text-body">
            {(overview?.brief ?? []).map((item) => (
              <MaybeLink key={item.kind} to={item.href} className="grid grid-cols-[20px_1fr] gap-2 rounded-control p-1" hoverClassName="hover:bg-surface">
                <span className="text-primary">{item.kind === "risk" ? <AlertTriangle className="h-4 w-4" /> : item.kind === "opportunity" ? <BriefcaseBusiness className="h-4 w-4" /> : <Users className="h-4 w-4" />}</span>
                <span><strong className="block text-body text-text">{item.title}</strong><small className="text-text-secondary">{item.detail}</small></span>
              </MaybeLink>
            ))}
          </div>
        </aside>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,1fr)]">
        <RevenueOutlook overview={overview} currency={currency} scenario={scenario} onScenario={setScenario} maximum={maximumRevenue} period={period} />
        <CapacityPanel capacity={overview?.capacity ?? null} />
      </div>

      <section aria-labelledby="lifecycle-title">
        <div className="mb-2 flex items-center justify-between">
          <h2 id="lifecycle-title" className="text-section font-semibold">From opportunity to delivery</h2>
          <span className="text-secondary text-text-muted">Overlapping entity populations, not an additive funnel</span>
        </div>
        <div className="grid overflow-hidden rounded-card border border-border bg-surface sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {(overview?.lifecycle_items ?? []).map((item) => (
            <MaybeLink key={item.key} to={item.href} state={{ from: returnTo }} className="min-h-24 border-b border-r border-divider p-3" hoverClassName="hover:bg-primary-subtle">
              <span className="block min-h-8 text-secondary text-text-muted">{item.label}</span>
              <strong className="mt-1 block text-[22px] text-text">{item.count}</strong>
              <small className="text-text-muted">{item.entity}</small>
            </MaybeLink>
          ))}
        </div>
      </section>

      <section className={panel} aria-labelledby="accounts-title">
        <PanelHeader id="accounts-title" title="Accounts & engagements" note="Open late-stage work, current-period wins and active delivery." action={<button className="inline-flex min-h-8 items-center gap-1 text-secondary font-medium text-primary" onClick={() => void downloadCommandAccounts(scope, search || undefined, health)}><Download className="h-4 w-4" /> Export this view</button>} />
        <div className="flex flex-wrap items-center gap-2 px-5 pb-3">
          <span className="rounded-control bg-primary-subtle px-2 py-1 text-[11px] font-semibold text-primary" data-testid="stage5-scope">HubSpot deals · Stage 5 and above</span>
          <Segment options={[["all", "All"], ["at_risk", "At risk"], ["watching", "Watching"]]} value={health} onChange={(value) => setParam("health", value)} />
          <select aria-label="Filter accounts by business unit" className="h-9 min-w-44 rounded-control border border-border bg-surface px-2 text-body text-text focus-visible:outline-focus" value={businessUnit} onChange={(event) => setParam("bu", event.target.value)}>
            <option value="">All business units</option>{(facets?.business_units ?? []).map((value) => <option key={value}>{value}</option>)}
          </select>
          <label className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
            <span className="sr-only">Find an account or engagement</span>
            <input className="h-9 w-full rounded-control border border-border bg-surface pl-9 pr-3 text-body focus-visible:outline-focus" type="search" value={search} onChange={(event) => setParam("search", event.target.value)} placeholder="Find an account or engagement…" />
          </label>
        </div>
        {accounts?.configuration_gaps.length ? <div className="mx-5 mb-3 rounded-control border border-warning/30 bg-warning-surface px-3 py-2 text-secondary text-warning">{accounts.configuration_gaps.join(" · ")}</div> : null}
        {accountsLoading ? <SectionState text="Loading eligible HubSpot deals…" /> : accountsError ? <SectionState text={`Could not load accounts: ${accountsError}`} /> : !accounts?.items.length ? <SectionState text="No current Stage 5 or later HubSpot deals match these filters." /> : <AccountsTable rows={accounts.items} currency={currency} onSelect={setSelected} />}
        <div className="flex items-center justify-between border-t border-divider px-5 py-3 text-secondary text-text-muted">
          <span>{accounts ? `${accounts.total} eligible deal${accounts.total === 1 ? "" : "s"}` : "Loading count"}</span>
          <div className="flex items-center gap-2">
            <button className={button} disabled={pageNumber <= 1} onClick={() => setParam("page", String(pageNumber - 1))}>Previous</button>
            <span>Page {pageNumber} of {Math.max(1, Math.ceil((accounts?.total ?? 0) / 25))}</span>
            <button className={button} disabled={!accounts || pageNumber * 25 >= accounts.total} onClick={() => setParam("page", String(pageNumber + 1))}>Next</button>
          </div>
        </div>
      </section>

      <section className={panel}>
        <PanelHeader title="Data & operational health" note="Source status is separate from business performance." action={<Link className="text-secondary font-medium text-primary" to="/settings/system-health">Inspect</Link>} />
        {overview?.configuration_gaps.length ? <div className="mx-5 mb-3 rounded-control border border-warning/30 bg-warning-surface px-3 py-2 text-secondary text-warning">{overview.configuration_gaps.join(" · ")}</div> : null}
        {overview?.sources.map((source) => (
          <div key={source.name} className="flex items-center justify-between gap-4 border-t border-divider px-5 py-3">
            <span><strong className="block text-body">{source.name}</strong><small className="text-text-muted">{source.detail}</small></span>
            <span className={cn("inline-flex items-center gap-1 rounded-control px-2 py-1 text-[11px] font-medium", source.status === "current" ? "bg-success-surface text-success" : source.status === "attention" ? "bg-warning-surface text-warning" : "bg-canvas text-text-muted")}><span className="h-1.5 w-1.5 rounded-full bg-current" />{source.status}</span>
          </div>
        ))}
      </section>
      {selected ? <AccountDrawer row={selected} currency={currency} returnTo={returnTo} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

function ActionTiles({ overview, currency, scoped }: { overview: CommandOverview; currency: string; scoped: boolean }) {
  const { revenue, gm, backlog, pipeline, people } = overview.tiles;
  const { open_opportunity_value: openValue, open_opportunity_count: openCount, open_opportunity_href: openHref, open_opportunity_business_units: openUnits } = overview.metrics;
  // S24-AG1 F7: shown only when the API sends the count (an older API, mid-deploy, still renders).
  const agreementAttention = overview.metrics.agreement_attention_clients;
  // The Pipeline filters whole business units, so a Command Center region opens (and counts) its unit.
  // (`?? []`: an API from before this field, during a deploy, still renders.)
  const unitScope = businessUnitScope(openUnits ?? []);
  return (
    <section aria-labelledby="questions-title">
      <div className="mb-2 flex items-center justify-between"><h2 id="questions-title" className="text-section font-semibold">Business now</h2><span className="text-secondary text-text-muted">{overview.scope.months[0]} reporting basis · {currency}</span></div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Tile href={revenue.href} label="Revenue this month" value={money(revenue.forecast, currency)} note={revenue.actual_to_date === null ? `No current-month actuals · latest ${monthLabel(revenue.latest_actual_month)} ${money(revenue.latest_actual, currency)}` : `${money(revenue.actual_to_date, currency)} actual through ${dateTimeLabel(revenue.actual_cutoff)}`} comparison={moneyChange(revenue.comparison.value, currency, revenue.comparison.basis)} detail={revenue.last_closed_billing_loss === null ? "Billing loss not recorded" : `${money(revenue.last_closed_billing_loss, currency)} billing loss in latest actual month`} />
        <Tile href={gm.href} label="GM this month" value={percentage(gm.value)} note={`${gm.covered_engagements} of ${gm.total_engagements} engagements have complete financial inputs`} comparison={gm.comparison.value === null ? gm.comparison.basis : `${(Number(gm.comparison.value) * 100).toFixed(1)} pp ${gm.comparison.basis}`} detail={`${percentage(gm.revenue_coverage_pct)} revenue covered · ${gm.confirmed_cost_engagements} confirmed · ${gm.estimated_cost_engagements} default estimate`} warning={gm.missing_cost_engagements > 0} />
        <Tile href={backlog.href} label="Signed backlog" value={money(backlog.amount, currency)} note={`${backlog.engagements} engagement${backlog.engagements === 1 ? "" : "s"} through effective end dates`} comparison={backlog.comparison.basis} detail="Recognized revenue excluded" />
        <Tile href={openHref} label="Open opportunity value" value={money(openValue, "USD")} note={`${openCount} open deal${openCount === 1 ? "" : "s"}${unitScope} · Hold included · unweighted`} comparison={openHref ? "Same number as the Pipeline" : "Not on the Pipeline: this owner has no HubSpot link"} detail="USD deals; other currencies are not converted" />
        <Tile href={pipeline.href} label={pipeline.label} value={money(pipeline.weighted, currency)} note={`Weighted · ${pipeline.eligible_deals} open deal${pipeline.eligible_deals === 1 ? "" : "s"} · ${money(pipeline.gross, currency)} gross`} linkNote={pipeline.href ? `Pipeline list: open deals with no SOW${unitScope}. This tile is weighted and leaves out deals linked to an engagement.` : undefined} comparison={pipeline.comparison.basis} detail={`${money(pipeline.unscheduled_weighted, currency)} unscheduled · ${pipeline.closed_won_gaps} closed-won gap${pipeline.closed_won_gaps === 1 ? "" : "s"}`} warning={pipeline.missing.length > 0} />
        {typeof agreementAttention === "number" ? (
          <Tile
            href={overview.metrics.agreement_attention_href ?? null}
            label={AGREEMENT_TILE_LABEL}
            value={String(agreementAttention)}
            note="Warn and flag only. Nothing is blocked anywhere."
            detail={scoped ? "Counts every client: the business unit and owner selected here do not apply" : "Counts every client"}
            comparison="Opens NDA & MSA filtered to “Needs attention”"
            warning={agreementAttention > 0}
          />
        ) : null}
        <div className="min-h-40 rounded-card border border-border bg-surface p-4">
          <span className="block text-secondary text-text-muted">People</span><strong className="my-2 block text-[23px] text-text">{people.billable_people} billable</strong>
          <div className="space-y-1 text-secondary"><Link className="block text-primary" to={people.billable_href}>{people.billable_fte} FTE allocated</Link><Link className="block text-primary" to={people.bench_href}>{people.bench_people === null ? "Bench not attributable in this scope" : `${people.bench_people} on bench`}</Link><Link className="block text-primary" to={people.rolloff_href}>{people.rolloffs_60_days} roll-offs in 60 days</Link><span className="block text-text-muted">{people.open_seats} open seats · {people.open_seat_fte} FTE</span><small className="block font-medium text-primary">{people.comparison.value > 0 ? "+" : ""}{people.comparison.value} {people.comparison.basis}</small></div>
        </div>
      </div>
    </section>
  );
}

/** S24-AG1 F7 · the directive's tile label (the prototype: "net-new clients are past stage 1 without an NDA or MSA"). */
const AGREEMENT_TILE_LABEL = "Net-new clients past stage 1 without an NDA or MSA";

function Tile({ href, label, value, note, comparison, detail, linkNote, warning = false }: { href: string | null; label: string; value: string; note: string; comparison: string; detail: string; linkNote?: string; warning?: boolean }) {
  return <MaybeLink to={href} testId="tile" className={cn("min-h-40 rounded-card border bg-surface p-4", warning ? "border-warning/40" : "border-border")} hoverClassName="hover:border-primary"><span className="block text-secondary text-text-muted">{label}</span><strong className="my-2 block text-[23px] text-text">{value}</strong><span className="block text-secondary text-text-secondary">{note}</span><small className="mt-2 block text-text-muted">{detail}</small>{linkNote ? <small className="mt-2 block text-text-muted">{linkNote}</small> : null}<small className={cn("mt-2 block font-medium", href ? "text-primary" : "text-text-muted")}>{comparison}</small></MaybeLink>;
}

/** A link when there is a list to open; the same content, unlinked, when the Pipeline cannot list the scope. */
function MaybeLink({ to, state, testId, className, hoverClassName, children }: { to: string | null; state?: unknown; testId?: string; className: string; hoverClassName: string; children: ReactNode }) {
  return to
    ? <Link to={to} state={state} data-testid={testId} className={cn(className, hoverClassName)}>{children}</Link>
    : <div data-testid={testId} className={className}>{children}</div>;
}

/** " in IT Avalon", " with no business unit": the Pipeline business units an open number covers. */
function businessUnitScope(units: string[]): string {
  const named = units.filter((unit) => unit !== "unmapped");
  const parts = [...(named.length ? [`in ${named.join(" or ")}`] : []), ...(units.includes("unmapped") ? ["with no business unit"] : [])];
  return parts.length ? ` ${parts.join(" or ")}` : "";
}

function RevenueOutlook({ overview, currency, scenario, onScenario, maximum, period }: { overview: CommandOverview | null; currency: string; scenario: "committed" | "expected" | "upside"; onScenario: (value: "committed" | "expected" | "upside") => void; maximum: number; period: CommandPeriod }) {
  return <section className={panel} aria-labelledby="revenue-title"><PanelHeader id="revenue-title" title="Revenue outlook" note={`${period === "this_quarter" ? "3-month" : "6-month"} cumulative scenarios`} action={<Segment options={[["committed", "Committed"], ["expected", "+ Expected renewal"], ["upside", "+ Pipeline upside"]]} value={scenario} onChange={(value) => onScenario(value as typeof scenario)} />} /><div className="flex h-52 items-end gap-4 border-b border-divider px-5" role="img" aria-label="Cumulative revenue outlook by month">{(overview?.revenue.months ?? []).map((row) => { const total = Number(scenario === "committed" ? row.committed_total : scenario === "expected" ? row.expected_total : row.upside_total); const committed = Number(row.committed); const renewal = scenario === "committed" ? 0 : Number(row.expected_renewal); const pipeline = scenario === "upside" ? Number(row.pipeline_upside) : 0; return <div key={row.month} className="flex h-full min-w-0 flex-1 flex-col justify-end"><div className="mb-1 truncate text-center text-[10px] font-medium text-text">{money(String(total), currency)}</div><div className="mx-auto flex w-full max-w-12 flex-col-reverse overflow-hidden rounded-t-control" style={{ height: `${Math.max(2, (total / maximum) * 100)}%` }}><span className="bg-primary" style={{ height: `${(committed / Math.max(1, total)) * 100}%` }} /><span className="bg-success" style={{ height: `${(renewal / Math.max(1, total)) * 100}%` }} /><span className="bg-warning/70" style={{ height: `${(pipeline / Math.max(1, total)) * 100}%` }} /></div><span className="mt-2 truncate text-center text-[10px] text-text-muted">{monthLabel(row.month)}</span></div>; })}</div><div className="flex flex-wrap gap-4 px-5 py-3 text-[11px] text-text-muted"><Legend color="bg-primary" label="Committed" /><Legend color="bg-success" label="Expected renewal" /><Legend color="bg-warning/70" label="Pipeline upside" /><span className="ml-auto">{money(overview?.revenue.unscheduled_weighted_pipeline, currency)} unscheduled weighted pipeline excluded from bars</span></div></section>;
}

function CapacityPanel({ capacity }: { capacity: CommandOverview["capacity"] | null }) {
  return <section className={panel} aria-labelledby="capacity-title"><PanelHeader id="capacity-title" title="Capacity by location" note={capacity ? `Next month · ${monthLabel(capacity.month)}` : "Next month"} action={<Link className="text-secondary font-medium text-primary" to="/people/demand">People</Link>} />{capacity?.locations.length ? <div className="overflow-x-auto"><table className="w-full text-left text-secondary"><thead className="bg-canvas text-[11px] uppercase text-text-muted"><tr><th className="px-4 py-2">Location</th><th className="px-2 py-2 text-right">People</th><th className="px-2 py-2 text-right">Allocated</th><th className="px-2 py-2 text-right">Open</th><th className="px-4 py-2 text-right">Roll-offs</th></tr></thead><tbody>{capacity.locations.map((row) => <tr key={row.location} className="border-t border-divider"><td className="px-4 py-3 font-medium text-text">{row.location}</td><td className="px-2 py-3 text-right">{row.people}</td><td className="px-2 py-3 text-right">{row.allocated_fte} FTE</td><td className="px-2 py-3 text-right text-warning">{row.open_seat_fte} FTE</td><td className="px-4 py-3 text-right">{row.rolloffs}</td></tr>)}</tbody></table></div> : <SectionState text="No dated allocations overlap next month in this scope." />}<div className="border-t border-divider px-5 py-4 text-secondary text-text-secondary">{capacity?.message ?? "Loading dated allocation evidence…"}</div></section>;
}

function Filter({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) { return <label className="grid gap-1 text-[11px] font-medium text-text-muted">{label}<select className="h-9 min-w-0 rounded-control border border-border bg-surface px-2 text-body text-text focus-visible:outline-focus" value={value} onChange={(event) => onChange(event.target.value)}>{children}</select></label>; }
function Segment({ options, value, onChange }: { options: ReadonlyArray<readonly [string, string]>; value: string; onChange: (value: string) => void }) { return <div className="inline-flex rounded-control border border-border bg-canvas p-0.5" role="group">{options.map(([key, label]) => <button key={key} className={cn("min-h-7 rounded-[4px] px-2 text-[11px] font-medium", value === key ? "bg-surface text-primary shadow-sm" : "text-text-muted")} aria-pressed={value === key} onClick={() => onChange(key)}>{label}</button>)}</div>; }
function Summary({ label, value }: { label: string; value: string }) { return <div className="min-w-0"><span className="block truncate text-text-muted">{label}</span><strong className="mt-1 block truncate text-[18px] text-text">{value}</strong></div>; }
function Legend({ color, label }: { color: string; label: string }) { return <span className="inline-flex items-center gap-1"><i className={cn("h-2 w-2 rounded-[2px]", color)} />{label}</span>; }

function AccountsTable({ rows, currency, onSelect }: { rows: CommandAccountRow[]; currency: string; onSelect: (row: CommandAccountRow) => void }) { return <div className="overflow-x-auto"><table className="w-full min-w-[1100px] border-collapse text-left text-secondary"><thead className="bg-canvas text-[11px] uppercase text-text-muted"><tr><th className="px-5 py-2.5">Account / engagement</th><th className="px-3 py-2.5">Business unit</th><th className="px-3 py-2.5">Sales stage</th><th className="px-3 py-2.5 text-right">Period revenue</th><th className="px-3 py-2.5 text-right">Forecast GM</th><th className="px-3 py-2.5">Staffing</th><th className="px-3 py-2.5">Owner</th><th className="px-5 py-2.5">Next action / due</th></tr></thead><tbody>{rows.map((row) => <tr key={row.opportunity_id} className="border-t border-divider hover:bg-canvas"><td className="px-5 py-3"><button className="text-left font-semibold text-text hover:text-primary" onClick={() => onSelect(row)}>{row.account_name}</button><small className="block text-text-muted">{row.engagement_name}</small></td><td className="px-3 py-3 font-medium text-text">{row.business_unit ?? "Not assigned"}</td><td className="px-3 py-3"><span className="rounded-control bg-primary-subtle px-2 py-1 text-[11px] text-primary">{row.stage_label}</span><small className="mt-1 block text-text-muted">{row.sow_stage.replaceAll("_", " ")}</small></td><td className="px-3 py-3 text-right font-medium">{money(row.period_revenue, row.currency ?? currency, "No linked forecast")}</td><td className="px-3 py-3 text-right"><span className={row.forecast_gm_pct === null ? "text-warning" : "text-text"}>{percentage(row.forecast_gm_pct, "Costs incomplete")}</span>{row.financial_status !== "complete" ? <small className="block text-warning">Review cost setup</small> : null}</td><td className="px-3 py-3">{row.assigned_fte ?? "No linked allocation"}<small className="block text-text-muted">Required {row.required_fte ?? "not published"}</small></td><td className="px-3 py-3">{row.owner_name ?? "Not assigned"}</td><td className="px-5 py-3">{row.next_action ?? "No recorded action"}<small className="block text-text-muted">{shortDate(row.next_action_due)}</small></td></tr>)}</tbody></table></div>; }

function AccountDrawer({ row, currency, returnTo, onClose }: { row: CommandAccountRow; currency: string; returnTo: string; onClose: () => void }) { return <Sheet open onOpenChange={(open) => { if (!open) onClose(); }}><SheetContent side="right" className="w-full max-w-lg overflow-y-auto sm:max-w-lg"><SheetHeader className="pr-8"><p className="text-[11px] font-semibold uppercase text-primary">HubSpot deal · Stage 5+</p><SheetTitle className="text-[22px] font-semibold">{row.account_name}</SheetTitle><SheetDescription>{row.engagement_name}</SheetDescription></SheetHeader><div className="mt-6 grid grid-cols-2 gap-4 border-y border-divider py-5"><Summary label="Sales stage" value={row.stage_label} /><Summary label="Deal value" value={money(row.deal_value, row.currency ?? currency)} /><Summary label="Period revenue" value={money(row.period_revenue, row.currency ?? currency, "No linked forecast")} /><Summary label="Forecast GM" value={percentage(row.forecast_gm_pct, "Costs incomplete")} /><Summary label="Assigned staffing" value={row.assigned_fte == null ? "No linked allocation" : `${row.assigned_fte} FTE`} /><Summary label="Owner" value={row.owner_name ?? "Not assigned"} /></div>{row.financial_blockers.length ? <div className="mt-5 rounded-control border border-warning/30 bg-warning-surface p-3 text-body text-warning"><strong>Financial inputs still needed</strong><ul className="mt-1 list-disc pl-5">{row.financial_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div> : <div className="mt-5 flex items-center gap-2 rounded-control bg-success-surface p-3 text-body text-success"><CheckCircle2 className="h-4 w-4" /> Financial calculation is complete.</div>}<div className="mt-6 flex flex-wrap gap-2"><Link className={cn(button, "border-primary bg-primary text-white")} to={`/deals/${row.opportunity_id}`} state={{ from: returnTo }}>Open deal</Link>{row.engagement_id ? <Link className={button} to={`/engagements/${row.engagement_id}`} state={{ from: returnTo }}>Open engagement</Link> : null}{row.account_id ? <Link className={button} to={`/clients/${row.account_id}`} state={{ from: returnTo }}>Open account</Link> : null}</div></SheetContent></Sheet>; }
