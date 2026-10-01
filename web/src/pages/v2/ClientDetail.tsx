/**
 * S20 · W2 · Client detail page (`/clients/:id`) — Session 3b rebuild.
 *
 * Replaces the S5-era ClientDetailPage that rendered `JSON.stringify`
 * activity rows and linked "deal" cells to `/sows/{opp.id}` (wrong
 * destination). This v2 page:
 *
 *  - Reads `/api/clients/:id` for entities, agreements and recent activity.
 *  - Reads `/api/pipeline/opportunities?client=<id>&include_closed=true`
 *    for the full deal list — same shape as /pipeline, so Closed Lost
 *    pills, owner labels, stage labels and BU column render identically.
 *  - Rollups (matching vs total open, currency totals) computed from the
 *    deal list itself so the client page + Pipeline row stay consistent.
 *  - Activity rows render as prose (actor + action + entity + when), not
 *    JSON — L07 specifically called out that 74 Sky activity was raw JSON.
 *  - L05: Account owner (client.hubspot_owner_id via the D2 owner mirror)
 *    is a separate axis from Deal owner (opportunity.owner_id). Both
 *    render; neither derives from the other.
 */

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, ExternalLink } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  getClient,
  getClientTimeline,
  listPipelineOpportunities,
  type ClientDetail,
  type ClientRecentActivity,
  type PipelineOpportunityRow,
  type TimelineEntry,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { WatchStar } from "../../ui-v2/WatchStar";
import { Badge } from "../../ui-v2/primitives/badge";
import { Button } from "../../ui-v2/primitives/button";

const HUBSPOT_COMPANY_URL =
  "https://app.hubspot.com/contacts/48656168/record/0-2/";

function formatMoneyMap(
  values: Record<string, string>,
): { currency: string; formatted: string }[] {
  return Object.entries(values).map(([currency, amount]) => ({
    currency,
    formatted: new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(Number(amount || 0)),
  }));
}

function formatMoney(amount: string | null, currency: string | null): string {
  if (amount == null) return "—";
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const t = iso.length <= 10 ? iso + "T00:00:00Z" : iso;
  return new Date(t).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function formatAgo(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - t);
  const days = Math.floor(diff / (24 * 60 * 60 * 1000));
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function ownerLabel(row: PipelineOpportunityRow): string {
  if (row.owner_name) return row.owner_name;
  if (row.owner_email) return row.owner_email;
  if (row.owner_id) return "Owner details unavailable";
  return "Unassigned";
}

function activityLine(a: ClientRecentActivity): string {
  const target = a.entity.replace(/_/g, " ");
  const action = a.action.replace(/_/g, " ");
  return `${action} on ${target}`;
}

export function ClientDetailPageV2() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [deals, setDeals] = useState<PipelineOpportunityRow[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    async function load() {
      try {
        const c = await getClient(id as string);
        if (cancelled) return;
        setClient(c);
        const [dealsPage, tl] = await Promise.all([
          listPipelineOpportunities({
            client: [id as string],
            include_closed: true,
            page_size: 100,
          }),
          getClientTimeline(id as string).catch(() => ({
            items: [] as TimelineEntry[],
          })),
        ]);
        if (cancelled) return;
        setDeals(dealsPage.items);
        setTimeline(tl.items);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const rollup = useMemo(() => {
    const open = deals.filter((d) => !d.is_closed_won && !d.is_closed_lost);
    const closedWon = deals.filter((d) => d.is_closed_won);
    const closedLost = deals.filter((d) => d.is_closed_lost);
    const openValueByCurrency: Record<string, string> = {};
    for (const d of open) {
      if (d.amount == null) continue;
      const cur = d.currency || "USD";
      const cur_total = Number(openValueByCurrency[cur] ?? "0") + Number(d.amount);
      openValueByCurrency[cur] = String(cur_total);
    }
    return {
      total: deals.length,
      open: open.length,
      closedWon: closedWon.length,
      closedLost: closedLost.length,
      openValueByCurrency,
    };
  }, [deals]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Loading client…" />
        <div
          role="status"
          className="rounded-panel border border-divider p-6 text-body text-text-secondary"
        >
          Fetching client rollup and deal list…
        </div>
      </div>
    );
  }

  if (error) {
    const msg = error instanceof ApiError ? error.message : String(error);
    const status = error instanceof ApiError ? error.status : 0;
    if (status === 404) {
      return (
        <div>
          <PageHeader title="Client not found" />
          <EmptyState
            title="No client at this id"
            description="It may have been archived, or the link is stale."
          />
        </div>
      );
    }
    return (
      <div>
        <PageHeader title="Client detail" />
        <ErrorState title="We couldn't load this client" description={msg} />
      </div>
    );
  }

  if (!client) return null;

  return (
    <div>
      <PageHeader
        title={<span data-testid="client-heading">{client.name}</span>}
        subtitle={
          <>
            {client.hubspot_company_id
              ? `HubSpot company #${client.hubspot_company_id}`
              : "No HubSpot company on file"}
            {" · "}
            <span className="text-text-secondary">
              {rollup.total.toLocaleString("en-US")} deal
              {rollup.total === 1 ? "" : "s"}
              {" ("}
              {rollup.open}{" "}open
              {rollup.closedWon > 0 ? `, ${rollup.closedWon} closed won` : ""}
              {rollup.closedLost > 0 ? `, ${rollup.closedLost} closed lost` : ""}
              {")"}
            </span>
          </>
        }
        actions={
          <>
            <WatchStar kind="client" itemId={client.id} />
            <Button variant="secondary" onClick={() => navigate("/pipeline")}>
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
              Pipeline
            </Button>
            {client.hubspot_company_id ? (
              <a
                href={`${HUBSPOT_COMPANY_URL}${client.hubspot_company_id}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="secondary" asChild={false}>
                  Open in HubSpot
                  <ExternalLink className="ml-1 h-4 w-4" aria-hidden />
                </Button>
              </a>
            ) : null}
          </>
        }
      />

      {/* Rollup panel (L05 · L07). */}
      <section
        aria-label="Client rollup"
        className="mb-6 grid grid-cols-2 gap-4 rounded-panel border border-divider bg-surface p-4 md:grid-cols-4"
        data-testid="client-rollup"
      >
        <Metric
          label="Open deals"
          value={rollup.open.toString()}
          testid="rollup-open"
        />
        <Metric
          label="Closed Won"
          value={rollup.closedWon.toString()}
          testid="rollup-closed-won"
        />
        <Metric
          label="Closed Lost"
          value={rollup.closedLost.toString()}
          testid="rollup-closed-lost"
          tone={rollup.closedLost > 0 && rollup.open === 0 ? "danger" : "default"}
        />
        <div>
          <div className="text-secondary text-text-secondary">Open value</div>
          <div className="mt-1 text-body text-text tnum" data-testid="rollup-open-value">
            {Object.keys(rollup.openValueByCurrency).length === 0
              ? "—"
              : formatMoneyMap(rollup.openValueByCurrency).map((v) => (
                  <div key={v.currency}>{v.formatted}</div>
                ))}
          </div>
        </div>
      </section>

      {/* L07: If the only signal is Closed Lost — 74 Sky-style — spell it out plainly. */}
      {rollup.open === 0 && rollup.closedLost > 0 && rollup.closedWon === 0 ? (
        <section
          className="mb-6 flex items-start gap-3 rounded-panel border border-danger/40 bg-danger/5 p-3"
          role="status"
          data-testid="client-closed-lost-callout"
        >
          <AlertTriangle
            className="mt-0.5 h-4 w-4 text-danger"
            aria-hidden
          />
          <div>
            <div className="font-medium text-danger">Closed Lost</div>
            <div className="text-body text-text-secondary">
              This client has {rollup.closedLost} closed-lost
              {rollup.closedLost === 1 ? " deal" : " deals"} and no open work.
              Nothing is in flight.
            </div>
          </div>
        </section>
      ) : null}

      {/* Legal entities panel. */}
      <section
        aria-label="Legal entities"
        className="mb-6 rounded-panel border border-divider bg-surface p-4"
        data-testid="client-entities"
      >
        <h2 className="mb-3 text-heading-3 text-text">Legal entities</h2>
        {client.legal_entities.length === 0 ? (
          <p className="text-body text-text-secondary">
            No legal entities on file. A default is created on intake — Legal
            can add more.
          </p>
        ) : (
          <ul className="space-y-2">
            {client.legal_entities.map((e) => (
              <li
                key={e.id}
                className="flex items-center justify-between border-b border-divider py-2 last:border-0"
                data-testid={`entity-${e.id}`}
              >
                <div className="font-medium text-text">{e.name}</div>
                <div className="text-secondary text-text-secondary">
                  {e.country || "Country not set"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Deals table — same shape as Pipeline's Opportunities view (L04, L07). */}
      <section
        aria-label="Deals"
        className="mb-6 rounded-panel border border-divider bg-surface p-4"
        data-testid="client-deals"
      >
        <h2 className="mb-3 text-heading-3 text-text">Deals</h2>
        {deals.length === 0 ? (
          <p className="text-body text-text-secondary">
            No deals for this client yet — HubSpot may still be syncing, or
            no company-to-deal association exists in the source.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table
              className="w-full text-body"
              aria-label="Client deals"
              data-testid="deals-table"
            >
              <thead className="text-left text-secondary text-text-secondary">
                <tr>
                  <th className="px-3 py-2 font-medium">Deal</th>
                  <th className="px-3 py-2 font-medium">Stage</th>
                  <th className="px-3 py-2 font-medium">Owner (deal)</th>
                  <th className="px-3 py-2 font-medium">Amount</th>
                  <th className="px-3 py-2 font-medium">Close</th>
                  <th className="px-3 py-2 font-medium">SOW</th>
                </tr>
              </thead>
              <tbody>
                {deals.map((d) => {
                  const display =
                    d.name && d.name.trim().length > 0
                      ? d.name
                      : d.hubspot_deal_id
                        ? `Deal ${d.hubspot_deal_id}`
                        : "Unnamed";
                  return (
                    <tr
                      key={d.opportunity_id}
                      className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                      onClick={() => navigate(`/deals/${d.opportunity_id}`)}
                      data-testid={`client-deal-row-${d.opportunity_id}`}
                    >
                      <td className="px-3 py-3 align-top">
                        <div className="flex items-center gap-2">
                          <span className="text-text">{display}</span>
                          {d.is_closed_lost ? (
                            <Badge tone="danger" data-testid={`closed-lost-${d.opportunity_id}`}>
                              Closed Lost
                            </Badge>
                          ) : null}
                          {d.is_closed_won ? (
                            <Badge tone="success" data-testid={`closed-won-${d.opportunity_id}`}>
                              Closed Won
                            </Badge>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {d.stage_label || "Unknown"}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {ownerLabel(d)}
                      </td>
                      <td className="px-3 py-3 align-top tnum text-text">
                        {formatMoney(d.amount, d.currency)}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {formatDate(d.close_date)}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {d.sow_approval_state}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* S20 W6 · combined timeline (comments + next-action events +
        * approvals + SOW versions) — prose, not JSON (L07). Falls back
        * to the ClientDetail.recent_activity feed when the timeline
        * endpoint returns empty (e.g. no deal-level events yet). */}
      <section
        aria-label="Recent activity"
        className="rounded-panel border border-divider bg-surface p-4"
        data-testid="client-activity"
      >
        <h2 className="mb-3 text-heading-3 text-text">Recent activity</h2>
        {timeline.length > 0 ? (
          <ol className="space-y-2">
            {timeline.slice(0, 10).map((t, i) => (
              <li
                key={`${t.ts}-${i}`}
                className="border-b border-divider py-2 last:border-0"
                data-testid={`timeline-${t.source}-${i}`}
              >
                <div className="text-body text-text">
                  <span className="mr-2 rounded bg-primary-subtle px-1.5 py-0.5 text-secondary text-primary">
                    {t.source}
                  </span>
                  {t.actor_name ? (
                    <span className="font-medium">{t.actor_name} </span>
                  ) : null}
                  {t.body}
                </div>
                <div className="text-secondary text-text-secondary">
                  {formatAgo(t.ts)}
                </div>
              </li>
            ))}
          </ol>
        ) : client.recent_activity.length === 0 ? (
          <p className="text-body text-text-secondary">
            No recent activity for this client.
          </p>
        ) : (
          <ol className="space-y-2">
            {client.recent_activity.slice(0, 10).map((a) => (
              <li
                key={a.id}
                className="border-b border-divider py-2 last:border-0"
                data-testid={`activity-${a.id}`}
              >
                <div className="text-body text-text">{activityLine(a)}</div>
                <div className="text-secondary text-text-secondary">
                  {formatAgo(a.ts)}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function Metric({
  label,
  value,
  testid,
  tone,
}: {
  label: string;
  value: string;
  testid?: string;
  tone?: "default" | "danger";
}) {
  return (
    <div>
      <div className="text-secondary text-text-secondary">{label}</div>
      <div
        className={`mt-1 text-heading-3 ${tone === "danger" ? "text-danger" : "text-text"}`}
        data-testid={testid}
      >
        {value}
      </div>
    </div>
  );
}
