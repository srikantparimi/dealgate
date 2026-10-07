import type {
  AgreementRow,
  ApprovalPackage,
  DealDetail,
  DeliveryGmModel,
  SignedSowUpload,
  SowVersion,
  HandoffGate,
  DeliveryAcceptance,
} from "../../../api/client";
import type { ReadinessItem } from "../../../ui-v2/ReadinessChecklist";
import {
  CURRENT_APPROVAL_FUNCTIONS,
  LEGACY_APPROVAL_FUNCTIONS,
} from "../../../api/client";

/**
 * Shape of the workspace data we consult to derive the readiness list and
 * the "next valid step" primary action. Every field is optional so that a
 * missing endpoint degrades to Unavailable rows rather than blowing up
 * the page (spec §4 — name the problem, do not hide it).
 */
export interface WorkspaceSnapshot {
  deal: DealDetail | null;
  sow: SowVersion | null;
  gmModel: DeliveryGmModel | null;
  approvalPackage: ApprovalPackage | null;
  approvalHistory?: ApprovalPackage[];
  agreements: AgreementRow[];
  signedSow: SignedSowUpload | null;
  handoffGate?: HandoffGate | null;
  deliveryAcceptance?: DeliveryAcceptance | null;
}

export interface NextStep {
  label: string;
  href?: string;
  disabled: boolean;
  reason?: string;
  action?: "submit" | "commercial";
}

export interface WorkspaceActionContext {
  activeTab?: string;
  commercial?: {
    state: "idle" | "calculating" | "blocked" | "ready_to_preview" | "ready_to_save" | "saving";
    blocker?: string;
    blockerLabel?: string;
  } | null;
}

/**
 * Six-step progress rail as required by spec §8. `state` is derived from
 * the workspace snapshot; we never claim a stage is complete without the
 * server-side evidence to prove it.
 */
export type RailStepKey =
  | "intake"
  | "scope_gm"
  | "function_reviews"
  | "ceo_exception"
  | "signature"
  | "handoff";

export type RailStepState = "done" | "current" | "upcoming" | "skipped";

export interface RailStep {
  key: RailStepKey;
  label: string;
  state: RailStepState;
  href?: string;
}

/** Which tab should we land on when the user opens the workspace? */
export function defaultTabFor(snap: WorkspaceSnapshot): string {
  const status = snap.approvalPackage?.status;
  if (
    status === "pending_delivery_hr" ||
    status === "pending_finance_legal" ||
    status === "pending_ceo_exception"
  ) {
    return "approvals";
  }
  if (status === "ready_to_sign") return "signature";
  if (status === "released") return "handoff";
  // Draft — direct the user to the scope work they still owe.
  return "scope";
}

/**
 * Build the readiness checklist. Each row states its blocking reason in
 * plain English (spec §8 — never a bare "Blocked").
 */
export function buildReadiness(snap: WorkspaceSnapshot): ReadinessItem[] {
  const items: ReadinessItem[] = [];
  const accountOwner =
    snap.approvalPackage?.owner?.name ||
    snap.deal?.owner?.name ||
    "Account owner (name unavailable)";
  // S17: NDA/MSA no longer gate readiness. The upload checkbox lands as a
  // note but never a blocker; the register lives at /agreements.
  const agreementsMarked = snap.sow?.agreements_signed === true;
  items.push({
    id: "nda-msa",
    label: "NDA & MSA",
    status: agreementsMarked ? "ok" : "neutral",
    statusLabel: agreementsMarked ? "Marked signed on upload" : "Not marked",
    hint: agreementsMarked
      ? undefined
      : "The uploader did not tick 'NDA and MSA are signed'. Nothing is blocked; this is a note only.",
  });

  const scopeConfirmed = snap.sow?.confirmed_at != null;
  items.push({
    id: "scope",
    label: "Scope confirmed",
    status: scopeConfirmed ? "ok" : "warn",
    statusLabel: scopeConfirmed
      ? "Confirmed"
      : snap.sow
        ? "Draft"
        : "Unavailable",
    owner: accountOwner,
    hint: scopeConfirmed
      ? "Confirmed scope is recorded; open Scope to inspect the source fields."
      : snap.sow
        ? "Open Scope and confirm each SOW field before submitting for review."
        : "SOW draft data is unavailable. Open Scope to inspect source availability.",
  });

  const gmComputed = snap.gmModel?.computed?.complete === true;
  items.push({
    id: "gm",
    label: "GM computed",
    status: gmComputed ? "ok" : "warn",
    statusLabel: gmComputed
      ? "Complete"
      : snap.gmModel
        ? "Incomplete"
        : "Unavailable",
    owner: accountOwner,
    hint: gmComputed
      ? "Validated calculation is recorded; open Staffing & GM to inspect it."
      : snap.gmModel
        ? `${snap.gmModel.completeness_issues?.join("; ") || "Validated staffing costs or revenue are missing."} Open Staffing & GM to resolve the missing inputs.`
        : "GM data is unavailable. Open Staffing & GM to inspect the model.",
  });

  const pkg = snap.approvalPackage;
  const approvedFns = new Set(
    (pkg?.approvals ?? [])
      .filter((a) => a.decision === "approve")
      .map((a) => a.function),
  );
  const functions =
    pkg?.required_functions ??
    (pkg ? LEGACY_APPROVAL_FUNCTIONS : CURRENT_APPROVAL_FUNCTIONS);
  for (const fn of functions) {
    const ok = approvedFns.has(fn);
    const assignment = pkg?.assignments?.find((a) => a.function === fn);
    const decision = pkg?.approvals.find((a) => a.function === fn);
    items.push({
      id: `fn-${fn}`,
      label: `${fn === "hr" ? "HR" : fn[0].toUpperCase() + fn.slice(1)} review`,
      status: ok ? "ok" : pkg ? "warn" : "neutral",
      statusLabel: ok
        ? "Approved"
        : decision
          ? decision.decision.replaceAll("_", " ")
          : assignment?.blocked
            ? "Blocked"
            : pkg
              ? "Pending"
              : "Not submitted",
      owner:
        decision && decision.decision !== "approve"
          ? accountOwner
          : assignment?.blocked
            ? "SystemAdmin"
            : assignment?.approver_name ||
              decision?.approver_name ||
              (pkg ? "Reviewer name unavailable" : accountOwner),
      due: assignment?.due_date,
      hint: decision
        ? `${decision.approver_name || assignment?.approver_name || "Reviewer"}: ${decision.reason || (ok ? "Approval recorded." : "No decision reason supplied.")} ${ok ? "View the decision in Approvals." : "Resolve the review feedback in Approvals before resubmitting."}`
        : assignment
          ? assignment.blocked
            ? "No eligible reviewer is assigned. Configure an eligible reviewer in Approvals."
            : assignment.active
              ? "Decision pending. Open Approvals for the assigned reviewer's permitted actions."
              : "Queued behind the current review stage. View routing in Approvals."
          : pkg
            ? "Reviewer assignment is unavailable. Open Approvals to inspect routing."
            : "Submit the confirmed scope and complete GM model in Approvals.",
    });
  }

  // S20 W3 T20: the CEO exception row always renders when a package is
  // submitted. "Not required" is the honest verified-negative answer
  // when the margin passes the floor.
  if (pkg) {
    if (pkg.floors?.requires_ceo) {
      items.push({
        id: "ceo",
        label: "CEO margin exception",
        status: pkg.ceo_exception?.decision === "approve" ? "ok" : "warn",
        statusLabel:
          pkg.ceo_exception?.decision === "approve"
            ? "Recorded"
            : pkg.status === "pending_ceo_exception"
              ? "Pending"
              : "Queued",
        owner:
          pkg.ceo_pending_with ||
          pkg.ceo_exception?.decided_by_name ||
          "CEO (name unavailable)",
        hint:
          pkg.ceo_exception?.decision === "approve"
            ? "Exception decision recorded; inspect its conditions and validity in Approvals."
            : "Margin requires an executive exception. Open Approvals to inspect the pending decision.",
      });
    } else {
      items.push({
        id: "ceo",
        label: "CEO margin exception",
        status: "ok",
        statusLabel: "Not required",
        hint: "Margin passes the floor — no exception is required.",
      });
    }
  }

  const signed = snap.signedSow?.package_id === pkg?.id ? snap.signedSow : null;
  items.push({
    id: "signature",
    label: "Signed SOW verified",
    status: signed?.verify_status === "verified" ? "ok" : "neutral",
    statusLabel:
      signed?.verify_status === "verified"
        ? "Verified"
        : signed?.verify_status === "blocked"
          ? "Blocked"
          : signed?.verify_status === "pending"
            ? "Awaiting verification"
            : signed
              ? signed.verify_status[0].toUpperCase() +
                signed.verify_status.slice(1)
              : "Not uploaded",
    owner: accountOwner,
    hint:
      signed?.verify_status === "verified"
        ? "Verification is recorded for this package. Review Delivery acceptance in Handoff."
        : signed
          ? `${signed.verify_reason || (signed.verify_status === "pending" ? "Verify the uploaded signed document." : "Signed document verification has not passed.")} Open Signature to inspect or replace the upload.`
          : pkg?.status === "ready_to_sign"
            ? "Upload the signed document for this approved package in Signature, then verify it."
            : "Current-package approvals must finish before signed-document upload. Open Approvals to inspect the current gate.",
  });

  const acceptance =
    snap.deliveryAcceptance?.package_id === pkg?.id
      ? snap.deliveryAcceptance
      : null;
  const acceptanceKnown =
    snap.deliveryAcceptance !== undefined && snap.deliveryAcceptance !== null
      ? acceptance !== null
      : snap.deliveryAcceptance === null && snap.handoffGate != null;
  const accepted =
    acceptance?.staffing_confirmed === true &&
    acceptance.billing_setup_confirmed === true &&
    acceptance.po_confirmed === true;
  items.push({
    id: "delivery-acceptance",
    label: "Delivery acceptance",
    status: accepted ? "ok" : acceptanceKnown ? "warn" : "neutral",
    statusLabel: !acceptanceKnown
      ? "Unavailable"
      : accepted
        ? "Recorded"
        : acceptance
          ? "Incomplete"
          : "Not recorded",
    owner: "Delivery",
    hint: !acceptanceKnown
      ? "Delivery acceptance data is unavailable here. Open Handoff to load the recorded checks."
      : accepted
        ? "Staffing, billing setup and PO confirmations are recorded. Open Handoff to inspect release readiness."
        : "Delivery must confirm staffing, billing setup and PO in Handoff before release.",
  });

  const handoffDone = signed?.released_at != null;
  items.push({
    id: "handoff",
    label: "Handoff released",
    status: handoffDone ? "ok" : "neutral",
    statusLabel: handoffDone ? "Released" : "Not released",
    owner: accountOwner,
    hint: handoffDone
      ? "Release is recorded. Open Handoff to view the release receipt; downstream work is not inferred from release."
      : snap.handoffGate
        ? snap.handoffGate.ok
          ? "Release checks passed. The account owner can release from Handoff."
          : `${snap.handoffGate.reasons.join("; ") || "Release checks have not passed."} Open Handoff to inspect the blocking checks.`
        : "Release checks are unavailable here. Open Handoff to load current checks before release.",
  });

  return items;
}

/**
 * Compute the "one primary action" for the RecordHeader. If the action is
 * disabled we always attach a `reason` so the readiness panel can echo
 * "why" — spec §8 forbids a bare disabled button.
 */
export function nextValidStep(
  snap: WorkspaceSnapshot,
  context: WorkspaceActionContext = {},
): NextStep {
  const pkg = snap.approvalPackage;
  const status = pkg?.status;

  if (status === "pending_delivery_hr" || status === "pending_finance_legal") {
    return { label: "View review status", href: "approvals", disabled: false };
  }
  if (status === "pending_ceo_exception") {
    return {
      label: "Awaiting CEO decision",
      href: "approvals",
      disabled: false,
    };
  }
  if (pkg && status === "ready_to_sign") {
    if (pkg.ceo_exception?.conditions_unmet)
      return {
        label: `Blocked: ${pkg.ceo_exception.conditions_text}`,
        href: "approvals",
        disabled: false,
        reason: `Owner: ${pkg.owner?.name ?? "Account owner"}. Evidence of satisfied CEO conditions is required.`,
      };
    if (pkg.ceo_exception?.expired)
      return {
        label: "Resolve expired CEO exception",
        href: "approvals",
        disabled: false,
      };
    if (
      snap.signedSow?.package_id === pkg.id &&
      snap.signedSow?.verify_status === "verified"
    ) {
      return {
        label: "Review handoff",
        href: "handoff",
        disabled: false,
        reason: snap.handoffGate
          ? snap.handoffGate.ok
            ? "Release checks passed; the account owner may release from Handoff."
            : snap.handoffGate.reasons.join("; ") ||
              "Release checks have not passed."
          : "Load current Delivery acceptance and release checks in Handoff.",
      };
    }
    return { label: "Prepare signature", href: "signature", disabled: false };
  }
  if (status === "released")
    return { label: "View handoff", href: "handoff", disabled: false };

  if (!snap.sow || snap.sow.confirmed_at == null) {
    return {
      label: "Complete scope",
      href: "scope",
      disabled: !snap.sow,
      reason: !snap.sow ? "No SOW draft uploaded yet." : undefined,
    };
  }
  if (!snap.gmModel?.computed?.complete) {
    if (context.activeTab === "staffing" && context.commercial) {
      const commercial = context.commercial;
      if (commercial.state === "blocked")
        return {
          label: `Fix ${commercial.blockerLabel ?? "financial input"}`,
          action: "commercial",
          disabled: false,
          reason: commercial.blocker,
        };
      if (commercial.state === "ready_to_save")
        return {
          label: "Save financial version",
          action: "commercial",
          disabled: false,
        };
      if (commercial.state === "ready_to_preview")
        return {
          label: "Calculate financials",
          action: "commercial",
          disabled: false,
        };
      if (commercial.state === "calculating" || commercial.state === "saving")
        return {
          label: commercial.state === "saving" ? "Saving financials…" : "Calculating financials…",
          action: "commercial",
          disabled: true,
        };
      return {
        label: "Review financial inputs",
        action: "commercial",
        disabled: false,
        reason: "Review the current Staffing & GM draft and its named blockers.",
      };
    }
    return {
      label: "Open Staffing & GM",
      href: "staffing",
      disabled: false,
      reason:
        snap.gmModel?.completeness_issues?.join("; ") ||
        "Missing validated staffing costs or revenue.",
    };
  }
  if (!pkg || status === "voided" || status === "rejected") {
    const returned = pkg?.approvals.find((a) => a.decision !== "approve");
    return {
      label:
        status === "rejected"
          ? "Resolve review"
          : snap.gmModel?.computed?.policy?.requires_ceo
            ? "Submit with CEO exception"
            : "Submit for approval",
      href: "approvals",
      disabled: false,
      action: "submit",
      reason: returned ? `${returned.function}: ${returned.reason}` : undefined,
    };
  }
  return {
    label: "View handoff",
    href: "handoff",
    disabled: false,
  };
}

/** Compose the six-step rail (spec §8). */
export function buildRail(snap: WorkspaceSnapshot): RailStep[] {
  const scopeDone = snap.sow?.confirmed_at != null;
  const gmDone = snap.gmModel?.computed?.complete === true;
  const pkg = snap.approvalPackage;
  const status = pkg?.status ?? null;
  const reviewsDone =
    status === "ready_to_sign" ||
    status === "pending_ceo_exception" ||
    status === "released";
  const ceoRequired = pkg?.floors?.requires_ceo === true;
  const ceoDone =
    ceoRequired && (status === "ready_to_sign" || status === "released");
  const currentSigned =
    snap.signedSow?.package_id === pkg?.id ? snap.signedSow : null;
  const signedDone = currentSigned?.verify_status === "verified";
  const handoffDone = currentSigned?.released_at != null;

  const rail: RailStep[] = [
    { key: "intake", label: "Intake", state: snap.sow ? "done" : "current" },
    {
      key: "scope_gm",
      label: "Scope & GM",
      state:
        scopeDone && gmDone
          ? "done"
          : scopeDone
            ? "current"
            : snap.sow
              ? "current"
              : "upcoming",
      href: "scope",
    },
    {
      key: "function_reviews",
      label: "Function reviews",
      state: reviewsDone ? "done" : pkg ? "current" : "upcoming",
      href: "approvals",
    },
    {
      key: "ceo_exception",
      label: "CEO exception",
      state: !ceoRequired
        ? "skipped"
        : ceoDone
          ? "done"
          : status === "pending_ceo_exception"
            ? "current"
            : "upcoming",
      href: "approvals",
    },
    {
      key: "signature",
      label: "Signature",
      state: signedDone
        ? "done"
        : status === "ready_to_sign"
          ? "current"
          : "upcoming",
      href: "signature",
    },
    {
      key: "handoff",
      label: "Handoff",
      state: handoffDone ? "done" : signedDone ? "current" : "upcoming",
      href: "handoff",
    },
  ];

  return rail;
}

export function agreementValid(_a: AgreementRow): boolean {
  // S17: an uploaded agreement row IS the record — there's no state or
  // expiry to gate on. Kept as a helper so callers don't need to change
  // shape; always returns true.
  return true;
}

export function workspaceTitle(snap: WorkspaceSnapshot): string {
  const fields = snap.sow?.extracted_fields as
    | Record<string, { value?: unknown }>
    | undefined;
  const title = fields?.sow_title?.value ?? fields?.title?.value;
  if (typeof title === "string" && title.trim()) return title.trim();
  return [
    snap.deal?.client_name ?? "SOW",
    snap.deal?.engagement_type?.replaceAll("_", " "),
  ]
    .filter(Boolean)
    .join(" · ");
}
