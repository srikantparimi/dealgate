/**
 * S9 — six-step GateSteps summary for the CEO exception page.
 *
 * The CEO lands on this page from a link in Command Center or a notice
 * email. They should see where the package is in the overall approval
 * flow (spec §8) without opening the SOW workspace.
 */
import type { ApprovalPackage, CeoException } from "../../../api/client";
import { GateSteps, type GateStep, type GateState } from "../../../ui-v2/GateSteps";

export function PackageGates({
  pkg,
  exception,
}: {
  pkg: ApprovalPackage | null;
  exception: CeoException;
}) {
  const status = pkg?.status ?? null;

  // Function reviews: check which functions have already recorded a
  // decision. If any decision is not `approve`, the review is still
  // in progress from the CEO's point of view.
  const approvals = pkg?.approvals ?? [];
  const functionsApproved = new Set(
    approvals.filter((a) => a.decision === "approve").map((a) => a.function),
  );
  const functionsDone = ["delivery", "hr", "finance", "legal"].every((f) =>
    functionsApproved.has(f as never),
  );

  const decided = exception.decision != null;
  const decidedApproved = exception.decision === "approve";
  const ceoState: GateState = decided
    ? decidedApproved
      ? "done"
      : "hold"
    : "now";

  const signatureState: GateState =
    status === "ready_to_sign"
      ? "now"
      : status === "released"
        ? "done"
        : decidedApproved
          ? "now"
          : "pending";

  const handoffState: GateState =
    status === "released" ? "done" : "pending";

  const steps: GateStep[] = [
    { id: "intake", label: "Intake", state: "done" },
    {
      id: "scope",
      label: "Scope & GM",
      state: pkg ? "done" : "now",
    },
    {
      id: "reviews",
      label: "Function reviews",
      state: functionsDone ? "done" : pkg ? "now" : "pending",
    },
    {
      id: "ceo",
      label: "CEO exception",
      state: ceoState,
    },
    { id: "signature", label: "Signature", state: signatureState },
    { id: "handoff", label: "Handoff", state: handoffState },
  ];

  return <GateSteps steps={steps} ariaLabel="Package gate progress" />;
}
