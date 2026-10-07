/**
 * S22 redesign · AI-first staffing proposal card (directive §5).
 *
 * Order of truth: the scope DEMAND estimate comes first (what the SOW's
 * deliverables need — roles, skills, phases, coverage, with verbatim
 * quotes, stated vs inferred), independent of the fee. Affordability is
 * a separate deterministic calculation; when fee or duration are
 * missing it reports an explicit blocked state instead of guessing.
 * Demand never shrinks to fit the budget: the gap is shown, with four
 * explained resolution actions. Nothing auto-applies; Apply offers a
 * compare first and Undo after, and never touches cost confirmation.
 *
 * Fee and duration are READ from the canonical contract fields (the
 * pricing editor's fee, the contract dates) — no duplicate values.
 */
import { useEffect, useRef, useState } from "react";
import {
  getStaffingAdvice,
  type CommercialComponent,
  type CommercialStaffing,
  type StaffingAdvice,
} from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { fractionToPercent } from "../format";
import { Field, PercentField } from "./Fields";

export type ResolutionAction = "fee" | "scope" | "term" | "exception";

export function PlanTeamPanel({
  opportunityId,
  inputs,
  advice,
  onAdvice,
  onApply,
  onResolve,
}: {
  opportunityId: string;
  inputs: CommercialComponent;
  advice: StaffingAdvice | null;
  onAdvice: (advice: StaffingAdvice | null) => void;
  onApply: (next: CommercialComponent) => void;
  onResolve?: (action: ResolutionAction) => void;
}) {
  // Canonical commercial facts — read, not duplicated. Other pricing
  // models have no single total fee; the server then reads the SOW's
  // extracted price and the response names what it used.
  const canonicalFee =
    inputs.profile === "fixed_assignment" ? (inputs.pricing?.total_fee ?? null) : null;
  const hasDates = !!inputs.service_start && !!inputs.service_end;
  const [weeksOverride, setWeeksOverride] = useState("");
  const [targetGm, setTargetGm] = useState("");
  const [requiredFte, setRequiredFte] = useState("");
  const [minOnshore, setMinOnshore] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [undoRows, setUndoRows] = useState<CommercialStaffing[] | null>(null);
  const autoRan = useRef(false);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const result = await getStaffingAdvice(opportunityId, {
        revenue: canonicalFee || null,
        weeks: hasDates ? null : weeksOverride || null,
        service_start: inputs.service_start,
        service_end: inputs.service_end,
        target_gm: targetGm || null,
        required_fte: requiredFte || null,
        min_onshore_fte: minOnshore || "0",
      });
      onAdvice(result);
      setComparing(false);
      if (!requiredFte && result.estimate?.required_fte)
        setRequiredFte(result.estimate.required_fte);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Advice unavailable");
    } finally {
      setBusy(false);
    }
  }

  // Auto-request the independent scope assessment once for a new/empty
  // draft (directive §5). Missing fee blocks affordability server-side,
  // never this estimate. Never re-runs per keystroke — regeneration is
  // the explicit button below.
  useEffect(() => {
    if (autoRan.current || advice || busy) return;
    if ((inputs.staffing?.length ?? 0) > 0) return;
    autoRan.current = true;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs.staffing?.length]);

  function proposedRows(): CommercialStaffing[] {
    if (!advice?.suggested) return [];
    const binding = {
      source_id: inputs.source_id,
      source_version: inputs.source_version,
      component_id: inputs.component_id,
      profile_version: inputs.profile_version,
      policy_version: inputs.policy_version,
    };
    const mk = (
      location: "US" | "India",
      fte: number,
      costRate: string,
      prefix: string,
      role: string,
    ): CommercialStaffing[] => {
      const rows: CommercialStaffing[] = [];
      const base = {
        ...binding,
        role,
        location,
        timezone: inputs.timezone ?? "America/Los_Angeles",
        currency: inputs.currency,
        calendar: null,
        bill_rate: null,
        cost_rate: costRate,
        rate_version: null,
        cost_version: "staffing-advice",
        start: inputs.service_start,
        end: inputs.service_end,
        cost_rate_basis: "hourly" as const,
        cost_proration: null,
      };
      const whole = Math.floor(fte);
      if (whole > 0)
        rows.push({ ...base, assignment_id: `${prefix}-full`, quantity: whole, allocation: "1" });
      if (fte - whole > 0)
        rows.push({
          ...base,
          assignment_id: `${prefix}-part`,
          quantity: 1,
          allocation: String(fte - whole),
        });
      return rows;
    };
    return [
      ...mk("US", Number(advice.suggested.onshore_fte), advice.inputs.onshore_cost_per_hour, "advised-us", "Onshore consultant"),
      ...mk("India", Number(advice.suggested.offshore_fte), advice.inputs.offshore_cost_per_hour, "advised-india", "Offshore consultant"),
    ];
  }

  function applyMix() {
    const rows = proposedRows();
    if (!rows.length) return;
    setUndoRows(inputs.staffing ?? []);
    const fteByLocation = new Map<string, number>();
    for (const row of rows) {
      if (!row.location) continue;
      fteByLocation.set(
        row.location,
        (fteByLocation.get(row.location) ?? 0) +
          row.quantity * (Number(row.allocation) || 0),
      );
    }
    const dominantLocation = [...fteByLocation.entries()].sort(
      (a, b) => b[1] - a[1],
    )[0]?.[0];
    const allocationBasis = inputs.pricing?.allocation_basis ?? "";
    const pricing =
      inputs.profile === "fixed_assignment" &&
      dominantLocation &&
      /\((?:proposed|defaulted)\)/.test(allocationBasis)
        ? {
            ...inputs.pricing,
            allocations: (inputs.pricing?.allocations ?? []).map((row) => ({
              ...row,
              location: dominantLocation,
            })),
          }
        : inputs.pricing;
    // Replaces current rows only through this explicit action; cost
    // confirmation and saved versions are untouched. A provisional
    // revenue geography follows the applied delivery team; an explicitly
    // confirmed allocation is never overwritten.
    onApply({ ...inputs, staffing: rows, pricing });
    setComparing(false);
  }

  function undo() {
    if (undoRows === null) return;
    onApply({ ...inputs, staffing: undoRows });
    setUndoRows(null);
  }

  const gmPercent = (raw: string) => `${fractionToPercent(raw)}%`;
  const currentFte = (inputs.staffing ?? []).reduce(
    (sum, row) => sum + (row.quantity || 0) * (Number(row.allocation) || 0),
    0,
  );
  const estimate = advice?.estimate ?? null;

  return (
    <section
      data-testid="plan-team-panel"
      className="rounded-panel border border-divider bg-surface p-4 space-y-4"
    >
      <div>
        <h3 className="text-section text-text">Suggest a team</h3>
        <p className="text-secondary text-text-secondary">
          The AI first reads the SOW for what the scope needs — roles,
          skills and coverage, with quotes. Separately, the pricing engine
          checks what the contract fee supports at your target margin.
          Suggestions are drafts: nothing is applied or confirmed without
          you.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <PercentField label="Target margin (%)" value={targetGm} onChange={setTargetGm} />
        <Field
          label="Estimated scope effort (FTE)"
          value={requiredFte}
          onChange={setRequiredFte}
        />
        <Field
          label="Minimum onshore effort (FTE, optional)"
          value={minOnshore}
          onChange={setMinOnshore}
        />
        {!hasDates && (
          <Field
            label="Duration (weeks — contract dates unknown)"
            value={weeksOverride}
            onChange={setWeeksOverride}
          />
        )}
      </div>
      <p className="text-secondary text-text-secondary">
        Fee and dates come from Contract & pricing:{" "}
        {canonicalFee
          ? `fee ${inputs.currency ?? ""} ${canonicalFee}`
          : "no single contract fee for this pricing model — the SOW's stated price is used when available"}
        {hasDates
          ? `; term ${inputs.service_start} to ${inputs.service_end}.`
          : "; contract dates not set."}
      </p>
      <Button
        type="button"
        variant="primary"
        disabled={busy}
        data-testid="plan-team-advise"
        onClick={() => void run()}
      >
        {busy ? "Working…" : advice ? "Regenerate suggestion" : "Suggest a team"}
      </Button>
      {error && (
        <p role="alert" className="text-danger" data-testid="plan-team-error">
          {error}
        </p>
      )}
      {advice && (
        <div className="space-y-3" data-testid="plan-team-result">
          <div className="rounded-panel border border-divider p-3 space-y-2">
            <h4 className="font-medium text-text">What the scope needs</h4>
            {estimate ? (
              <>
                <p className="text-text">
                  <strong>{estimate.required_fte} FTE</strong>
                  {estimate.duration_weeks
                    ? ` over ${estimate.duration_weeks} weeks`
                    : ""}{" "}
                  <span className="text-text-secondary">
                    (AI draft from the SOW scope — review and confirm)
                  </span>
                </p>
                {estimate.roles.length > 0 && (
                  <ul className="space-y-1 text-secondary" data-testid="plan-team-roles">
                    {estimate.roles.map((role, i) => (
                      <li key={i} className="text-text">
                        {role.people != null && role.allocation != null
                          ? `${role.people} × ${fractionToPercent(role.allocation)}% `
                          : ""}
                        {role.role}
                        {role.seniority ? ` (${role.seniority})` : ""} —{" "}
                        {role.fte} FTE
                        {role.skills?.length ? ` · ${role.skills.join(", ")}` : ""}
                        {role.phase ? ` · ${role.phase}` : ""}{" "}
                        <span
                          className={
                            role.basis === "stated"
                              ? "text-ok"
                              : "text-text-secondary"
                          }
                        >
                          [{role.basis === "stated" ? "stated in SOW" : "inferred"}]
                        </span>
                        {role.evidence ? (
                          <span className="block text-text-secondary">
                            “{role.evidence}”
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {estimate.coverage && (
                  <p className="text-secondary text-text">
                    Coverage commitment: “{estimate.coverage}”
                  </p>
                )}
                {!!estimate.unknowns?.length && (
                  <ul className="list-disc pl-5 text-secondary text-text-secondary">
                    {estimate.unknowns.map((unknown, i) => (
                      <li key={i}>Unknown: {unknown}</li>
                    ))}
                  </ul>
                )}
                {estimate.evidence.length > 0 && (
                  <details className="text-secondary">
                    <summary className="cursor-pointer">Source quotes</summary>
                    <ul className="mt-1 list-disc pl-5 text-text-secondary">
                      {estimate.evidence.map((quote, i) => (
                        <li key={i}>“{quote}”</li>
                      ))}
                    </ul>
                  </details>
                )}
              </>
            ) : (
              <p className="text-text-secondary">
                No scope estimate is available — enter the FTE by hand above.
                Unknown scope stays unknown; it is not zero.
              </p>
            )}
          </div>

          <div className="rounded-panel border border-divider p-3 space-y-2">
            <h4 className="font-medium text-text">What the budget supports</h4>
            {advice.affordability === "blocked" ? (
              <ul
                className="list-disc pl-5 text-secondary text-text"
                data-testid="plan-team-blocked"
              >
                {advice.blocked_reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            ) : (
              <>
                <p className="text-text">
                  Up to <strong>{advice.max_fte_at_target} FTE</strong> at the{" "}
                  {gmPercent(advice.inputs.target_gm)} target margin
                  {advice.inputs.target_gm_provenance === "defaulted"
                    ? " (policy floor — set the deal's own target if it differs)"
                    : ""}
                  .
                </p>
                <p className="text-secondary text-text-secondary">
                  Assumptions: onshore cost ${advice.inputs.onshore_cost_per_hour}
                  /hr, offshore ${advice.inputs.offshore_cost_per_hour}/hr (
                  {advice.inputs.rates_provenance === "looked_up"
                    ? "from the active rate card"
                    : "defaults — no active rate card"}
                  ), fee {advice.inputs.revenue}, {advice.inputs.weeks} weeks.
                  All-onshore, all-offshore and mixed teams are all valid; no
                  minimum location is imposed unless you set one.
                </p>
                {advice.suggested && (
                  <p className="text-text" data-testid="plan-team-mix">
                    Suggested mix:{" "}
                    <strong>
                      {advice.suggested.onshore_fte} onshore +{" "}
                      {advice.suggested.offshore_fte} offshore
                    </strong>{" "}
                    → margin {gmPercent(advice.suggested.gm)}{" "}
                    {advice.feasible
                      ? `(meets the ${gmPercent(advice.inputs.target_gm)} target)`
                      : `(best achievable — below the ${gmPercent(advice.inputs.target_gm)} target)`}
                  </p>
                )}
                {!advice.suggested && (
                  <p className="text-text" data-testid="plan-team-no-mix">
                    No feasible mix under the current assumptions — adjust the
                    fee, term or target, or staff manually below.
                  </p>
                )}
              </>
            )}
          </div>

          {advice.caution && (
            <div
              role="alert"
              data-testid="plan-team-caution"
              className="rounded-panel border border-danger/50 bg-danger/10 p-3 space-y-2"
            >
              <p className="text-danger font-medium">{advice.caution}</p>
              <p className="text-secondary text-text">
                The scope's demand stays as estimated — it does not shrink to
                what the fee affords. Ways to close the gap (each is a
                proposal you apply deliberately; changes follow the normal
                re-approval rules):
              </p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="secondary" data-testid="resolve-fee"
                  onClick={() => onResolve?.("fee")}>
                  Increase the fee
                </Button>
                <Button type="button" variant="secondary" data-testid="resolve-scope"
                  onClick={() => onResolve?.("scope")}>
                  Reduce the scope
                </Button>
                <Button type="button" variant="secondary" data-testid="resolve-term"
                  onClick={() => onResolve?.("term")}>
                  Change the term
                </Button>
                <Button type="button" variant="secondary" data-testid="resolve-exception"
                  onClick={() => onResolve?.("exception")}>
                  Request a GM exception
                </Button>
              </div>
              <p className="text-secondary text-text-secondary">
                A GM exception permits a margin below policy through the
                existing CEO approval at submission — it does not add people
                or cure a delivery gap.
              </p>
            </div>
          )}

          {advice.warnings.map((warning, i) => (
            <p key={i} className="text-secondary text-text-secondary">
              {warning}
            </p>
          ))}

          {advice.suggested && (
            <div className="space-y-2">
              {!comparing ? (
                <Button
                  type="button"
                  data-testid="plan-team-review"
                  onClick={() => setComparing(true)}
                >
                  Review & apply proposal
                </Button>
              ) : (
                <div
                  className="rounded-panel border border-primary/40 p-3 space-y-2"
                  data-testid="plan-team-compare"
                >
                  <p className="text-text">
                    Current team: {(inputs.staffing ?? []).length} role
                    {(inputs.staffing ?? []).length === 1 ? "" : "s"} ·{" "}
                    {Math.round(currentFte * 100) / 100} FTE. Proposed:{" "}
                    {advice.suggested.onshore_fte} onshore +{" "}
                    {advice.suggested.offshore_fte} offshore FTE at margin{" "}
                    {gmPercent(advice.suggested.gm)}.
                  </p>
                  {(inputs.staffing ?? []).length > 0 && (
                    <p className="text-secondary text-warning">
                      Applying replaces the current rows. Your edits are only
                      replaced through this action — Undo restores them.
                    </p>
                  )}
                  <p className="text-secondary text-text-secondary">
                    This is a provisional comparison, not an approval. Cost
                    confirmation and saved versions are untouched.
                  </p>
                  <div className="flex gap-2">
                    <Button type="button" data-testid="plan-team-apply" onClick={applyMix}>
                      Apply proposal to team roles
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setComparing(false)}>
                      Keep current team
                    </Button>
                  </div>
                </div>
              )}
              {undoRows !== null && (
                <Button type="button" variant="secondary" data-testid="plan-team-undo" onClick={undo}>
                  Undo applied proposal
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
