/**
 * SowPackageCard — a single card in the six-lane board (spec §13.1).
 *
 * Never draggable. Server enforces gate transitions. The card is
 * clickable (opens `/sows/:opportunity_id`) but individual status
 * chips act as their own links to the linked agreement records.
 */
import { Link } from "react-router-dom";
import type {
  AgreementRow,
  ApprovalFunction,
  ApprovalPackage,
} from "../../../api/client";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import { cn } from "../../../lib/cn";

const FUNCTION_LABELS: Record<ApprovalFunction, string> = {
  delivery: "D",
  hr: "H",
  finance: "F",
  legal: "L",
};

const FUNCTIONS: ApprovalFunction[] = ["delivery", "hr", "finance", "legal"];

function ageInDays(iso: string | null): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

function decisionTone(decision: string | undefined): StatusTone {
  if (decision === "approve") return "ok";
  if (decision === "reject") return "danger";
  if (decision === "request_changes") return "warn";
  return "neutral";
}

function decisionShortLabel(decision: string | undefined): string {
  if (decision === "approve") return "approved";
  if (decision === "reject") return "rejected";
  if (decision === "request_changes") return "changes";
  return "pending";
}

function agreementTone(state: string | undefined): StatusTone {
  if (!state) return "warn";
  if (state === "executed") return "ok";
  if (
    state === "expired" ||
    state === "terminated" ||
    state === "superseded"
  ) {
    return "danger";
  }
  if (state === "missing") return "warn";
  return "primarySubtle";
}

function agreementShort(state: string | undefined): string {
  if (!state) return "missing";
  return state.replace(/_/g, " ");
}

/**
 * Money formatting is display-only. Never do math here; the amount
 * comes off the server as a Decimal string.
 */
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
}

export interface PackageCardProps {
  pkg: ApprovalPackage;
  meta: CardMeta;
  /** Route target for the SOW workspace. */
  href: string;
}

export function PackageCard({ pkg, meta, href }: PackageCardProps) {
  const age = ageInDays(pkg.submitted_at);
  const value = formatMoney(meta.proposedValue, meta.currency ?? "USD");
  const belowFloor =
    pkg.floors && !pkg.floors.us_pass && !pkg.floors.india_pass;
  const mixedFloor =
    pkg.floors &&
    (pkg.floors.us_pass !== pkg.floors.india_pass || pkg.floors.requires_ceo);

  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-panel border border-divider bg-surface p-3",
        "text-body text-text transition-motion",
        "hover:border-primary/40 focus-within:border-primary/60",
      )}
      data-testid={`sow-card-${pkg.id}`}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="text-secondary text-text-secondary uppercase tracking-wide">
            {(meta.engagementType ?? "engagement").replace(/_/g, " ")}
          </p>
          <Link
            to={href}
            className="block truncate text-body font-medium text-text hover:text-primary focus-visible:outline-focus"
          >
            {meta.sowName ?? "Untitled SOW"}
          </Link>
          <p className="truncate text-secondary text-text-secondary">
            {meta.clientName ?? "Client TBD"}
          </p>
        </div>
        <div className="shrink-0 text-right text-secondary text-text-secondary">
          {age !== null ? <div>{age}d in stage</div> : <div>New</div>}
          {meta.dueDate ? <div>Due {meta.dueDate}</div> : null}
        </div>
      </header>

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-section text-text tnum">
          {value ?? "Value TBC"}
        </span>
        <span
          className={cn(
            "text-secondary tnum",
            belowFloor ? "text-danger" : "text-text-secondary",
          )}
        >
          {meta.marginPct ? `${meta.marginPct} GM` : "GM pending"}
          {meta.completeness ? ` · ${meta.completeness}` : ""}
        </span>
      </div>

      <div className="flex flex-wrap gap-1">
        <StatusBadge
          tone={agreementTone(meta.ndaAgreement?.state)}
          label={`NDA ${agreementShort(meta.ndaAgreement?.state)}`}
          className="text-secondary"
        />
        <StatusBadge
          tone={agreementTone(meta.msaAgreement?.state)}
          label={`MSA ${agreementShort(meta.msaAgreement?.state)}`}
          className="text-secondary"
        />
        {mixedFloor ? (
          <StatusBadge tone="warn" label="CEO route" />
        ) : null}
      </div>

      <div
        className="flex items-center gap-1"
        aria-label="Functional review status"
      >
        {FUNCTIONS.map((fn) => {
          const decision = pkg.approvals.find((a) => a.function === fn);
          const tone = decisionTone(decision?.decision);
          const label = decisionShortLabel(decision?.decision);
          return (
            <span
              key={fn}
              title={`${fn}: ${label}`}
              aria-label={`${fn} ${label}`}
              className={cn(
                "inline-flex h-5 w-5 items-center justify-center rounded-[6px]",
                "text-secondary font-medium",
                tone === "ok" && "bg-success-surface text-success",
                tone === "warn" && "bg-warning-surface text-warning",
                tone === "danger" && "bg-danger-surface text-danger",
                tone === "neutral" && "bg-divider text-text-secondary",
                tone === "primarySubtle" && "bg-primary-subtle text-primary",
              )}
            >
              {FUNCTION_LABELS[fn]}
            </span>
          );
        })}
      </div>

      <footer className="flex items-center justify-between gap-2 border-t border-divider pt-2">
        <span
          className="truncate text-secondary text-text-secondary"
          title={meta.ownerEmail ?? undefined}
        >
          {meta.ownerName ?? meta.ownerEmail ?? "Owner unassigned"}
        </span>
        <span className="truncate text-secondary text-text">
          {meta.nextAction ?? "Awaiting next reviewer"}
        </span>
      </footer>
    </article>
  );
}
