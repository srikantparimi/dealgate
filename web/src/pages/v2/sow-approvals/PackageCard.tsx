/**
 * SowPackageCard — DealGate v2.1 prototype (lines 204–216, 546–557).
 *
 * Card layout:
 *   - Header row: bold client, right-aligned value.
 *   - Description row: engagement type / short summary.
 *   - GM chip (ok / warn / bad / neutral) with the outcome text.
 *   - NDA + MSA chip pair with muted "NDA" / "MSA" labels.
 *   - FunctionMark row (D / H / F / L, 22×18) followed by "n/4 reviews".
 *   - Left stripe per state (bad / warn / prog).
 *   - Owner + next-action + age foot.
 *
 * Never draggable. Server enforces gate transitions.
 */
import { Link } from "react-router-dom";
import type {
  AgreementRow,
  ApprovalFunction,
  ApprovalPackage,
} from "../../../api/client";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import {
  FunctionMarkRow,
  type FunctionState,
} from "../../../ui-v2/FunctionMark";
import { cardStripeClass, type CardStripeVariant } from "../../../ui-v2/CardStripe";
import { cn } from "../../../lib/cn";

function ageInDays(iso: string | null): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

function agreementTone(state: string | undefined): StatusTone {
  if (!state) return "warning";
  if (state === "executed") return "success";
  if (
    state === "expired" ||
    state === "terminated" ||
    state === "superseded"
  ) {
    return "danger";
  }
  if (state === "missing") return "warning";
  return "progress";
}

function agreementShort(state: string | undefined): string {
  if (!state) return "Missing";
  if (state === "executed") return "OK";
  return state.replace(/_/g, " ");
}

function decisionState(decision: string | undefined): FunctionState {
  if (decision === "approve") return "ok";
  if (decision === "reject") return "bad";
  if (decision === "request_changes") return "progress";
  return "pending";
}

function formatMoney(amount: string | null | undefined, currency = "USD") {
  if (amount === null || amount === undefined || amount === "") return null;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(Number(amount));
  } catch {
    return `$${amount}`;
  }
}

function pkgStripe(pkg: ApprovalPackage): CardStripeVariant {
  if (pkg.status === "voided" || pkg.status === "rejected") return "blocked";
  if (pkg.floors?.requires_ceo) return "blocked";
  if (pkg.status === "pending_finance_legal") return "at-risk";
  if (pkg.status === "pending_delivery_hr") return "in-progress";
  return null;
}

export interface CardMeta {
  clientName?: string | null;
  sowName?: string | null;
  engagementType?: string | null;
  ownerName?: string | null;
  ownerEmail?: string | null;
  proposedValue?: string | null;
  currency?: string | null;
  marginPct?: string | null;
  completeness?: string | null;
  nextAction?: string | null;
  ndaAgreement?: AgreementRow | null;
  msaAgreement?: AgreementRow | null;
  dueDate?: string | null;
  /**
   * S10-02: sow_version.governance_status. When it is
   * ``legacy_not_evidenced`` the card renders a neutral "Legacy" chip
   * so reviewers instantly see the record was imported, not signed
   * through the pipeline. Other values render nothing.
   */
  governanceStatus?: string | null;
}

export interface PackageCardProps {
  pkg: ApprovalPackage;
  meta: CardMeta;
  /** Route target for the SOW workspace. */
  href: string;
}

const FUNCTIONS: ApprovalFunction[] = ["delivery", "hr", "finance", "legal"];

export function PackageCard({ pkg, meta, href }: PackageCardProps) {
  const age = ageInDays(pkg.submitted_at);
  const value = formatMoney(meta.proposedValue, meta.currency ?? "USD");
  const belowFloor = pkg.floors?.requires_ceo === true;
  const gmTone: StatusTone = meta.marginPct
    ? belowFloor
      ? "danger"
      : "success"
    : "neutral";
  const gmLabel = meta.marginPct
    ? `${meta.marginPct}${belowFloor ? " · below floor" : ""}`
    : meta.completeness ?? "GM pending";

  const states: Partial<Record<"D" | "H" | "F" | "L", FunctionState>> = {};
  const LETTER: Record<ApprovalFunction, "D" | "H" | "F" | "L"> = {
    delivery: "D",
    hr: "H",
    finance: "F",
    legal: "L",
  };
  for (const fn of FUNCTIONS) {
    const dec = pkg.approvals.find((a) => a.function === fn);
    states[LETTER[fn]] = decisionState(dec?.decision);
  }

  return (
    <Link
      to={href}
      data-testid={`sow-card-${pkg.id}`}
      className={cn(
        "flex flex-col gap-[6px] rounded-[8px] border border-border bg-surface",
        "px-3 py-[10px] text-[13px] text-text",
        "transition-motion hover:border-borderStrong",
        "focus-visible:outline-focus",
        cardStripeClass(pkgStripe(pkg)),
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold text-text truncate">
          {meta.clientName ?? meta.sowName ?? "Untitled SOW"}
        </span>
        {value ? (
          <span className="tnum text-[12px] text-text-secondary">{value}</span>
        ) : null}
      </div>
      {meta.sowName || meta.engagementType ? (
        <div className="text-[12px] text-text-secondary truncate">
          {[meta.sowName, meta.engagementType]
            .filter(Boolean)
            .join(" · ")}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-[4px]">
        <StatusBadge tone={gmTone} label={gmLabel} />
        {meta.governanceStatus === "legacy_not_evidenced" ? (
          <StatusBadge
            tone="neutral"
            label="Legacy"
            data-testid="legacy-chip"
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-[4px]">
        <span className="text-[11px] text-text-muted">NDA</span>
        <StatusBadge
          tone={agreementTone(meta.ndaAgreement?.state)}
          label={agreementShort(meta.ndaAgreement?.state)}
        />
        <span className="text-[11px] text-text-muted ml-1">MSA</span>
        <StatusBadge
          tone={agreementTone(meta.msaAgreement?.state)}
          label={agreementShort(meta.msaAgreement?.state)}
        />
      </div>

      <FunctionMarkRow states={states} />

      <div className="mt-1 flex items-center justify-between text-[12px] text-text-muted">
        <span className="truncate">
          {meta.ownerName ?? meta.ownerEmail
            ? `${meta.ownerName ?? meta.ownerEmail} · `
            : ""}
          {meta.nextAction ?? "Awaiting next reviewer"}
        </span>
        {age !== null ? (
          <span className="tnum shrink-0">{age}d</span>
        ) : null}
      </div>
    </Link>
  );
}
