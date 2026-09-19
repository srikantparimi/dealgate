import type {
  ApprovalFunction,
  ApprovalPackage,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import type { WorkspaceSnapshot } from "./readiness";

const FUNCTIONS: { key: ApprovalFunction; label: string; hint: string }[] = [
  {
    key: "delivery",
    label: "Delivery review",
    hint: "Feasibility, risks, staffing plan.",
  },
  {
    key: "hr",
    label: "HR review",
    hint: "Named resources, lead time, ramp.",
  },
  {
    key: "finance",
    label: "Finance review",
    hint: "Rate card, FX, floors, exposure.",
  },
  {
    key: "legal",
    label: "Legal review",
    hint: "NDA/MSA coverage, T&Cs, obligations.",
  },
];

export function ApprovalsTab({ snap }: { snap: WorkspaceSnapshot }) {
  const pkg = snap.approvalPackage;
  if (!pkg) {
    return (
      <EmptyState
        title="No approval package submitted"
        description="When the GM is complete and floors are documented, Submit package to open the functional reviews."
      />
    );
  }
  const packageTone = statusTone(pkg.status);

  return (
    <div className="space-y-4" style={{ maxWidth: "960px" }}>
      <section
        aria-label="Package summary"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-section text-text">Current package</h2>
            <p className="text-secondary text-text-secondary">
              Hash {pkg.package_hash.slice(0, 12)} — submitted{" "}
              {pkg.submitted_at ?? "—"}
            </p>
          </div>
          <StatusBadge
            tone={packageTone}
            label={pkg.status.replace(/_/g, " ")}
          />
        </div>
        {pkg.floors?.requires_ceo ? (
          <p className="mt-3 text-body text-text">
            CEO margin exception is required — see the CEO exception step.
          </p>
        ) : null}
      </section>

      <section aria-label="Functional reviews" className="grid gap-3 md:grid-cols-2">
        {FUNCTIONS.map((fn) => {
          const decision = pkg.approvals.find((a) => a.function === fn.key);
          const tone: StatusTone = decision
            ? decision.decision === "approve"
              ? "ok"
              : decision.decision === "reject"
                ? "danger"
                : "warn"
            : "neutral";
          const label = decision ? decision.decision.replace("_", " ") : "Pending";
          return (
            <article
              key={fn.key}
              className="rounded-panel border border-divider bg-surface p-4"
            >
              <header className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-body font-medium text-text">{fn.label}</h3>
                  <p className="text-secondary text-text-secondary">{fn.hint}</p>
                </div>
                <StatusBadge tone={tone} label={label} />
              </header>
              {decision?.reason ? (
                <p className="mt-3 text-body text-text">
                  <span className="text-text-secondary text-secondary uppercase">
                    Comment:
                  </span>{" "}
                  {decision.reason}
                </p>
              ) : null}
            </article>
          );
        })}
      </section>
    </div>
  );
}

function statusTone(status: ApprovalPackage["status"]): StatusTone {
  switch (status) {
    case "ready_to_sign":
      return "ok";
    case "released":
      return "ok";
    case "voided":
    case "rejected":
      return "danger";
    case "pending_ceo_exception":
      return "warn";
    default:
      return "warn";
  }
}
