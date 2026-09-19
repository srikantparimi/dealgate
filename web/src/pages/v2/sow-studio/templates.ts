/**
 * Engagement templates for the New SOW studio (spec §13.2).
 *
 * The six templates map 1:1 to `EngagementType` in the API client.
 * Each template drives step 3's schema by pointing at `getGmSchema()`;
 * the field list (labels, required flags) is server-authoritative, so
 * this file only owns *display* metadata (name, blurb, mixed-model
 * capability).
 */
import type { EngagementType } from "../../../api/client";

export interface EngagementTemplate {
  id: EngagementType;
  name: string;
  short: string;
  supportsMixed: boolean;
  /** One-line hint shown next to the radio in step 1. */
  hint: string;
}

export const TEMPLATES: EngagementTemplate[] = [
  {
    id: "staff_aug",
    name: "Multi-person staff augmentation",
    short: "Staff aug",
    supportsMixed: true,
    hint: "Named resources across US/India; billable calendar and loaded cost per row.",
  },
  {
    id: "single_resource",
    name: "Single consultant",
    short: "Single consultant",
    supportsMixed: false,
    hint: "One named resource. Placement is a different template — do not confuse.",
  },
  {
    id: "fixed_price",
    name: "Fixed price project",
    short: "Fixed price",
    supportsMixed: true,
    hint: "Milestones + deliverables; effort and staffing mix drive cost.",
  },
  {
    id: "assessment",
    name: "Assessment (2 / 4 week)",
    short: "Assessment",
    supportsMixed: true,
    hint: "Prep, workshops, analysis, reporting, travel; explicit exclusions.",
  },
  {
    id: "tm",
    name: "Time & materials",
    short: "T&M",
    supportsMixed: true,
    hint: "Hourly rates with a cap; forecast value ≠ cap.",
  },
  {
    id: "managed_service",
    name: "Managed service",
    short: "Managed service",
    supportsMixed: true,
    hint: "Coverage, SLAs, recurring revenue and cost.",
  },
];

export function templateById(id: EngagementType | null): EngagementTemplate | null {
  if (!id) return null;
  return TEMPLATES.find((t) => t.id === id) ?? null;
}
