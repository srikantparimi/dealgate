/**
 * Lane definitions for the SOW approvals board (spec §13.1).
 *
 * Six lanes, in visual order. Server enforces the gate transitions;
 * this file is *display only* — never move a card across lanes from
 * the client. A returned package is served under a "voided/rejected"
 * status and lands back in Draft intake for revision.
 */
import type { ApprovalPackage, ApprovalPackageStatus } from "../../../api/client";

export type LaneId =
  | "draft_intake"
  | "scope_gm"
  | "functional_review"
  | "ceo_exception"
  | "client_signature"
  | "handoff";

export interface LaneDef {
  id: LaneId;
  title: string;
  subtitle: string;
  /** Function the "My decisions" chip narrows to. */
  reviewerFn: "delivery" | "hr" | "finance" | "legal" | "ceo" | null;
}

export const LANES: LaneDef[] = [
  {
    id: "draft_intake",
    title: "Draft intake",
    subtitle: "Returned or awaiting first submission",
    reviewerFn: null,
  },
  {
    id: "scope_gm",
    title: "Scope & GM",
    subtitle: "Delivery baseline in progress",
    reviewerFn: "delivery",
  },
  {
    id: "functional_review",
    title: "Functional review",
    subtitle: "HR · Finance · Legal in parallel",
    reviewerFn: "finance",
  },
  {
    id: "ceo_exception",
    title: "CEO exception",
    subtitle: "Below-floor authority needed",
    reviewerFn: "ceo",
  },
  {
    id: "client_signature",
    title: "Client signature",
    subtitle: "Envelope out, awaiting execution",
    reviewerFn: null,
  },
  {
    id: "handoff",
    title: "Handoff",
    subtitle: "Distribution and Delivery acceptance",
    reviewerFn: null,
  },
];

/**
 * Bucket a package into its lane. `released_at` wins over any status:
 * once released, the package is in Handoff regardless of the last
 * transition label.
 */
export function laneForPackage(pkg: ApprovalPackage): LaneId {
  if (pkg.released_at) return "handoff";
  const status: ApprovalPackageStatus | string = pkg.status;
  switch (status) {
    case "pending_delivery_hr":
      return "scope_gm";
    case "pending_finance_legal":
      return "functional_review";
    case "pending_ceo_exception":
      return "ceo_exception";
    case "ready_to_sign":
      return "client_signature";
    case "voided":
    case "rejected":
      return "draft_intake";
    default:
      return "draft_intake";
  }
}
