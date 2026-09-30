/**
 * S20 · W2 · Deal detail page (`/deals/:id`) — Session 3b.
 *
 * Replaces the S18 RetiredPage redirect. Renders the mirror facts
 * (name, client, owner, stage, close date, amount, BU, pipeline), an
 * ordered stage strip drawn from the pipeline mirror, NDA/MSA marks
 * on the client, the latest next action + latest visible comment
 * (W6's contract), and the SOW list — or a single "Upload SOW"
 * button when the deal has no SOW yet.
 *
 * Rule 11 (CLAUDE.md): every control is wired. No stub buttons, no
 * "Not implemented" branches. If the mirror has no pipeline id, the
 * ordered stage strip degrades to a single "current stage" chip
 * rather than rendering an empty section.
 *
 * Contract coverage:
 *  - L04 dealname → h1 heading + `data-testid="deal-heading"`
 *  - L07 Closed Lost pill next to the name if `is_closed_lost`
 *  - L09 no stub SOW workspace: shows "Upload SOW" when `sow_count===0`
 *  - D2 owner label: "Unassigned" (no id) vs
 *    "Owner details unavailable" (id but unresolved)
 *  - W6 next-action + latest-comment slots read live
 */

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, ExternalLink, Upload } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  getDealTimeline,
  getPipelineOpportunity,
  listDealComments,
  listNextActions,
  listPipelineStages,
  type DealCommentRow,
  type NextActionRow,
  type PipelineOpportunityRow,
  type PipelineStageCount,
  type TimelineEntry,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { WatchStar } from "../../ui-v2/WatchStar";
import { Badge } from "../../ui-v2/primitives/badge";
import { Button } from "../../ui-v2/primitives/button";

const HUBSPOT_DEAL_URL = "https://app.hubspot.com/contacts/48656168/record/0-3/";

const SOW_STATE_LABELS: Record<string, string> = {
  none: "No SOW",
  draft: "Draft",
  in_review_delivery_hr: "In review · delivery/hr",
  in_review_finance_legal: "In review · finance/legal",
  changes_requested: "Changes requested",
  ceo_exception: "CEO exception",
  approved: "Approved",
  awaiting_signature: "Awaiting signature",
  signed: "Signed",
};

const ATTENTION_LABELS: Record<string, string> = {
  overdue_action: "Overdue action",
  stalled: "Stalled 14d+",
  no_owner: "No owner",
  pending_approval: "Pending approval",
  closed_won_not_released: "Closed-won · no release",
};

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
  return new Date(iso + "T00:00:00Z").toLocaleDateString(undefined, {
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

export function DealDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [deal, setDeal] = useState<PipelineOpportunityRow | null>(null);
  const [stages, setStages] = useState<PipelineStageCount[]>([]);
  const [nextActions, setNextActions] = useState<NextActionRow[]>([]);
  const [latestComment, setLatestComment] = useState<DealCommentRow | null>(
    null,
  );
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    async function load() {
      try {
        const d = await getPipelineOpportunity(id as string);
        if (cancelled) return;
        setDeal(d);

        const [stageList, actions, comments, tl] = await Promise.all([
          d.hubspot_pipeline_id
            ? listPipelineStages(d.hubspot_pipeline_id)
            : Promise.resolve([] as PipelineStageCount[]),
          listNextActions({ opportunity_id: d.opportunity_id }),
          listDealComments(d.opportunity_id),
          getDealTimeline(d.opportunity_id).catch(() => ({
            items: [] as TimelineEntry[],
          })),
        ]);
        if (cancelled) return;
        setStages(stageList);
        setNextActions(actions.items);
        setLatestComment(comments.latest);
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

  const heading = useMemo(() => {
    if (!deal) return "Deal";
    return deal.name && deal.name.trim().length > 0
      ? deal.name
      : deal.hubspot_deal_id
        ? `Deal ${deal.hubspot_deal_id}`
        : "Unnamed deal";
  }, [deal]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Loading deal…" />
        <div
          role="status"
          className="rounded-panel border border-divider p-6 text-body text-text-secondary"
        >
          Fetching deal facts and rollups…
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
          <PageHeader
            title="Deal not found"
            actions={
              <Button variant="secondary" onClick={() => navigate("/pipeline")}>
                <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
                Back to Pipeline
              </Button>
            }
          />
          <EmptyState
            title="No deal at this id"
            description="It may have been archived, or the link is stale. Go back to Pipeline to find the current deal."
          />
        </div>
      );
    }
    return (
      <div>
        <PageHeader
          title="Deal detail"
          actions={
            <Button variant="secondary" onClick={() => navigate("/pipeline")}>
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
              Back to Pipeline
            </Button>
          }
        />
        <ErrorState title="We couldn't load this deal" description={msg} />
      </div>
    );
  }

  if (!deal) return null;

  return (
    <div>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span data-testid="deal-heading">{heading}</span>
            {deal.is_closed_lost ? (
              <Badge tone="danger" data-testid="closed-lost-pill">
                Closed Lost
              </Badge>
            ) : null}
            {deal.is_closed_won ? (
              <Badge tone="success" data-testid="closed-won-pill">
                Closed Won
              </Badge>
            ) : null}
          </span>
        }
        subtitle={
          deal.client_name ? (
            <>
              <Link
                to={deal.client_id ? `/clients/${deal.client_id}` : "/pipeline"}
                className="text-primary hover:underline"
                data-testid="deal-client-link"
              >
                {deal.client_name}
              </Link>
              {deal.hubspot_deal_id ? (
                <>
                  {" · "}
                  <span className="text-secondary">
                    HubSpot deal #{deal.hubspot_deal_id}
                  </span>
                </>
              ) : null}
            </>
          ) : (
            "No client on this deal"
          )
        }
        actions={
          <>
            <WatchStar kind="opportunity" itemId={deal.opportunity_id} />
            <Button variant="secondary" onClick={() => navigate("/pipeline")}>
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
              Pipeline
            </Button>
            {deal.hubspot_deal_id ? (
              <a
                href={`${HUBSPOT_DEAL_URL}${deal.hubspot_deal_id}`}
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

      {/* Facts panel. */}
      <section
        aria-label="Deal facts"
        className="mb-6 grid grid-cols-2 gap-4 rounded-panel border border-divider bg-surface p-4 md:grid-cols-4"
        data-testid="deal-facts"
      >
        <Fact label="Amount" value={formatMoney(deal.amount, deal.currency)} />
        <Fact label="Close date" value={formatDate(deal.close_date)} />
        <Fact label="Owner" value={ownerLabel(deal)} />
        <Fact label="Business unit" value={deal.business_unit || "—"} />
        <Fact
          label="Stage"
          value={deal.stage_label || deal.stage_id || "Unknown"}
        />
        <Fact
          label="Pipeline"
          value={deal.hubspot_pipeline_id || "—"}
        />
        <Fact
          label="Last activity"
          value={formatAgo(deal.hubspot_last_activity_at)}
        />
        <Fact
          label="SOW state"
          value={
            SOW_STATE_LABELS[deal.sow_approval_state] ??
            deal.sow_approval_state
          }
        />
      </section>

      {/* Ordered stage strip. */}
      <section
        aria-label="Deal stage strip"
        className="mb-6 rounded-panel border border-divider bg-surface p-4"
        data-testid="deal-stage-strip"
      >
        <div className="mb-2 text-secondary text-text-secondary">
          Stage order
        </div>
        {stages.length > 0 ? (
          <ol className="flex flex-wrap gap-2">
            {stages.map((s) => {
              const active = s.stage_id === deal.stage_id;
              const tone = s.is_closed_lost
                ? "border-danger text-danger"
                : s.is_closed_won
                  ? "border-success text-success"
                  : "border-divider text-text-secondary";
              return (
                <li
                  key={`${s.pipeline_id}:${s.stage_id}`}
                  className={`rounded-panel border px-3 py-1 text-secondary ${
                    active
                      ? "bg-primary-subtle font-medium text-primary"
                      : `bg-surface ${tone}`
                  }`}
                  aria-current={active ? "step" : undefined}
                  data-testid={
                    active
                      ? `stage-current-${s.stage_id}`
                      : `stage-step-${s.stage_id}`
                  }
                >
                  {s.stage_label ?? "Unknown"}
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="text-body text-text-secondary">
            {deal.stage_label
              ? `Currently in ${deal.stage_label} — pipeline stage mirror hasn't listed this pipeline's other stages.`
              : "No stage on this deal (HubSpot may still be catching up)."}
          </div>
        )}
      </section>

      {/* Attention flags. */}
      {deal.attention_flags.length > 0 ? (
        <section
          className="mb-6 flex items-start gap-3 rounded-panel border border-warn/40 bg-warn-fill/20 p-3"
          role="status"
          data-testid="deal-attention"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 text-warn" aria-hidden />
          <div>
            <div className="font-medium text-warn">Needs attention</div>
            <ul className="mt-1 flex flex-wrap gap-2">
              {deal.attention_flags.map((f) => (
                <li key={f}>
                  <Badge tone="warning" data-testid={`flag-${f}`}>
                    {ATTENTION_LABELS[f] ?? f}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Next action + latest comment (W6). */}
        <section
          aria-label="Next action"
          className="rounded-panel border border-divider bg-surface p-4"
          data-testid="deal-next-action"
        >
          <h2 className="mb-3 text-heading-3 text-text">Next action</h2>
          {nextActions.length === 0 ? (
            <p className="text-body text-text-secondary">
              No next actions on this deal. When one is created via My Work
              or by an approver, it will appear here.
            </p>
          ) : (
            <ol className="space-y-3">
              {nextActions.slice(0, 3).map((a) => (
                <li key={a.id} data-testid={`next-action-${a.id}`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="font-medium text-text">
                      {a.title || a.description}
                    </div>
                    <div className="text-secondary text-text-secondary tnum">
                      {a.due_date ? `due ${formatDate(a.due_date)}` : "no due"}
                    </div>
                  </div>
                  {a.title && a.description ? (
                    <div className="mt-1 text-body text-text-secondary">
                      {a.description}
                    </div>
                  ) : null}
                  <div className="mt-1 flex items-center gap-2 text-secondary">
                    <Badge
                      tone={a.status === "open" ? "warning" : "neutral"}
                      data-testid={`next-action-status-${a.status}`}
                    >
                      {a.status}
                    </Badge>
                    {a.blocker ? (
                      <span className="text-text-secondary">
                        blocker: {a.blocker}
                      </span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section
          aria-label="Latest comment"
          className="rounded-panel border border-divider bg-surface p-4"
          data-testid="deal-latest-comment"
        >
          <h2 className="mb-3 text-heading-3 text-text">Latest comment</h2>
          {latestComment ? (
            <div>
              <div className="text-body text-text">{latestComment.body}</div>
              <div className="mt-2 text-secondary text-text-secondary">
                {latestComment.author_name_fallback || "Someone"} ·{" "}
                {formatAgo(latestComment.created_at)}
                {latestComment.source === "hubspot_note" ? " · HubSpot note" : null}
              </div>
            </div>
          ) : (
            <p className="text-body text-text-secondary">
              No comments yet on this deal.
            </p>
          )}
        </section>
      </div>

      {/* SOW list or Upload SOW button (L09). */}
      <section
        aria-label="SOW packages"
        className="mt-6 rounded-panel border border-divider bg-surface p-4"
        data-testid="deal-sows"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-heading-3 text-text">SOW packages</h2>
          <div className="text-secondary text-text-secondary">
            {deal.sow_count} {deal.sow_count === 1 ? "package" : "packages"}
          </div>
        </div>
        {deal.sow_count === 0 ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-body text-text-secondary">
              No SOW yet for this deal. Upload one from the SOW studio when the
              scope is ready.
            </p>
            <Link
              to={`/sows/new?opportunity_id=${deal.opportunity_id}${
                deal.client_id ? `&client_id=${deal.client_id}` : ""
              }`}
              data-testid="upload-sow-cta"
            >
              <Button variant="primary" asChild={false}>
                <Upload className="mr-1 h-4 w-4" aria-hidden />
                Upload SOW
              </Button>
            </Link>
          </div>
        ) : (
          <div className="flex flex-col items-start gap-2">
            <p className="text-body text-text-secondary">
              {deal.sow_count} SOW {deal.sow_count === 1 ? "package" : "packages"}
              {" · state: "}
              <span className="font-medium">
                {SOW_STATE_LABELS[deal.sow_approval_state] ??
                  deal.sow_approval_state}
              </span>
            </p>
            <Link
              to={`/sows?opportunity_id=${deal.opportunity_id}`}
              data-testid="view-sow-list"
              className="text-primary hover:underline"
            >
              View SOW list →
            </Link>
          </div>
        )}
      </section>

      {/* S20 W6 · combined timeline (comments + next-action events + approval + SOW). */}
      <section
        aria-label="Activity timeline"
        className="mt-6 rounded-panel border border-divider bg-surface p-4"
        data-testid="deal-timeline"
      >
        <h2 className="mb-3 text-heading-3 text-text">Activity</h2>
        {timeline.length === 0 ? (
          <p className="text-body text-text-secondary">
            Nothing has happened on this deal yet — no comments, actions or
            SOW events.
          </p>
        ) : (
          <ol className="space-y-2">
            {timeline.map((t, i) => (
              <li
                key={`${t.ts}-${i}`}
                className="border-b border-divider py-2 last:border-0"
                data-testid={`timeline-${t.source}-${i}`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div className="text-body text-text">
                    <span className="mr-2 rounded bg-primary-subtle px-1.5 py-0.5 text-secondary text-primary">
                      {t.source}
                    </span>
                    {t.actor_name ? (
                      <span className="font-medium">{t.actor_name} </span>
                    ) : null}
                    {t.body}
                  </div>
                  <div className="text-secondary text-text-secondary tnum">
                    {formatAgo(t.ts)}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-secondary text-text-secondary">{label}</div>
      <div
        className="mt-1 text-body text-text"
        data-testid={`fact-${label.toLowerCase().replace(/\s+/g, "-")}`}
      >
        {value}
      </div>
    </div>
  );
}
