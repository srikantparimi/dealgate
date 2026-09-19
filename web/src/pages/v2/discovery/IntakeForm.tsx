/**
 * Adviser intake form — the left 40% panel per spec §10.
 *
 * Fields: client name + domain, associated opportunity, business
 * outcome, requested functionality, integrations, data sensitivity
 * category, delivery model, engagement type, expected dates, available
 * budget, constraints. Uploaded briefs are captured by name only in
 * this wave — a full upload path arrives with the storage story.
 *
 * The form is uncontrolled at the DOM level (values live in the parent
 * reducer) so a mid-generation cancel does not wipe user input. Every
 * label allows an explicit "Unknown" — the API accepts nullable fields
 * and prompts the user for gaps.
 */
import type { AdviserIntakeBody } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";

export interface IntakeState {
  client_name: string;
  domain: string;
  opportunity: string;
  outcome: string;
  problem: string;
  functionality: string;
  integrations: string;
  data_sensitivity: string;
  delivery_model: string;
  engagement_type: string;
  expected_start: string;
  expected_end: string;
  budget: string;
  constraints: string;
  briefs: string;
}

export const INITIAL_INTAKE: IntakeState = {
  client_name: "",
  domain: "",
  opportunity: "",
  outcome: "",
  problem: "",
  functionality: "",
  integrations: "",
  data_sensitivity: "",
  delivery_model: "",
  engagement_type: "",
  expected_start: "",
  expected_end: "",
  budget: "",
  constraints: "",
  briefs: "",
};

/** Shape the intake into the API body. `problem` is required by the
 * server; we compose it from outcome + functionality when the user
 * left the problem field blank — the API sees the exact string, so we
 * do not silently overwrite what the user typed. */
export function toApiBody(state: IntakeState): AdviserIntakeBody {
  const problemLines = [
    state.problem.trim(),
    state.outcome.trim() ? `Outcome: ${state.outcome.trim()}` : "",
    state.functionality.trim()
      ? `Functionality: ${state.functionality.trim()}`
      : "",
    state.constraints.trim() ? `Constraints: ${state.constraints.trim()}` : "",
    state.data_sensitivity.trim()
      ? `Data sensitivity: ${state.data_sensitivity.trim()}`
      : "",
  ].filter(Boolean);
  return {
    client_name: state.client_name.trim() || "Unknown",
    problem: problemLines.join("\n\n") || "Unknown",
    website: state.domain.trim() || null,
    functions: state.functionality
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    users_count: null,
    systems: state.integrations
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    geography: state.delivery_model.trim() || null,
    timeline:
      [state.expected_start, state.expected_end].filter(Boolean).join(" → ") ||
      null,
    budget: state.budget.trim() || null,
  };
}

export interface IntakeFormProps {
  value: IntakeState;
  onChange: (next: IntakeState) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  busy: boolean;
}

export function IntakeForm({
  value,
  onChange,
  onSubmit,
  onCancel,
  busy,
}: IntakeFormProps) {
  function patch<K extends keyof IntakeState>(k: K, v: IntakeState[K]) {
    onChange({ ...value, [k]: v });
  }
  const missing = !value.client_name.trim();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (missing) return;
        onSubmit();
      }}
      className="flex flex-col gap-4"
      aria-label="AI adviser intake"
    >
      <FieldPair label="Client name" required htmlFor="ai-client">
        <Input
          id="ai-client"
          value={value.client_name}
          onChange={(e) => patch("client_name", e.target.value)}
          placeholder="e.g. Acme Corp"
        />
      </FieldPair>
      <FieldPair label="Client domain" htmlFor="ai-domain">
        <Input
          id="ai-domain"
          value={value.domain}
          onChange={(e) => patch("domain", e.target.value)}
          placeholder="acme.com — Unknown is fine"
        />
      </FieldPair>
      <FieldPair label="Associated opportunity" htmlFor="ai-opp">
        <Input
          id="ai-opp"
          value={value.opportunity}
          onChange={(e) => patch("opportunity", e.target.value)}
          placeholder="HubSpot deal id (optional)"
        />
      </FieldPair>
      <FieldPair label="Business outcome" htmlFor="ai-outcome">
        <textarea
          id="ai-outcome"
          rows={3}
          className="rounded-control border border-input-border bg-surface px-3 py-2 text-body text-text focus-visible:outline-focus"
          value={value.outcome}
          onChange={(e) => patch("outcome", e.target.value)}
          placeholder="What decision does this unlock for the client?"
        />
      </FieldPair>
      <FieldPair label="Problem detail" htmlFor="ai-problem">
        <textarea
          id="ai-problem"
          rows={4}
          className="rounded-control border border-input-border bg-surface px-3 py-2 text-body text-text focus-visible:outline-focus"
          value={value.problem}
          onChange={(e) => patch("problem", e.target.value)}
          placeholder="Anything specific to describe about the request — free-form."
        />
      </FieldPair>
      <FieldPair label="Requested functionality" htmlFor="ai-func">
        <Input
          id="ai-func"
          value={value.functionality}
          onChange={(e) => patch("functionality", e.target.value)}
          placeholder="Comma-separated capabilities"
        />
      </FieldPair>
      <FieldPair label="Integrations" htmlFor="ai-int">
        <Input
          id="ai-int"
          value={value.integrations}
          onChange={(e) => patch("integrations", e.target.value)}
          placeholder="Comma-separated systems"
        />
      </FieldPair>
      <FieldPair label="Data sensitivity" htmlFor="ai-sens">
        <select
          id="ai-sens"
          className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
          value={value.data_sensitivity}
          onChange={(e) => patch("data_sensitivity", e.target.value)}
        >
          <option value="">Unknown</option>
          <option value="public">Public</option>
          <option value="internal">Internal</option>
          <option value="confidential">Confidential</option>
          <option value="regulated">Regulated (PII / PHI)</option>
        </select>
      </FieldPair>
      <FieldPair label="Delivery model" htmlFor="ai-model">
        <select
          id="ai-model"
          className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
          value={value.delivery_model}
          onChange={(e) => patch("delivery_model", e.target.value)}
        >
          <option value="">Unknown</option>
          <option value="US">US only</option>
          <option value="India">India only</option>
          <option value="Mixed">Mixed US + India</option>
        </select>
      </FieldPair>
      <FieldPair label="Engagement type" htmlFor="ai-eng">
        <select
          id="ai-eng"
          className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
          value={value.engagement_type}
          onChange={(e) => patch("engagement_type", e.target.value)}
        >
          <option value="">Unknown</option>
          <option value="staff_aug">Staff augmentation</option>
          <option value="single_resource">Single resource</option>
          <option value="fixed_price">Fixed price</option>
          <option value="assessment">Assessment</option>
          <option value="tm">Time & materials</option>
          <option value="managed_service">Managed service</option>
        </select>
      </FieldPair>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FieldPair label="Expected start" htmlFor="ai-start">
          <Input
            id="ai-start"
            type="date"
            value={value.expected_start}
            onChange={(e) => patch("expected_start", e.target.value)}
          />
        </FieldPair>
        <FieldPair label="Expected end" htmlFor="ai-end">
          <Input
            id="ai-end"
            type="date"
            value={value.expected_end}
            onChange={(e) => patch("expected_end", e.target.value)}
          />
        </FieldPair>
      </div>
      <FieldPair label="Available budget" htmlFor="ai-budget">
        <Input
          id="ai-budget"
          value={value.budget}
          onChange={(e) => patch("budget", e.target.value)}
          placeholder="e.g. $500k or Unknown"
        />
      </FieldPair>
      <FieldPair label="Constraints" htmlFor="ai-constraints">
        <textarea
          id="ai-constraints"
          rows={2}
          className="rounded-control border border-input-border bg-surface px-3 py-2 text-body text-text focus-visible:outline-focus"
          value={value.constraints}
          onChange={(e) => patch("constraints", e.target.value)}
          placeholder="Compliance, geography, timing, etc."
        />
      </FieldPair>
      <FieldPair label="Uploaded briefs" htmlFor="ai-briefs">
        <Input
          id="ai-briefs"
          value={value.briefs}
          onChange={(e) => patch("briefs", e.target.value)}
          placeholder="Reference doc name — full upload lands next sprint"
        />
      </FieldPair>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" disabled={busy || missing}>
          {busy ? "Generating…" : "Generate estimate"}
        </Button>
        {busy && onCancel ? (
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        {missing ? (
          <span className="text-secondary text-text-secondary">
            Client name is required — everything else can be Unknown.
          </span>
        ) : null}
      </div>
    </form>
  );
}

interface FieldPairProps {
  label: string;
  htmlFor: string;
  required?: boolean;
  children: React.ReactNode;
}

function FieldPair({ label, htmlFor, required, children }: FieldPairProps) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={htmlFor}>
        {label}
        {required ? (
          <span className="ml-1 text-danger" aria-hidden>
            *
          </span>
        ) : null}
      </Label>
      {children}
    </div>
  );
}
