/**
 * Side-panel readiness view for the studio (spec §13.2 + §8).
 *
 * Every advance blocker is rendered as a warn item; met criteria are ok.
 * The panel never invents "green" — it echoes the blockers the reducer
 * produces so the user always understands why Next is disabled.
 */
import type { ReactNode } from "react";
import { ReadinessChecklist, type ReadinessItem } from "../../../ui-v2/ReadinessChecklist";
import { advanceBlockers, type StepId, type StudioState } from "./steps";
import { TEMPLATES } from "./templates";

export interface ReadinessPanelProps {
  state: StudioState;
}

export function ReadinessPanel({ state }: ReadinessPanelProps) {
  const items = buildItems(state);
  return (
    <ReadinessChecklist
      title="Step readiness"
      items={items}
    />
  );
}

function buildItems(state: StudioState): ReadinessItem[] {
  const blockers = advanceBlockers(state);
  const stepItems = stepSpecificItems(state.step, state);
  const items: ReadinessItem[] = [
    ...stepItems,
    ...blockers.map<ReadinessItem>((msg, i) => ({
      id: `blocker-${i}`,
      label: msg,
      status: "warn",
      statusLabel: "blocked",
    })),
  ];
  if (blockers.length === 0) {
    items.push({
      id: "cleared",
      label: "Advance rule met — Next is available.",
      status: "ok",
      statusLabel: "ready",
    });
  }
  return items;
}

function stepSpecificItems(
  step: StepId,
  state: StudioState,
): ReadinessItem[] {
  switch (step) {
    case "source":
      return [
        {
          id: "client-owner",
          label: "Client owner",
          status: state.source.clientId ? "ok" : "neutral",
          statusLabel: state.source.clientId ? "linked" : "not linked",
          hint: state.source.clientId
            ? undefined
            : "Pick from the search to attach an owner and agreement history.",
        },
        {
          id: "nda-msa",
          label: "NDA · MSA",
          status: "neutral",
          statusLabel: "verified in workspace",
          hint: "Coverage evidence is confirmed on the SOW workspace after submit.",
        },
        {
          id: "model",
          label: "Model selection",
          status: state.source.engagementType ? "ok" : "neutral",
          statusLabel: state.source.engagementType ? "chosen" : "pending",
          hint: state.source.engagementType
            ? TEMPLATES.find((t) => t.id === state.source.engagementType)?.name
            : undefined,
        },
      ];
    case "scope":
      return [
        {
          id: "critical-fields",
          label: "Critical commercial fields",
          status:
            state.scope.scopeSummary && state.scope.price && state.scope.termStart
              ? "ok"
              : "warn",
          statusLabel:
            state.scope.scopeSummary && state.scope.price && state.scope.termStart
              ? "captured"
              : "missing",
        },
      ];
    case "gm":
      return [
        {
          id: "geography",
          label: "Geography allocation",
          status:
            state.gm.revenueUs && state.gm.revenueIndia
              ? "ok"
              : state.gm.revenueUs || state.gm.revenueIndia
                ? "primarySubtle"
                : "warn",
          statusLabel:
            state.gm.revenueUs && state.gm.revenueIndia
              ? "US + India"
              : state.gm.revenueUs
                ? "US only"
                : state.gm.revenueIndia
                  ? "India only"
                  : "not allocated",
        },
        {
          id: "floors",
          label: "Floor policy",
          status: state.gm.lastComputedAt ? "ok" : "neutral",
          statusLabel: state.gm.lastComputedAt ? "tested" : "pending",
          hint: "US 35 % · India 50 % · mixed tested independently.",
        },
      ];
    case "routing": {
      const owners = [
        state.routing.deliveryOwnerId,
        state.routing.hrOwnerId,
        state.routing.financeOwnerId,
        state.routing.legalOwnerId,
      ];
      const named = owners.filter(Boolean).length;
      return [
        {
          id: "owners",
          label: "Accountable reviewers",
          status: named === 4 ? "ok" : "warn",
          statusLabel: `${named}/4 named`,
        },
      ];
    }
    case "submit":
      return [
        {
          id: "final",
          label: "Permitted next action",
          status: "primarySubtle" as const,
          statusLabel: "review will start",
          hint: "Submitting creates a Delivery review task and freezes the SOW/GM versions.",
        },
      ];
    default:
      return [];
  }
}

/** Marker export so tsc doesn't complain about the unused ReactNode import. */
export type _R = ReactNode;
