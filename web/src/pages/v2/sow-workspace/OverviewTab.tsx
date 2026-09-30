import { Metric } from "../../../ui-v2/Metric";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { formatPercent, formatUsd } from "./format";
import type { WorkspaceSnapshot } from "./readiness";

/**
 * Overview tab — the executive at-a-glance view (spec §8). Never shows
 * "Approved" unless the underlying package really is approved.
 *
 * S20 W3 L10: the Readiness list is rendered once — as the workspace
 * aside (see `SowWorkspace.tsx`). This tab does not render a second
 * Readiness copy. Duplicate lists let the two drift as columns evolve.
 */
export function OverviewTab({ snap }: { snap: WorkspaceSnapshot }) {
  const computed = snap.gmModel?.computed ?? null;
  const commercialTypeKnown =
    typeof snap.deal?.engagement_type === "string" &&
    snap.deal.engagement_type.length > 0;
  const gmAvailable = computed != null;
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
            <dd>{snap.deal?.owner?.name ?? "Unassigned"}</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">Next action</dt>
            <dd>{snap.deal?.next_client_action ?? "Not scheduled"}</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">Next date</dt>
            <dd>{snap.deal?.next_client_date ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text-secondary text-secondary">
              Commercial type
            </dt>
            <dd>
              {/* S20 W3 L10: render "Unknown" explicitly when the deal
                  has no engagement type — never blank, never a made-up
                  default like "fixed fee". */}
              {commercialTypeKnown
                ? snap.deal!.engagement_type!.replaceAll("_", " ")
                : "Unknown"}
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
