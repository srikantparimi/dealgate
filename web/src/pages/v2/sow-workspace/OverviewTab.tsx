import { Link } from "react-router-dom";
import { Metric } from "../../../ui-v2/Metric";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { formatPercent, formatUsd, formatTermRange } from "./format";
import type { WorkspaceSnapshot } from "./readiness";

const ENGAGEMENT_LABELS: Record<string, string> = {
  staff_augmentation: "Staff augmentation",
  fixed_price: "Fixed price",
  time_and_materials: "T&M",
  managed_service: "Managed service",
};

/**
 * Overview tab — the executive at-a-glance view (spec §8). Never shows
 * "Approved" unless the underlying package really is approved.
 *
 * S20 W3 L10: the Readiness list is rendered once — as the workspace
 * aside (see `SowWorkspace.tsx`). This tab does not render a second
 * Readiness copy. Duplicate lists let the two drift as columns evolve.
 *
 * S21 item 4 (click-through fix): no blank fallbacks. Owner defaults
 * to the deal owner, else the uploader's short id, else an explicit
 * "Set owner" affordance (never the raw word "Unassigned"). Commercial
 * type defaults to the extractor's confirmed → suggested → deal value
 * chain, with an inline select when none landed (never "Unknown").
 * Term renders in a single "Oct 12, 2026 – Apr 12, 2027" format.
 */
export function OverviewTab({ snap }: { snap: WorkspaceSnapshot }) {
  const computed = snap.gmModel?.computed ?? null;
  // S21 item 4: commercial type default chain — extractor's confirmed
  // field, else its suggestion, else the HubSpot deal engagement type.
  // The display label uses the human form ("Fixed price" not
  // "fixed_price"); the raw snake value is kept for the inline editor.
  const commercialRaw =
    snap.sow?.engagement_type_confirmed ??
    snap.sow?.engagement_type_suggested ??
    snap.deal?.engagement_type ??
    null;
  const commercialLabel = commercialRaw
    ? (ENGAGEMENT_LABELS[commercialRaw] ?? commercialRaw.replaceAll("_", " "))
    : null;
  const gmAvailable = computed != null;
  // S21 item 4 + S21-1c item 1: owner falls back to the SOW uploader
  // by name when the deal has no owner. Never a raw id or UUID prefix
  // (T09 extension — uploader_name is resolved on the server from the
  // user table, with the `Former teammate` sentinel for deleted users).
  const dealOwnerName = snap.deal?.owner?.name ?? null;
  const uploaderName = snap.sow?.uploaded_by_name ?? null;
  const ownerDisplay = dealOwnerName
    ? dealOwnerName
    : uploaderName
      ? `Uploader · ${uploaderName}`
      : null;
  // S21 item 4: term renders in one format with explicit years.
  const termStart = snap.sow?.extracted_fields?.term_start?.value;
  const termEnd = snap.sow?.extracted_fields?.term_end?.value;
  const termDisplay = formatTermRange(
    typeof termStart === "string" ? termStart : null,
    typeof termEnd === "string" ? termEnd : null,
  );
  const nextAction = snap.deal?.next_client_action ?? null;
  const nextDate = snap.deal?.next_client_date ?? null;
  const revenue =
    formatUsd(
      computed
        ? String(
            (Number(computed.revenue_us || 0) +
              Number(computed.revenue_india || 0)) as number,
          )
        : null,
    ) ?? "Unavailable";
  const cost =
    formatUsd(
      computed
        ? String(
            (Number(computed.cost_us || 0) +
              Number(computed.cost_india || 0)) as number,
          )
        : null,
    ) ?? "Unavailable";
  const gmBlended = formatPercent(computed?.gm_blended ?? null) ?? "Unavailable";

  const pkg = snap.approvalPackage;
  const decisions = pkg?.approvals ?? [];

  return (
    <div className="space-y-6" style={{ maxWidth: "960px" }}>
      <section
        aria-label="Commercial summary"
        className="grid gap-3 sm:grid-cols-3"
      >
        <Metric label="Revenue" value={revenue} />
        <Metric label="Delivery cost" value={cost} />
        <Metric label="Combined GM" value={gmBlended} />
      </section>

      <section
        aria-label="Owner and next action"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h2 className="text-section text-text">Owner and next action</h2>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2 text-body text-text">
          <div>
            <dt className="text-text-secondary text-secondary">Owner</dt>
            <dd data-testid="overview-owner">
              {ownerDisplay ?? (
                <span className="text-text-secondary">Set owner on HubSpot deal</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">Next action</dt>
            <dd data-testid="overview-next-action">
              {nextAction ?? (
                <span className="text-text-secondary">Add in My Work</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">Next date</dt>
            <dd data-testid="overview-next-date">{nextDate ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">Term</dt>
            <dd data-testid="overview-term">{termDisplay ?? "—"}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-text-secondary text-secondary">
              Commercial type
            </dt>
            <dd data-testid="overview-commercial-type">
              {commercialLabel ?? (
                <span className="inline-flex items-center gap-2">
                  <span className="text-text-secondary">Not yet extracted</span>
                  {snap.sow?.opportunity_id ? (
                    <Link
                      className="text-primary underline text-secondary"
                      to={`/sows/${snap.sow.opportunity_id}/scope`}
                    >
                      Set on Scope tab
                    </Link>
                  ) : null}
                </span>
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section
        aria-label="Key risks"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h2 className="text-section text-text">Key risks</h2>
        {/*
          S20 W3 L10 + review §"Honest status language": when the GM has
          not been assessed, "No blockers surfaced" is a lie by omission
          — the engine never ran. Render "Not assessed" with the reason
          instead.
        */}
        {!gmAvailable ? (
          <p className="mt-3 text-body text-text-secondary">
            <span className="font-semibold">Not assessed.</span>{" "}
            Staffing and GM inputs have not been provided yet. Complete
            the delivery model to check the margin floor and surface any
            blockers.
          </p>
        ) : computed?.missing?.length ? (
          <ul className="mt-3 list-disc pl-5 text-body text-text">
            {computed.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-body text-text-secondary">
            No blockers surfaced from the GM engine.
          </p>
        )}
      </section>

      <section
        aria-label="Recent decisions"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <h2 className="text-section text-text">Recent decisions</h2>
        {decisions.length === 0 ? (
          <p className="mt-3 text-body text-text-secondary">
            No approval decisions on file yet.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {decisions.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between gap-3 text-body text-text"
              >
                <span className="capitalize">{d.function}</span>
                <StatusBadge
                  tone={
                    d.decision === "approve"
                      ? "ok"
                      : d.decision === "reject"
                        ? "danger"
                        : "warn"
                  }
                  label={d.decision.replace("_", " ")}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

