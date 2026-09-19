/**
 * Settings & controls — secondary vertical navigation (spec §18).
 *
 * Each section is a real route (/settings/:section). Role gating is a UX
 * hint — the API still enforces every endpoint (CLAUDE.md rule 5).
 * Unauthorized sections are hidden from the nav; the section body itself
 * degrades to a scoped "You don't have access" empty state when the
 * server returns 403 (spec §4).
 */

import {
  Activity,
  Cog,
  Database,
  DollarSign,
  Gauge,
  Plug,
  ShieldAlert,
  Users,
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "general"
  | "rates"
  | "policy"
  | "people"
  | "integrations"
  | "imports"
  | "audit"
  | "system-health";

export interface SectionDef {
  id: SectionId;
  label: string;
  description: string;
  icon: LucideIcon;
  /** At least one of these groups must intersect the user's roles.
   *  Empty list = every authenticated user may see the nav entry. */
  requireAny: readonly string[];
}

/** Canonical order — spec §18. Do not reshuffle without updating the spec. */
export const SECTIONS: SectionDef[] = [
  {
    id: "general",
    label: "General",
    description: "Workspace, currency, calendars and defaults.",
    icon: Cog,
    requireAny: ["SystemAdmin", "Finance", "CEO"],
  },
  {
    id: "rates",
    label: "Rate cards",
    description: "Cost and bill bands. New versions never re-price approved GM.",
    icon: DollarSign,
    requireAny: ["SystemAdmin", "Finance", "Delivery", "HR"],
  },
  {
    id: "policy",
    label: "Margin policy",
    description: "US 35% · India 50% floors and FX convention.",
    icon: ShieldAlert,
    requireAny: ["SystemAdmin", "Finance", "CEO"],
  },
  {
    id: "people",
    label: "People & access",
    description: "Users, roles, delegations.",
    icon: Users,
    requireAny: ["SystemAdmin"],
  },
  {
    id: "integrations",
    label: "Integrations",
    description: "HubSpot, identity, storage, finance, notifications.",
    icon: Plug,
    requireAny: ["SystemAdmin"],
  },
  {
    id: "imports",
    label: "Data imports",
    description: "Legacy SOW + actuals uploads with reversible staging.",
    icon: Database,
    requireAny: ["SystemAdmin", "Finance", "CEO"],
  },
  {
    id: "audit",
    label: "Audit log",
    description: "Immutable, chain-verifiable history.",
    icon: Activity,
    requireAny: ["SystemAdmin", "Finance", "Legal", "CEO"],
  },
  {
    id: "system-health",
    label: "System health",
    description: "Queues, failed events, retries.",
    icon: Gauge,
    requireAny: ["SystemAdmin"],
  },
];

export const DEFAULT_SECTION: SectionId = "general";

export function isAllowed(
  section: SectionDef,
  groups: readonly string[],
): boolean {
  if (section.requireAny.length === 0) return true;
  return section.requireAny.some((g) => groups.includes(g));
}

export function findSection(id: string | undefined): SectionDef | null {
  const wanted = id ?? DEFAULT_SECTION;
  return SECTIONS.find((s) => s.id === wanted) ?? null;
}
