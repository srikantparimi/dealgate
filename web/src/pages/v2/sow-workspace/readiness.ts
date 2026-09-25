import type {
  AgreementRow,
  ApprovalPackage,
  DealDetail,
  DeliveryGmModel,
  SignedSowUpload,
  SowVersion,
} from "../../../api/client";
import type { ReadinessItem } from "../../../ui-v2/ReadinessChecklist";

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
}

export interface NextStep {
  label: string;
  href?: string;
  disabled: boolean;
  reason?: string;
  action?: "submit";
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
  const nda = snap.agreements.find(
    (a) => a.kind === "NDA" && agreementValid(a),
  );
  const msa = snap.agreements.find(
    (a) => a.kind === "MSA" && agreementValid(a),
  );

  items.push({
    id: "nda",
    label: "NDA in force",
    status: nda ? "ok" : "warn",
    statusLabel: nda ? "Executed" : "Missing",
    hint: nda ? undefined : "NDA missing - blocks signature, not review.",
  });
  items.push({
    id: "msa",
    label: "MSA in force",
    status: msa ? "ok" : "warn",
    statusLabel: msa ? "Executed" : "Missing",
    hint: msa ? undefined : "MSA missing - blocks signature, not review.",
  });

  const scopeConfirmed = snap.sow?.confirmed_at != null;
  items.push({
    id: "scope",
    label: "Scope confirmed",
    status: scopeConfirmed ? "ok" : "warn",
    statusLabel: scopeConfirmed ? "Confirmed" : "Draft",
    hint: scopeConfirmed
      ? undefined
      : "Owner must confirm each SOW field before submitting for review.",
  });

  const gmComputed = snap.gmModel?.computed?.complete === true;
  items.push({
    id: "gm",
    label: "GM computed",
    status: gmComputed ? "ok" : "warn",
    statusLabel: gmComputed ? "Complete" : "Incomplete",
    hint: gmComputed
      ? undefined
      : "Complete the delivery model — staffing, cost lines and revenue.",
  });

  const pkg = snap.approvalPackage;
  const approvedFns = new Set(
    (pkg?.approvals ?? [])
      .filter((a) => a.decision === "approve")
      .map((a) => a.function),
  );
  const functions: ("delivery" | "hr" | "finance" | "legal")[] = [
    "delivery",
    "hr",
    "finance",
    "legal",
  ];
  for (const fn of functions) {
    const ok = approvedFns.has(fn);
    const assignment = pkg?.assignments?.find(a => a.function === fn);
    const decision = pkg?.approvals.find(a => a.function === fn);
    items.push({
      id: `fn-${fn}`,
      label: `${fn === "hr" ? "HR" : fn[0].toUpperCase() + fn.slice(1)} review`,
      status: ok ? "ok" : pkg ? "warn" : "neutral",
      statusLabel: ok ? "Approved" : decision ? decision.decision.replaceAll("_", " ") : assignment?.blocked ? "Blocked" : pkg ? "Pending" : "Not submitted",
      hint: decision?.reason ?? (assignment ? assignment.blocked ? "Owner: SystemAdmin. Configure an eligible reviewer." : `${assignment.active ? "Pending with" : "Queued for"} ${assignment.approver_name}` : undefined),
    });
  }

  if (pkg?.floors?.requires_ceo) {
    items.push({
      id: "ceo",
      label: "CEO margin exception",
      status: pkg.ceo_exception?.decision === "approve" ? "ok" : "warn",
      statusLabel:
        pkg.ceo_exception?.decision === "approve" ? "Recorded" : pkg.status === "pending_ceo_exception" ? "Pending" : "Queued",
    });
  }

  const signed = snap.signedSow;
  items.push({
    id: "signature",
    label: "Signed SOW verified",
    status: signed?.verify_status === "verified" ? "ok" : "neutral",
    statusLabel:
      signed?.verify_status === "verified"
        ? "Verified"
        : signed?.verify_status === "blocked"
          ? "Blocked"
          : "Not uploaded",
    hint:
      signed?.verify_status === "blocked"
        ? "Uploaded PDF does not match approved package — see Signature tab."
        : undefined,
  });

  const handoffDone = signed?.released_at != null;
  items.push({
    id: "handoff",
    label: "Handoff released",
    status: handoffDone ? "ok" : "neutral",
    statusLabel: handoffDone ? "Released" : "Not released",
  });

  return items;
}

/**
 * Compute the "one primary action" for the RecordHeader. If the action is
 * disabled we always attach a `reason` so the readiness panel can echo
 * "why" — spec §8 forbids a bare disabled button.
 */
export function nextValidStep(snap: WorkspaceSnapshot): NextStep {
  const pkg = snap.approvalPackage;
  const status = pkg?.status;

  if (status === "pending_delivery_hr" || status === "pending_finance_legal") {
    return { label: "View review status", href: "approvals", disabled: false };
  }
  if (status === "pending_ceo_exception") {
    return { label: "Awaiting CEO decision", href: "approvals", disabled: false };
  }
  if (pkg && status === "ready_to_sign") {
    if (pkg.ceo_exception?.conditions_unmet) return { label: `Blocked: ${pkg.ceo_exception.conditions_text}`, href: "approvals", disabled: false, reason: `Owner: ${pkg.owner?.name ?? "Account owner"}. Evidence of satisfied CEO conditions is required.` };
    if (pkg.ceo_exception?.expired) return { label: "Resolve expired CEO exception", href: "approvals", disabled: false };
    return { label: "Prepare signature", href: "signature", disabled: false };
  }
  if (status === "released") return { label: "View handoff", href: "handoff", disabled: false };

  if (!snap.sow || snap.sow.confirmed_at == null) {
    return {
      label: "Complete scope",
      href: "scope",
      disabled: !snap.sow,
      reason: !snap.sow ? "No SOW draft uploaded yet." : undefined,
    };
  }
  if (!snap.gmModel?.computed?.complete) {
    return {
      label: "Open Staffing & GM",
      href: "staffing",
      disabled: false,
      reason: snap.gmModel?.completeness_issues?.join("; ") || "Missing validated staffing costs or revenue.",
    };
  }
  if (!pkg || status === "voided" || status === "rejected") {
    const returned = pkg?.approvals.find(a => a.decision !== "approve");
    return {
      label: status === "rejected" ? "Resolve review" : "Submit for approval",
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
  const signedDone = snap.signedSow?.verify_status === "verified";
  const handoffDone = snap.signedSow?.released_at != null;

  const rail: RailStep[] = [
    { key: "intake", label: "Intake", state: snap.sow ? "done" : "current" },
    {
      key: "scope_gm",
      label: "Scope & GM",
      state: scopeDone && gmDone
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
      state: handoffDone
        ? "done"
        : signedDone
          ? "current"
          : "upcoming",
      href: "handoff",
    },
  ];

  return rail;
}

export function agreementValid(a: AgreementRow): boolean {
  return a.state === "executed" && (!a.expiry || a.expiry >= new Date().toISOString().slice(0, 10));
}

export function workspaceTitle(snap: WorkspaceSnapshot): string {
  const fields = snap.sow?.extracted_fields as Record<string, { value?: unknown }> | undefined;
  const title = fields?.sow_title?.value ?? fields?.title?.value;
  if (typeof title === "string" && title.trim()) return title.trim();
  return [snap.deal?.client_name ?? "SOW", snap.deal?.engagement_type?.replaceAll("_", " ")].filter(Boolean).join(" · ");
}
