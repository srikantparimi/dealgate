/**
 * Adviser estimate + evidence panel — the right 60% column (spec §10).
 *
 * Renders scope interpretation, staffing table, cost low/base/high,
 * confidence, missing information, assumptions/exclusions, and the
 * evidence list. Distinguishes sourced client facts from inferred
 * requirements (the estimate object carries `reasons[]` + `inputs`;
 * sources come from public research).
 *
 * `research_status === "unavailable"` renders an explicit banner:
 *   "Public research unavailable — no verified source found."
 * When sources[] is empty and research succeeded we still say "No
 * verified source found" rather than showing a fake link (spec §10).
 */
import { ExternalLink } from "lucide-react";
import type { AdviserEstimate } from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import {
  confidenceTone,
  toEvidence,
} from "./adviserDisplay";

export interface EstimatePanelProps {
  estimate: AdviserEstimate;
}

export function EstimatePanel({ estimate }: EstimatePanelProps) {
  const sources = toEvidence(estimate.sources);
  const researchUnavailable = estimate.research_status === "unavailable";

  return (
    <div className="flex flex-col gap-6">
      <ResearchBanner
        unavailable={researchUnavailable}
        sourceCount={sources.length}
      />

      <section
        aria-label="Scope interpretation"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text">Scope interpretation</h3>
        <p className="mt-2 text-body text-text whitespace-pre-wrap">
          {estimate.scope}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusBadge
            tone={confidenceTone(estimate.confidence)}
            label={`Confidence: ${estimate.confidence}`}
          />
          {estimate.has_sentinel_costs ? (
            <StatusBadge
              tone="warn"
              label="Some cost inputs use sentinel values"
            />
          ) : null}
        </div>
      </section>

      <section
        aria-label="Staffing"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text mb-3">
          Staffing — roles · location · effort
        </h3>
        {estimate.team.length === 0 ? (
          <EmptyState
            title="No staffing rows yet."
            description="The estimate did not include a priced team."
          />
        ) : (
          <div className="overflow-x-auto">
            <table
              className="w-full text-body"
              aria-label="Adviser team members"
              data-testid="adviser-team"
            >
              <thead>
                <tr className="text-left text-secondary text-text-secondary">
                  <th className="px-2 py-1 font-medium">Role · seniority</th>
                  <th className="px-2 py-1 font-medium">Location</th>
                  <th className="px-2 py-1 font-medium text-right">Hours</th>
                  <th className="px-2 py-1 font-medium text-right">
                    Allocation
                  </th>
                  <th className="px-2 py-1 font-medium text-right">
                    Cost range
                  </th>
                </tr>
              </thead>
              <tbody>
                {estimate.team.map((m, i) => (
                  <tr
                    key={`${m.role}-${i}`}
                    className="border-t border-divider"
                  >
                    <td className="px-2 py-2 text-text">
                      {m.role} · {m.seniority}
                    </td>
                    <td className="px-2 py-2 text-text-secondary">
                      {m.location}
                    </td>
                    <td className="px-2 py-2 tnum text-right text-text">
                      {m.hours}
                    </td>
                    <td className="px-2 py-2 tnum text-right text-text">
                      {m.allocation_pct}%
                    </td>
                    <td className="px-2 py-2 text-right text-text tnum">
                      {m.cost_low} · {m.cost_base} · {m.cost_high}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section
        aria-label="Cost range"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text mb-3">
          Estimated cost — low / base / high
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <CostTile label="Low" value={estimate.cost_low} />
          <CostTile label="Base" value={estimate.cost_base} />
          <CostTile label="High" value={estimate.cost_high} />
        </div>
        <p className="mt-3 text-secondary text-text-secondary">
          Indicative only. Cost is the server's staffing × rate range —
          it never approves scope, salary, terms or GM.
        </p>
      </section>

      <section
        aria-label="Delivery options"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text mb-3">Delivery options</h3>
        {estimate.options.length === 0 ? (
          <EmptyState
            title="No delivery options priced."
            description="The Adviser did not return a US / India / Mixed comparison."
          />
        ) : (
          <div className="overflow-x-auto">
            <table
              className="w-full text-body"
              aria-label="Delivery options"
              data-testid="adviser-options"
            >
              <thead>
                <tr className="text-left text-secondary text-text-secondary">
                  <th className="px-2 py-1 font-medium">Option</th>
                  <th className="px-2 py-1 font-medium text-right">Cost base</th>
                  <th className="px-2 py-1 font-medium text-right">
                    Min compliant price
                  </th>
                  <th className="px-2 py-1 font-medium text-right">Floor</th>
                  <th className="px-2 py-1 font-medium">Eligible?</th>
                </tr>
              </thead>
              <tbody>
                {estimate.options.map((o) => (
                  <tr key={o.key} className="border-t border-divider">
                    <td className="px-2 py-2 text-text">{o.label}</td>
                    <td className="px-2 py-2 tnum text-right text-text">
                      {o.cost_base}
                    </td>
                    <td className="px-2 py-2 tnum text-right text-text">
                      {o.min_price}
                    </td>
                    <td className="px-2 py-2 tnum text-right text-text-secondary">
                      {o.floor_applied}
                    </td>
                    <td className="px-2 py-2">
                      <StatusBadge
                        tone={o.eligible ? "ok" : "danger"}
                        label={o.eligible ? "Eligible" : "Below floor"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section
        aria-label="Reasons and assumptions"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h3 className="text-section text-text mb-2">
          Assumptions · exclusions · missing information
        </h3>
        {estimate.reasons.length === 0 ? (
          <p className="text-body text-text-secondary">
            No assumptions or missing-info notes were returned.
          </p>
        ) : (
          <ul className="list-disc pl-5 text-body text-text">
            {estimate.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </section>

      <section
        aria-label="Public evidence"
        className="rounded-panel border border-divider bg-surface p-4"
        data-testid="adviser-sources"
      >
        <h3 className="text-section text-text mb-3">Public evidence</h3>
        {researchUnavailable || sources.length === 0 ? (
          <EmptyState
            title="No verified source found."
            description={
              researchUnavailable
                ? "Public research was unavailable for this estimate. Nothing has been fabricated."
                : "The Adviser did not return any citations for this run. We never fabricate URLs when research is empty."
            }
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {sources.map((s, i) => (
              <li key={i} className="rounded-control border border-divider p-3">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 text-primary underline"
                >
                  {s.title}
                  <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
                <div className="mt-1 text-secondary text-text-secondary">
                  Retrieved: {s.retrievedAt}
                  {s.relevance ? ` · ${s.relevance}` : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ResearchBanner({
  unavailable,
  sourceCount,
}: {
  unavailable: boolean;
  sourceCount: number;
}) {
  if (unavailable) {
    return (
      <div
        role="status"
        data-testid="research-unavailable-banner"
        className="rounded-panel border border-warning/40 bg-warning-surface px-4 py-3 text-body text-text"
      >
        Public research unavailable — no verified source found. Client
        facts below are inferred from your intake only.
      </div>
    );
  }
  if (sourceCount === 0) {
    return (
      <div
        role="status"
        data-testid="research-empty-banner"
        className="rounded-panel border border-divider bg-primary-subtle/40 px-4 py-3 text-body text-text-secondary"
      >
        No verified sources returned for this estimate. Everything below
        is inferred from your intake.
      </div>
    );
  }
  return null;
}

function CostTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-divider bg-surface p-3">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <MoneyCell value={value} className="text-metric" />
    </div>
  );
}
