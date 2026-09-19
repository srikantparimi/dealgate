import type { SowExtractedFields, SowFieldName } from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";

/**
 * The scope tab breaks the SOW into the structured lists the spec asks
 * for (outcomes, deliverables, exclusions, assumptions, dependencies,
 * acceptance, risks, client inputs). Fields the extractor does not know
 * about surface as an explicit "Not extracted" — spec §4 forbids a silent
 * blank.
 */
interface Section {
  id: string;
  title: string;
  /** Non-null when we can pull the value from the SOW extractor. */
  field: SowFieldName | null;
  helper: string;
}

const SECTIONS: Section[] = [
  {
    id: "outcomes",
    title: "Outcomes",
    field: "scope_summary",
    helper: "Business outcomes the client will realise.",
  },
  {
    id: "deliverables",
    title: "Deliverables",
    field: "deliverables",
    helper: "Named artefacts and milestones.",
  },
  {
    id: "exclusions",
    title: "Exclusions",
    field: "exclusions",
    helper: "Explicitly out of scope.",
  },
  {
    id: "assumptions",
    title: "Assumptions",
    field: "assumptions",
    helper: "Working assumptions the estimate relies on.",
  },
  {
    id: "dependencies",
    title: "Dependencies",
    field: null,
    helper: "Third parties, tools, environments the plan depends on.",
  },
  {
    id: "acceptance",
    title: "Acceptance criteria",
    field: "acceptance_criteria",
    helper: "How each deliverable is signed off.",
  },
  {
    id: "risks",
    title: "Risks",
    field: null,
    helper: "Known risks and their mitigations.",
  },
  {
    id: "client_inputs",
    title: "Client inputs",
    field: null,
    helper: "What the client must provide, and when.",
  },
];

function ScopeSection({
  section,
  fields,
}: {
  section: Section;
  fields: SowExtractedFields | null;
}) {
  const entry = section.field ? fields?.[section.field] : undefined;
  const status = entry?.status;
  const items = normalise(entry?.value);

  return (
    <section
      id={section.id}
      aria-label={section.title}
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-section text-text">{section.title}</h2>
          <p className="text-secondary text-text-secondary mt-1">
            {section.helper}
          </p>
        </div>
        {status ? (
          <StatusBadge
            tone={
              status === "confirmed"
                ? "ok"
                : status === "disputed"
                  ? "danger"
                  : "neutral"
            }
            label={status}
          />
        ) : null}
      </header>
      {items.length === 0 ? (
        <p className="mt-3 text-body text-text-secondary">Not extracted.</p>
      ) : (
        <ul className="mt-3 list-disc pl-5 space-y-1 text-body text-text">
          {items.map((line, idx) => (
            <li key={idx}>{line}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function normalise(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) return value.map((v) => String(v));
  if (typeof value === "string") {
    return value
      .split(/\r?\n|;/)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return [String(value)];
}

export function ScopeTab({ snap }: { snap: WorkspaceSnapshot }) {
  if (!snap.sow) {
    return (
      <EmptyState
        title="No SOW draft uploaded"
        description="Upload a SOW in the New SOW studio to populate scope, deliverables, assumptions and acceptance."
      />
    );
  }
  const fields = snap.sow.extracted_fields ?? null;
  return (
    <div
      className="grid gap-4 md:grid-cols-2"
      style={{ maxWidth: "960px" }}
    >
      {SECTIONS.map((s) => (
        <ScopeSection key={s.id} section={s} fields={fields} />
      ))}
    </div>
  );
}
