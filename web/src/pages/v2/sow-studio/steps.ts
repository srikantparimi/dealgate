/**
 * Step definitions and the persistent draft shape for the New SOW
 * studio (spec §13.2). Save-draft is distinct from Submit; both live
 * in the reducer + component, not this module.
 */
import type { EngagementType, UUID } from "../../../api/client";

export type StepId =
  | "source"
  | "scope"
  | "gm"
  | "routing"
  | "submit";

export interface StepDef {
  id: StepId;
  index: 1 | 2 | 3 | 4 | 5;
  title: string;
  short: string;
  purpose: string;
}

export const STEPS: StepDef[] = [
  {
    id: "source",
    index: 1,
    title: "Source & type",
    short: "Source",
    purpose:
      "Attach a file or start structured; pick a client, entity and engagement template.",
  },
  {
    id: "scope",
    index: 2,
    title: "Scope & terms",
    short: "Scope",
    purpose:
      "Verified scope, deliverables, price, term, acceptance, exclusions.",
  },
  {
    id: "gm",
    index: 3,
    title: "Build GM",
    short: "GM",
    purpose:
      "Staffing, direct costs, geographic allocation, floor checks.",
  },
  {
    id: "routing",
    index: 4,
    title: "Review routing",
    short: "Routing",
    purpose:
      "Name a Delivery, HR, Finance and Legal owner; add CEO if below floor.",
  },
  {
    id: "submit",
    index: 5,
    title: "Submit package",
    short: "Submit",
    purpose:
      "Freeze the SOW/GM versions and hand off to Delivery review.",
  },
];

export function stepByIndex(index: number): StepDef | null {
  return STEPS.find((s) => s.index === index) ?? null;
}

/**
 * The full studio state — persisted on every keystroke via `useReducer`.
 * `stagedFile` is the local File the user just picked; it is only sent
 * to S3 (via `getSowUploadUrl`) after step 1's advance rule succeeds.
 */
export interface StudioState {
  step: StepId;
  /** Highest step reached so previously-visited steps stay clickable. */
  furthest: StepId;
  source: {
    kind: "file" | "structured" | null;
    clientId: UUID | null;
    clientName: string;
    legalEntityId: UUID | null;
    sowTitle: string;
    stagedFileName: string | null;
    stagedFileSize: number | null;
    engagementType: EngagementType | null;
    sowVersionId: UUID | null;
  };
  scope: {
    scopeSummary: string;
    deliverables: string;
    price: string;
    currency: string;
    termStart: string;
    termEnd: string;
    acceptance: string;
    exclusions: string;
    payment: string;
    notice: string;
    signatories: string;
  };
  gm: {
    inputs: Record<string, string>;
    revenueUs: string;
    revenueIndia: string;
    lastComputedAt: string | null;
  };
  routing: {
    deliveryOwnerId: UUID | null;
    hrOwnerId: UUID | null;
    financeOwnerId: UUID | null;
    legalOwnerId: UUID | null;
    ceoOwnerId: UUID | null;
    ceoRequired: boolean;
    dueDate: string;
  };
  savedDraftAt: string | null;
  submittedAt: string | null;
  lastError: string | null;
}

export const INITIAL_STATE: StudioState = {
  step: "source",
  furthest: "source",
  source: {
    kind: null,
    clientId: null,
    clientName: "",
    legalEntityId: null,
    sowTitle: "",
    stagedFileName: null,
    stagedFileSize: null,
    engagementType: null,
    sowVersionId: null,
  },
  scope: {
    scopeSummary: "",
    deliverables: "",
    price: "",
    currency: "USD",
    termStart: "",
    termEnd: "",
    acceptance: "",
    exclusions: "",
    payment: "",
    notice: "",
    signatories: "",
  },
  gm: {
    inputs: {},
    revenueUs: "",
    revenueIndia: "",
    lastComputedAt: null,
  },
  routing: {
    deliveryOwnerId: null,
    hrOwnerId: null,
    financeOwnerId: null,
    legalOwnerId: null,
    ceoOwnerId: null,
    ceoRequired: false,
    dueDate: "",
  },
  savedDraftAt: null,
  submittedAt: null,
  lastError: null,
};

const STEP_ORDER: StepId[] = ["source", "scope", "gm", "routing", "submit"];

function stepIndex(id: StepId): number {
  return STEP_ORDER.indexOf(id);
}

/**
 * Advance rules per spec §13.2 table. Each returns the first blocking
 * message or null when clear. The message is shown to the user + used
 * to disable the Next button.
 */
export function advanceBlockers(state: StudioState): string[] {
  const blockers: string[] = [];
  switch (state.step) {
    case "source": {
      const s = state.source;
      if (!s.clientName.trim()) blockers.push("Pick a client.");
      if (!s.sowTitle.trim()) blockers.push("Give the SOW a title.");
      if (!s.kind) blockers.push("Stage a file or start a structured draft.");
      if (!s.engagementType) blockers.push("Pick an engagement template.");
      break;
    }
    case "scope": {
      const s = state.scope;
      if (!s.scopeSummary.trim()) blockers.push("Scope summary is required.");
      if (!s.price.trim()) blockers.push("Enter the proposed price.");
      if (!s.termStart.trim() || !s.termEnd.trim()) {
        blockers.push("Term start and end are required.");
      }
      if (!s.acceptance.trim()) {
        blockers.push("Acceptance criteria must be explicit.");
      }
      break;
    }
    case "gm": {
      if (!state.gm.revenueUs.trim() && !state.gm.revenueIndia.trim()) {
        blockers.push("Allocate revenue to US, India or both.");
      }
      if (!state.gm.lastComputedAt) {
        blockers.push("Compute the GM at least once before advancing.");
      }
      break;
    }
    case "routing": {
      const r = state.routing;
      if (!r.deliveryOwnerId) blockers.push("Name a Delivery reviewer.");
      if (!r.hrOwnerId) blockers.push("Name an HR reviewer.");
      if (!r.financeOwnerId) blockers.push("Name a Finance reviewer.");
      if (!r.legalOwnerId) blockers.push("Name a Legal reviewer.");
      if (r.ceoRequired && !r.ceoOwnerId) {
        blockers.push("Below-floor packages need a named CEO approver.");
      }
      if (!r.dueDate.trim()) blockers.push("Add a review due date.");
      break;
    }
    case "submit": {
      // Final submission button is separately gated — this is only
      // consulted when the user tries to advance further.
      break;
    }
  }
  return blockers;
}

export function canRevisitStep(state: StudioState, target: StepId): boolean {
  return stepIndex(target) <= stepIndex(state.furthest);
}

export function nextStep(id: StepId): StepId | null {
  const i = stepIndex(id);
  return STEP_ORDER[i + 1] ?? null;
}

export function prevStep(id: StepId): StepId | null {
  const i = stepIndex(id);
  return STEP_ORDER[i - 1] ?? null;
}
