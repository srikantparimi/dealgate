import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type {
  AdviserDeliveryOption,
  AdviserEstimate,
  AdviserIntakeBody,
  AdviserQuestions,
  AdviserResult,
  AdviserTeamMember,
} from "../api/client";
import { createAdviserEstimate } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

/**
 * Opportunity Adviser intake — Marketing/Sales/Presales fill this in with
 * a short problem statement and receive either a structured estimate or
 * clarifying questions. Deterministic pricing math runs server-side.
 *
 * Deliberately does NOT expose a PDF export button (§15 risk mitigation).
 * The mandatory label at the top makes clear this is not a quote.
 */
export function AdviserIntakePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<AdviserIntakeBody>({
    client_name: "",
    problem: "",
    website: "",
    functions: [],
    users_count: undefined,
    systems: [],
    geography: "",
    timeline: "",
    budget: "",
  });
  const [result, setResult] = useState<AdviserResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.client_name.trim() || !form.problem.trim()) return;
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const payload: AdviserIntakeBody = {
        client_name: form.client_name.trim(),
        problem: form.problem.trim(),
      };
      if (form.website) payload.website = form.website;
      if (form.functions && form.functions.length > 0) payload.functions = form.functions;
      if (form.users_count !== undefined && form.users_count !== null && !Number.isNaN(form.users_count)) {
        payload.users_count = Number(form.users_count);
      }
      if (form.systems && form.systems.length > 0) payload.systems = form.systems;
      if (form.geography) payload.geography = form.geography;
      if (form.timeline) payload.timeline = form.timeline;
      if (form.budget) payload.budget = form.budget;
      const res = await createAdviserEstimate(payload);
      setResult(res);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  const label =
    result?.label ??
    "Indicative estimate, requires Delivery and Finance validation";

  return (
    <div>
      <PageHeader
        title="Opportunity Adviser"
        subtitle="Fill in what you know. The adviser drafts a team; Delivery and Finance validate before it becomes a quote."
        right={
          <Link
            to="/adviser"
            aria-label="View past estimates"
            style={{
              fontSize: 13,
              color: "#374151",
              textDecoration: "none",
              border: "1px solid #e5e7eb",
              padding: "6px 10px",
              borderRadius: 6,
            }}
          >
            Past estimates
          </Link>
        }
      />

      <div
        role="note"
        data-testid="adviser-label"
        style={{
          background: "#fef3c7",
          border: "1px solid #fcd34d",
          color: "#78350f",
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 16,
        }}
      >
        {label}
      </div>

      <form onSubmit={submit} style={{ display: "grid", gap: 12, maxWidth: 720 }}>
        <label style={fieldStyle}>
          <span style={labelStyle}>Client name *</span>
          <input
            required
            aria-label="Client name"
            value={form.client_name}
            onChange={(e) => setForm({ ...form, client_name: e.target.value })}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Problem statement *</span>
          <textarea
            required
            aria-label="Problem statement"
            rows={4}
            value={form.problem}
            onChange={(e) => setForm({ ...form, problem: e.target.value })}
            style={{ ...inputStyle, resize: "vertical" }}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Website (optional)</span>
          <input
            aria-label="Website"
            value={form.website ?? ""}
            onChange={(e) => setForm({ ...form, website: e.target.value })}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Functions (comma separated)</span>
          <input
            aria-label="Functions"
            value={(form.functions ?? []).join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                functions: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Users</span>
          <input
            aria-label="Users count"
            type="number"
            min={0}
            value={form.users_count ?? ""}
            onChange={(e) =>
              setForm({
                ...form,
                users_count: e.target.value === "" ? undefined : Number(e.target.value),
              })
            }
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Systems (comma separated)</span>
          <input
            aria-label="Systems"
            value={(form.systems ?? []).join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                systems: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Geography</span>
          <input
            aria-label="Geography"
            value={form.geography ?? ""}
            onChange={(e) => setForm({ ...form, geography: e.target.value })}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Timeline</span>
          <input
            aria-label="Timeline"
            value={form.timeline ?? ""}
            onChange={(e) => setForm({ ...form, timeline: e.target.value })}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Budget</span>
          <input
            aria-label="Budget"
            value={form.budget ?? ""}
            onChange={(e) => setForm({ ...form, budget: e.target.value })}
            style={inputStyle}
          />
        </label>

        <div>
          <button
            type="submit"
            disabled={saving || !form.client_name.trim() || !form.problem.trim()}
            style={primaryButtonStyle}
          >
            {saving ? "Drafting…" : "Draft estimate"}
          </button>
        </div>
      </form>

      <div style={{ marginTop: 24 }}>
        {error ? <ErrorState error={error} /> : null}
        {result && result.kind === "questions" ? (
          <QuestionsCard questions={result} />
        ) : null}
        {result && result.kind === "estimate" ? (
          <EstimateCard estimate={result} onOpen={() => navigate(`/adviser/${result.id}`)} />
        ) : null}
        {!result && !error && !saving ? (
          <EmptyState
            title="No draft yet"
            hint="Fill in the form and click 'Draft estimate' to see a team + cost bands."
          />
        ) : null}
      </div>
    </div>
  );
}

function QuestionsCard({ questions }: { questions: AdviserQuestions }) {
  return (
    <section
      aria-label="Clarifying questions"
      data-testid="adviser-questions"
      style={cardStyle}
    >
      <h2 style={cardTitleStyle}>Clarifying questions</h2>
      {questions.note ? (
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 4 }}>{questions.note}</p>
      ) : null}
      <ul style={{ marginTop: 8 }}>
        {questions.questions.map((q, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            {q}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EstimateCard({
  estimate,
  onOpen,
}: {
  estimate: AdviserEstimate;
  onOpen?: () => void;
}) {
  const teamColumns: Column<AdviserTeamMember & { id: string }>[] = [
    { key: "role", header: "Role", render: (r) => r.role },
    { key: "seniority", header: "Seniority", render: (r) => r.seniority },
    {
      key: "location",
      header: "Location",
      render: (r) => (
        <StatusChip tone={r.location === "US" ? "neutral" : "ok"}>
          {r.location}
        </StatusChip>
      ),
    },
    { key: "hours", header: "Hours", render: (r) => r.hours },
    {
      key: "cost_base",
      header: "Cost (base)",
      render: (r) => (
        <span style={{ color: r.is_sentinel ? "#b45309" : "#111827" }}>
          {money(r.cost_base)}
          {r.is_sentinel ? " (TBD)" : ""}
        </span>
      ),
    },
  ];
  const teamRows = estimate.team.map((m, i) => ({ ...m, id: `${i}-${m.role}` }));

  return (
    <section aria-label="Estimate" data-testid="adviser-estimate" style={cardStyle}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 8,
        }}
      >
        <div>
          <h2 style={cardTitleStyle}>Scope interpretation</h2>
          <p style={{ marginTop: 4, color: "#374151" }}>{estimate.scope}</p>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <StatusChip tone={confidenceTone(estimate.confidence)}>
            {estimate.confidence} confidence
          </StatusChip>
          {onOpen ? (
            <button type="button" onClick={onOpen} style={buttonStyle}>
              Open
            </button>
          ) : null}
        </div>
      </header>

      <h3 style={sectionTitleStyle}>Proposed team</h3>
      <Table ariaLabel="Proposed team" columns={teamColumns} rows={teamRows} />

      <h3 style={sectionTitleStyle}>Cost range</h3>
      <div style={{ display: "flex", gap: 16, fontSize: 14 }}>
        <div>
          <div style={miniLabelStyle}>Low</div>
          <div>{money(estimate.cost_low)}</div>
        </div>
        <div>
          <div style={miniLabelStyle}>Base</div>
          <div style={{ fontWeight: 600 }}>{money(estimate.cost_base)}</div>
        </div>
        <div>
          <div style={miniLabelStyle}>High</div>
          <div>{money(estimate.cost_high)}</div>
        </div>
      </div>

      <h3 style={sectionTitleStyle}>Minimum price by delivery option</h3>
      <ul style={{ display: "grid", gap: 6, listStyle: "none", padding: 0 }}>
        {estimate.options.map((opt) => (
          <OptionRow key={opt.key} option={opt} />
        ))}
      </ul>

      <h3 style={sectionTitleStyle}>Why</h3>
      <ul>
        {estimate.reasons.map((r, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            {r}
          </li>
        ))}
      </ul>

      <h3 style={sectionTitleStyle}>Sources</h3>
      {estimate.sources.length === 0 ? (
        <p style={{ color: "#6b7280", fontSize: 13 }}>None cited.</p>
      ) : (
        <ul>
          {estimate.sources.map((s, i) => (
            <li key={i} style={{ fontSize: 13, color: "#374151" }}>
              {JSON.stringify(s)}
            </li>
          ))}
        </ul>
      )}

      <footer
        style={{
          marginTop: 12,
          fontSize: 12,
          color: "#6b7280",
          display: "flex",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <span>Model: {estimate.model}</span>
        <span>Prompt: {estimate.prompt_version}</span>
        <button
          type="button"
          onClick={() => alert("Task filed for Presales review.")}
          style={{ ...buttonStyle, background: "#111827", color: "white" }}
          aria-label="Send to Presales"
        >
          Send to Presales
        </button>
      </footer>
    </section>
  );
}

function OptionRow({ option }: { option: AdviserDeliveryOption }) {
  return (
    <li
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "6px 10px",
        background: option.eligible ? "#f9fafb" : "#fef2f2",
        border: "1px solid #e5e7eb",
        borderRadius: 6,
      }}
    >
      <span>
        <strong>{option.label}</strong>
        {!option.eligible ? " (not feasible with proposed team)" : null}
      </span>
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        min: {money(option.min_price)} · cost: {money(option.cost_base)}
      </span>
    </li>
  );
}

function confidenceTone(conf: string): "ok" | "warn" | "block" | "neutral" {
  if (conf === "high") return "ok";
  if (conf === "medium") return "neutral";
  if (conf === "low") return "warn";
  return "neutral";
}

function money(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `$${n.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

const fieldStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#6b7280",
  fontWeight: 500,
};

const inputStyle: React.CSSProperties = {
  padding: "6px 10px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 14,
};

const buttonStyle: React.CSSProperties = {
  background: "white",
  border: "1px solid #e5e7eb",
  padding: "4px 10px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "#111827",
  color: "white",
  border: "none",
  padding: "8px 14px",
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
};

const cardStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 16,
  background: "white",
};

const cardTitleStyle: React.CSSProperties = {
  fontSize: 16,
  margin: 0,
  color: "#111827",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: "#374151",
  marginTop: 16,
  marginBottom: 6,
  textTransform: "uppercase",
  letterSpacing: 0.4,
};

const miniLabelStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
  textTransform: "uppercase",
};

export { EstimateCard, QuestionsCard };
