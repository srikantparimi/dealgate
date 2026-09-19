/**
 * Section 6 — Approvers.
 *
 * `GateSteps` rendered with the four function approvers (D/H/F/L) +
 * an optional CEO gate. When `payload.ceo_gate.will_trigger` is true
 * the CEO step comes in as `hold` with the "Will trigger" microcopy
 * from the v2.1 addendum (agent-brief rule "hold state").
 */
import { type ReactNode } from "react";
import type {
  SowConfirmationApproverFunction,
  SowConfirmationPayload,
} from "../../../../api/client";
import { GateSteps, type GateStep } from "../../../../ui-v2/GateSteps";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { Section } from "./Section";
import { FUNCTION_LABEL } from "./helpers";

export interface ApproversSectionProps {
  payload: SowConfirmationPayload;
}

const FUNCTION_ORDER: SowConfirmationApproverFunction[] = [
  "delivery",
  "hr",
  "finance",
  "legal",
];

export function ApproversSection({ payload }: ApproversSectionProps) {
  const willTrigger = Boolean(payload.ceo_gate?.will_trigger);
  const steps: GateStep[] = FUNCTION_ORDER.map((fn) => {
    const approver = payload.approvers?.[fn];
    return {
      id: fn,
      label: FUNCTION_LABEL[fn],
      state: "pending",
      hint: approverHint(approver),
    };
  });
  steps.push({
    id: "ceo",
    label: "CEO exception",
    state: willTrigger ? "hold" : "pending",
    hint: willTrigger
      ? "Below-floor SOW — CEO brief pre-drafted"
      : "Only if floors fail at submit",
  });

  return (
    <Section
      id="section-approvers"
      title="Approvers"
      description="Function owners are resolved from the owner table. CEO is added automatically when a floor fails."
    >
      <div className="flex flex-col gap-3">
        <GateSteps steps={steps} ariaLabel="Approval gate progress" />
        {willTrigger ? (
          <div className="flex items-center gap-2">
            <StatusBadge
              tone="warning"
              label="CEO gate — will trigger"
              data-testid="ceo-will-trigger"
            />
            <p className="text-secondary text-text-secondary">
              A CEO brief has been pre-drafted from the auto-GM run.
            </p>
          </div>
        ) : null}
      </div>
    </Section>
  );
}

function approverHint(
  approver: { user_id: string | null; source: string } | undefined,
): ReactNode {
  if (!approver) return null;
  if (!approver.user_id) return "unassigned";
  const src =
    approver.source === "group_fallback"
      ? "group fallback"
      : approver.source.replace(/_/g, " ");
  return `${approver.user_id.slice(0, 6)} · ${src}`;
}
