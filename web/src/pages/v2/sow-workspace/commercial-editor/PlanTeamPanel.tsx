/**
 * S22 · "Plan the team" — the simple front door the owner asked for.
 *
 * Fee + duration + target GM in, one click out: the AI reads the SOW
 * scope for required FTE (a draft with verbatim quotes), rates come
 * from the rate card, and the Decimal solver suggests the cheapest
 * onshore/offshore mix that hits the target — or raises an explicit
 * delivery caution when the scope needs more people than the fee
 * supports. "Apply mix" fills Calendar staffing; every value stays
 * editable and nothing is confirmed until Save.
 */
import { useEffect, useRef, useState } from "react";
import { getStaffingAdvice, type CommercialComponent, type StaffingAdvice } from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { Field } from "./Fields";

export function PlanTeamPanel({
  opportunityId,
  inputs,
  onApply,
}: {
  opportunityId: string;
  inputs: CommercialComponent;
  onApply: (next: CommercialComponent) => void;
}) {
  const [fee, setFee] = useState<string>(inputs.pricing?.total_fee ?? "");
  const [weeks, setWeeks] = useState<string>("");
  const [targetGm, setTargetGm] = useState<string>("");
  const [requiredFte, setRequiredFte] = useState<string>("");
  const [minOnshore, setMinOnshore] = useState<string>("0");
  const [advice, setAdvice] = useState<StaffingAdvice | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const autoRan = useRef(false);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const result = await getStaffingAdvice(opportunityId, {
        revenue: fee || null,
        weeks: weeks || null,
        service_start: inputs.service_start,
        service_end: inputs.service_end,
        target_gm: targetGm ? String(Number(targetGm) / 100) : null,
        required_fte: requiredFte || null,
        min_onshore_fte: minOnshore || "0",
      });
      setAdvice(result);
      if (!fee && result.inputs.revenue) setFee(result.inputs.revenue);
      if (!weeks && result.inputs.weeks) setWeeks(result.inputs.weeks);
      if (!requiredFte && result.estimate?.required_fte)
        setRequiredFte(result.estimate.required_fte);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Advice unavailable");
    } finally {
      setBusy(false);
    }
  }

  // The suggestion greets you: when the model has no staffing yet and we
  // know enough to advise (a fee or term dates), run once on open. Apply
  // stays a human decision.
  useEffect(() => {
    if (autoRan.current || advice || busy) return;
    const hasBasis = !!fee || (!!inputs.service_start && !!inputs.service_end);
    if ((inputs.staffing?.length ?? 0) > 0 || !hasBasis) return;
    autoRan.current = true;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fee, inputs.service_start, inputs.service_end, inputs.staffing?.length]);

  function applyMix() {
    if (!advice?.suggested) return;
    const binding = {
      source_id: inputs.source_id,
      source_version: inputs.source_version,
      component_id: inputs.component_id,
      profile_version: inputs.profile_version,
      policy_version: inputs.policy_version,
    };
    const mkAssignments = (
      location: "US" | "India",
      fte: number,
      costRate: string,
      prefix: string,
    ) => {
      const rows = [];
      const whole = Math.floor(fte);
      if (whole > 0)
        rows.push({
          ...binding,
          assignment_id: `${prefix}-full`,
          role: location === "US" ? "Onshore consultant" : "Offshore consultant",
          location,
          timezone: inputs.timezone ?? "America/Los_Angeles",
          currency: inputs.currency,
          quantity: whole,
          allocation: "1",
          calendar: null,
          bill_rate: null,
          cost_rate: costRate,
          rate_version: null,
          cost_version: "staffing-advice",
          start: inputs.service_start,
          end: inputs.service_end,
          cost_rate_basis: "hourly" as const,
          cost_proration: null,
        });
      if (fte - whole > 0)
        rows.push({
          ...binding,
          assignment_id: `${prefix}-half`,
          role: location === "US" ? "Onshore consultant" : "Offshore consultant",
          location,
          timezone: inputs.timezone ?? "America/Los_Angeles",
          currency: inputs.currency,
          quantity: 1,
          allocation: String(fte - whole),
          calendar: null,
          bill_rate: null,
          cost_rate: costRate,
          rate_version: null,
          cost_version: "staffing-advice",
          start: inputs.service_start,
          end: inputs.service_end,
          cost_rate_basis: "hourly" as const,
          cost_proration: null,
        });
      return rows;
    };
    onApply({
      ...inputs,
      staffing: [
        ...mkAssignments(
          "US",
          Number(advice.suggested.onshore_fte),
          advice.inputs.onshore_cost_per_hour,
          "advised-us",
        ),
        ...mkAssignments(
          "India",
          Number(advice.suggested.offshore_fte),
          advice.inputs.offshore_cost_per_hour,
          "advised-india",
        ),
      ],
    });
  }

  const gmPercent = (raw: string) => `${(Number(raw) * 100).toFixed(1)}%`;

  return (
    <section
      data-testid="plan-team-panel"
      className="rounded-panel border border-divider bg-surface p-4 space-y-3"
    >
      <div>
        <h3 className="text-section text-text">Plan the team</h3>
        <p className="text-secondary text-text-secondary">
          Fee and duration in — AI reads the SOW for the people the scope
          needs, the solver finds the cheapest mix that hits your GM target,
          and warns when the two cannot meet.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Field label="Engagement fee" value={fee} onChange={setFee} />
        <Field label="Duration (weeks)" value={weeks} onChange={setWeeks} />
        <Field label="Target GM %" value={targetGm} onChange={setTargetGm} />
        <Field
          label="Required FTE (blank = estimate from SOW)"
          value={requiredFte}
          onChange={setRequiredFte}
        />
        <Field
          label="Onshore minimum (FTE)"
          value={minOnshore}
          onChange={setMinOnshore}
        />
      </div>
      <Button
        type="button"
        variant="primary"
        disabled={busy}
        data-testid="plan-team-advise"
        onClick={() => void run()}
      >
        {busy ? "Advising…" : "Advise staffing"}
      </Button>
      {error && (
        <p role="alert" className="text-danger" data-testid="plan-team-error">
          {error}
        </p>
      )}
      {advice && (
        <div className="space-y-2" data-testid="plan-team-result">
          {advice.estimate && (
            <div className="rounded-panel border border-divider p-3">
              <p className="text-text">
                Scope estimate: <strong>{advice.estimate.required_fte} FTE</strong>
                {advice.estimate.duration_weeks
                  ? ` over ${advice.estimate.duration_weeks} weeks`
                  : ""}{" "}
                <span className="text-text-secondary">(AI draft — confirm)</span>
              </p>
              <ul className="mt-1 list-disc pl-5 text-secondary text-text-secondary">
                {advice.estimate.evidence.slice(0, 3).map((quote, i) => (
                  <li key={i}>“{quote}”</li>
                ))}
              </ul>
            </div>
          )}
          {advice.suggested && (
            <p className="text-text" data-testid="plan-team-mix">
              Suggested mix:{" "}
              <strong>
                {advice.suggested.onshore_fte} onshore +{" "}
                {advice.suggested.offshore_fte} offshore
              </strong>{" "}
              → GM {gmPercent(advice.suggested.gm)}{" "}
              {advice.feasible
                ? `(meets the ${gmPercent(advice.inputs.target_gm)} target)`
                : `(best achievable at the ${gmPercent(advice.inputs.target_gm)} target)`}
            </p>
          )}
          {advice.caution && (
            <p
              role="alert"
              data-testid="plan-team-caution"
              className="rounded-panel border border-danger/50 bg-danger/10 p-3 text-danger"
            >
              {advice.caution}
            </p>
          )}
          {advice.warnings.map((w, i) => (
            <p key={i} className="text-secondary text-text-secondary">
              {w}
            </p>
          ))}
          {advice.suggested && (
            <Button
              type="button"
              data-testid="plan-team-apply"
              onClick={applyMix}
            >
              Apply mix to Calendar staffing
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
