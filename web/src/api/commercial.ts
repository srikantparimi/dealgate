import {
  request,
  type DeliveryGmModel,
  type DeliveryComputedResult,
} from "./client";

export interface PeriodCost {
  source_id: string;
  month: string;
  location: string;
  amount: string | null;
  description?: string | null;
}
export interface Allocation {
  month: string;
  location: string;
  weight: string;
}
export interface RecurringFee {
  location: string;
  amount: string | null;
}
export interface MspAdjustment {
  source_id: string;
  month: string;
  location: string;
  kind: string;
  amount: string | null;
}
export interface MspUsage extends CommercialQuantity {
  unit: string;
  included_quantity: string | null;
  unit_rate: string | null;
}
export interface CommercialPricing {
  adjustments?: MspAdjustment[];
  usage?: MspUsage[];
  milestones?: CommercialMilestone[];
  rate?: string | null;
  unit?: string;
  quantities?: CommercialQuantity[];
  contractual_basis?: string | null;
  estimates?: CommercialQuantity[];
  approved_usage?: CommercialQuantity[];
  cap?: string | null;
  minimum?: string | null;
  limit_allocation_basis?: string | null;
  calendar_estimates?: boolean;
  total_fee?: string | null;
  allocations?: Allocation[];
  allocation_basis?: string | null;
  minor_unit?: string | null;
  rates?: CommercialStaffingRate[];
  components?: CommercialComponent[];
  shared_cost_allocations?: {
    source_id: string;
    component_id: string;
    weight: string;
  }[];
  fx_rates?: {
    currency: string;
    rate: string | null;
    version: string | null;
    as_of: string | null;
  }[];
  fees?: RecurringFee[];
  proration?: string | null;
  included_scope?: string | null;
  [key: string]: unknown;
}
export interface CommercialMilestone {
  milestone_id: string;
  planned_date: string | null;
  location: string;
  amount: string | null;
  acceptance_conditions: string | null;
  approved_invoice_ref?: string | null;
  recognized_revenue_ref?: string | null;
}
export interface CommercialQuantity {
  source_id: string;
  month: string;
  location: string;
  quantity: string | null;
}
export interface CalendarHours {
  scheduled: string;
  billable: string;
  paid: string;
}
export interface CommercialCalendar {
  calendar_id: string;
  version: string;
  timezone: string;
  coverage_start: string;
  coverage_end: string;
  week: CalendarHours[];
  overrides: { day: string; hours: CalendarHours; reason: string }[];
}
export interface CommercialStaffing {
  assignment_id: string;
  source_id: string;
  source_version: string;
  component_id: string;
  profile_version: string;
  policy_version: string;
  role: string;
  location: string | null;
  timezone: string;
  currency: string | null;
  quantity: number;
  allocation: string;
  calendar: CommercialCalendar | null;
  bill_rate: string | null;
  cost_rate: string | null;
  rate_version: string | null;
  cost_version: string | null;
  cost_rate_basis?: "hourly" | "monthly" | null;
  cost_proration?: "full_month" | null;
  start?: string | null;
  end?: string | null;
  seniority?: string | null;
  /** Total per-person hours across the role dates. */
  hours_billable?: string | null;
}
export interface CommercialStaffingRate {
  assignment_id: string;
  basis: string;
  rate: string | null;
  version: string | null;
  hours_per_day: string | null;
  proration: string | null;
}
export interface CommercialComponent {
  component_id: string;
  version: string;
  source_id: string;
  source_version: string;
  workstream_id: string;
  profile: string;
  profile_version: string;
  policy_version: string;
  source_evidence: string[];
  service_start: string | null;
  service_end: string | null;
  timezone: string | null;
  currency: string | null;
  billing_cadence: string | null;
  cost_basis: string | null;
  costs_confirmed: boolean;
  costs: PeriodCost[];
  pricing: CommercialPricing | null;
  staffing: CommercialStaffing[];
}
export interface CommercialSchedule {
  calendar_rows?: {
    month: string;
    assignment: CommercialStaffing;
    period_start: string;
    period_end: string;
    scheduled_hours: string | null;
    billable_hours: string | null;
    paid_hours: string | null;
    days: { day: string; scheduled_hours: string; billable_hours: string; paid_hours: string; reason: string | null }[];
  }[];
  component?: CommercialComponent;
  rows: {
    month: string;
    location: string;
    revenue: string;
    cost: string | null;
  }[];
  children?: CommercialSchedule[];
  status: string;
  missing: { field?: string; key?: string; reason?: string; line?: number | null; role?: string | null }[];
}
export interface CommercialSnapshot {
  schedule: CommercialSchedule;
  [key: string]: unknown;
}
export interface CommercialPreview {
  computed?: DeliveryComputedResult;
  commercial_snapshot?: CommercialSnapshot;
}
export interface CommercialRegistry {
  profiles: {
    key: string;
    version: string;
    required_fields: string[];
    calculation_available: boolean;
  }[];
  calculation_version: string;
  policy: { version: string; us_floor: string; india_floor: string };
}
export const getCommercialProfiles = () =>
  request<CommercialRegistry>("/delivery-model/commercial/profiles");
export const previewCommercial = (inputs: CommercialComponent) =>
  request<CommercialPreview>("/delivery-model/commercial/preview", {
    method: "POST",
    body: JSON.stringify(inputs),
  });
export const saveCommercialVersion = (
  opportunityId: string,
  body: {
    sow_version_id: string;
    expected_gm_model_id: string | null;
    inputs: CommercialComponent;
    change_reason: string;
  },
) =>
  request<{ gm_model: DeliveryGmModel }>(
    `/delivery-model/${opportunityId}/commercial/versions`,
    { method: "POST", body: JSON.stringify(body) },
  );

/** S22 · one server-persisted Staffing & GM working draft per
 * opportunity, so the plan survives reloads and is visible on every
 * surface. NOT an immutable GM version — Save version still creates
 * those explicitly. */
export interface CommercialDraftResponse {
  exists: boolean;
  inputs?: CommercialComponent;
  sow_version_id?: string | null;
  updated_at?: string;
}
export const getCommercialDraft = (opportunityId: string) =>
  request<CommercialDraftResponse>(
    `/delivery-model/${opportunityId}/commercial/draft`,
  );
export const putCommercialDraft = (
  opportunityId: string,
  body: {
    inputs: CommercialComponent;
    sow_version_id: string | null;
    expected_updated_at: string | null;
  },
) =>
  request<{ exists: true; updated_at: string }>(
    `/delivery-model/${opportunityId}/commercial/draft`,
    { method: "PUT", body: JSON.stringify(body) },
  );
export const deleteCommercialDraft = (opportunityId: string) =>
  request<void>(`/delivery-model/${opportunityId}/commercial/draft`, {
    method: "DELETE",
  });

/** S22 · SOW/auto-staffing proposed draft for the editor (Delivery/SystemAdmin). */
export interface CommercialProposal {
  component: CommercialComponent;
  provenance: Record<string, string>;
  warnings: string[];
  suggested_profile: string;
  engagement_type: string;
  saved_version_exists: boolean;
  sow_version_id: string;
}
export const getCommercialProposal = (opportunityId: string) =>
  request<CommercialProposal>(
    `/delivery-model/${opportunityId}/commercial/proposal`,
  );

/** S22 · staffing advice: scope estimate + rate lookup + Decimal mix solver. */
export interface StaffingAdviceRole {
  role: string;
  fte: string;
  location_hint: string | null;
  evidence: string;
  skills?: string[];
  seniority?: string | null;
  phase?: string | null;
  people?: number | null;
  allocation?: string | null;
  basis?: "stated" | "inferred";
}
export interface StaffingAdvice {
  inputs: {
    revenue: string | null;
    weeks: string | null;
    target_gm: string;
    target_gm_provenance: string;
    required_fte: string | null;
    min_onshore_fte: string;
    onshore_cost_per_hour: string;
    offshore_cost_per_hour: string;
    rates_provenance: string;
  };
  estimate: {
    required_fte: string;
    duration_weeks: string | null;
    roles: StaffingAdviceRole[];
    rationale: string;
    evidence: string[];
    unknowns?: string[];
    coverage?: string | null;
    provenance: string;
  } | null;
  /** "blocked" when fee/duration are missing: the scope estimate still
   * returns; only affordability waits (redesign directive §5). */
  affordability: "calculated" | "blocked";
  blocked_reasons: string[];
  suggested: {
    onshore_fte: string;
    offshore_fte: string;
    cost: string;
    gm: string;
  } | null;
  feasible: boolean;
  max_fte_at_target: string | null;
  caution: string | null;
  warnings: string[];
  sow_version_id: string;
}
export const getStaffingAdvice = (
  opportunityId: string,
  body: {
    revenue?: string | null;
    weeks?: string | null;
    service_start?: string | null;
    service_end?: string | null;
    target_gm?: string | null;
    required_fte?: string | null;
    min_onshore_fte?: string;
  },
) =>
  request<StaffingAdvice>(
    `/delivery-model/${opportunityId}/commercial/staffing-advice`,
    { method: "POST", body: JSON.stringify(body) },
  );
