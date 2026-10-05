import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Save, X } from "lucide-react";
import {
  reviseForecastAssumptions,
  type ForecastAssumptions,
  type ForecastPlan,
  type ForecastPlans,
} from "../../../api/forecast";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { formatPercent } from "../sow-workspace/format";
import { PlanCommercialEditor } from "./PlanCommercialEditor";

export function NextOpportunities({
  plans,
  onSaved,
}: {
  plans: ForecastPlans;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [commercial, setCommercial] = useState<string | null>(null);
  return (
    <section aria-label="Next opportunities" className="space-y-4">
      <h2 className="text-lg font-semibold">Next opportunities</h2>
      <p className="text-secondary">
        {plans.items.length} of {plans.total} planning opportunities / Page{" "}
        {plans.page}
      </p>
      {plans.items.length === 0 && (
        <p className="text-secondary">
          No planning opportunities in this scope.
        </p>
      )}
      {plans.items.map((plan) => (
        <article
          key={plan.version_id}
          aria-label={plan.title}
          className="min-w-0 space-y-3 border-t border-divider py-4"
        >
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="break-words font-semibold">{plan.title}</h3>
              <p className="text-secondary">
                {plan.account_name ?? "Account unavailable"} / Version{" "}
                {plan.version}
              </p>
            </div>
            {plan.can_edit_assumptions && editing !== plan.id && (
              <Button variant="secondary" onClick={() => setEditing(plan.id)}>
                <Pencil className="h-4 w-4" />
                Edit assumptions
              </Button>
            )}
          </header>
          {plan.can_edit_assumptions && plan.commercial_inputs && commercial !== plan.version_id && (
            <Button variant="secondary" onClick={() => setCommercial(plan.version_id)}>
              <Pencil className="h-4 w-4" />Edit commercial terms
            </Button>
          )}
          {plan.can_edit_assumptions && plan.commercial_inputs && commercial === plan.version_id && (
            <PlanCommercialEditor key={plan.version_id} planId={plan.id} versionId={plan.version_id}
              initial={plan.commercial_inputs} onCancel={() => setCommercial(null)}
              onSaved={() => { setCommercial(null); onSaved(); }} />
          )}
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-secondary">
            <span>{plan.source_status}</span>
            <span>{plan.lifecycle.replaceAll("_", " ")}</span>
            <span>
              Win probability: {formatPercent(plan.probability) ?? "Unresolved"}
            </span>
            {plan.opportunity_id && (
              <Link
                className="text-primary underline"
                to={`/deals/${plan.opportunity_id}`}
              >
                Open linked deal
              </Link>
            )}
          </div>
          <p className="text-secondary">
            Probability source: {plan.probability_source ?? "Unconfirmed"}
          </p>
          <section className="space-y-1" aria-label="Planning assumptions">
            <h4 className="font-medium">Assumptions</h4>
            {plan.assumptions.length ? (
              plan.assumptions.map((text, i) => (
                <p key={i} className="break-words text-secondary">
                  {text}
                </p>
              ))
            ) : (
              <p className="text-secondary">No assumptions recorded.</p>
            )}
          </section>
          <section className="space-y-1" aria-label="Plan source evidence">
            <h4 className="font-medium">Source evidence</h4>
            {plan.source_evidence?.length ? (
              plan.source_evidence.map((text, i) => (
                <p key={i} className="break-words text-secondary">
                  {text}
                </p>
              ))
            ) : (
              <p className="text-secondary">Source evidence unavailable.</p>
            )}
          </section>
          <section
            aria-label="Calculation job"
            className="space-y-1 text-secondary"
          >
            <p>Calculation: {plan.job?.status ?? "No job"}</p>
            {plan.job && (
              <p>
                Attempts: {plan.job.attempts} / Next retry:{" "}
                {plan.job.next_attempt_at ?? "Not scheduled"}
              </p>
            )}
            {plan.job?.last_error && (
              <p className="text-danger">{plan.job.last_error}</p>
            )}
          </section>
          {plan.can_edit_assumptions && editing === plan.id && (
            <AssumptionEditor
              plan={plan}
              onCancel={() => setEditing(null)}
              onSaved={onSaved}
            />
          )}
        </article>
      ))}
    </section>
  );
}

const lifecycles: ForecastAssumptions["lifecycle"][] = [
  "needs_review",
  "tentative",
  "won_unsigned",
  "closed_lost",
  "dismissed",
  "expired",
];

function AssumptionEditor({
  plan,
  onCancel,
  onSaved,
}: {
  plan: ForecastPlan;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [probability, setProbability] = useState(plan.probability ?? "");
  const assumptionsId = useId();
  const [source, setSource] = useState(plan.probability_source ?? "");
  const [assumptions, setAssumptions] = useState(plan.assumptions.join("\n"));
  const [lifecycle, setLifecycle] = useState(plan.lifecycle);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await reviseForecastAssumptions(plan.id, {
        expected_version_id: plan.version_id,
        probability: probability || null,
        probability_source: source || null,
        assumptions: assumptions.split("\n").filter((line) => line.trim()),
        lifecycle: lifecycle as ForecastAssumptions["lifecycle"],
        change_reason: reason,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assumption revision failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      onSubmit={save}
      aria-label="Edit planning assumptions"
      className="space-y-3 border-l-2 border-primary pl-4"
    >
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      <fieldset disabled={busy} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1">
            Win probability (0 to 1)
            <Input
              inputMode="decimal"
              value={probability}
              onChange={(e) => setProbability(e.target.value)}
            />
          </label>
          <label className="space-y-1">
            Probability source
            <Input value={source} onChange={(e) => setSource(e.target.value)} />
          </label>
        </div>
        <label className="block space-y-1">
          Planning status
          <select
            className="block h-10 w-full rounded-md border border-divider bg-surface px-3"
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value)}
          >
            {!lifecycles.includes(
              lifecycle as ForecastAssumptions["lifecycle"],
            ) && <option value={lifecycle}>{lifecycle} (unsupported)</option>}
            {lifecycles.map((status) => (
              <option key={status} value={status}>
                {status.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <div className="space-y-1">
          <label htmlFor={assumptionsId}>Assumptions</label>
          <textarea
            id={assumptionsId}
            className="block min-h-24 w-full rounded-md border border-divider bg-surface p-3"
            value={assumptions}
            onChange={(e) => setAssumptions(e.target.value)}
          />
        </div>
        <label className="block space-y-1">
          Change reason
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            disabled={
              !reason.trim() ||
              !lifecycles.includes(
                lifecycle as ForecastAssumptions["lifecycle"],
              )
            }
          >
            <Save className="h-4 w-4" />
            {busy ? "Saving revision..." : "Save revision"}
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            <X className="h-4 w-4" />
            Cancel
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
