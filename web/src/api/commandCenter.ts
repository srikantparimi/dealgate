import { request, type DecimalStr, type UUID } from "./client";

export type CommandPeriod = "this_quarter" | "next_two_quarters";
export type CommandFocus = "leadership" | "delivery" | "sales" | "finance";

export interface CommandScope {
  business_unit?: string;
  owner_id?: UUID;
  period: CommandPeriod;
  currency: string;
  focus: CommandFocus;
}

export interface CommandAction {
  id: UUID;
  rank: number;
  category: string;
  account: string;
  title: string;
  detail: string;
  owner: string | null;
  due: string | null;
  href: string;
  action: string;
}

export interface CommandRevenueMonth {
  month: string;
  actual: DecimalStr;
  remaining_signed: DecimalStr;
  potential_expected: DecimalStr;
  potential_upside: DecimalStr;
}

export interface CommandOverview {
  scope: {
    period: CommandPeriod;
    months: string[];
    currency: string;
    focus: CommandFocus;
  };
  actions: CommandAction[];
  metrics: {
    open_opportunity_value: DecimalStr | null;
    sows_in_progress: number;
    committed_revenue: DecimalStr | null;
    committed_gm_pct: DecimalStr | null;
    planned_people: number | null;
  };
  lifecycle: Record<string, number>;
  revenue: {
    actual: DecimalStr | null;
    remaining_signed: DecimalStr | null;
    potential_expected: DecimalStr | null;
    potential_upside: DecimalStr | null;
    currency: string;
    months: CommandRevenueMonth[];
    cost_coverage_complete: boolean;
    financial_blockers: string[];
  };
  capacity: {
    required_fte: DecimalStr | null;
    allocated_fte: DecimalStr | null;
    gap_fte: DecimalStr | null;
    status: "current" | "attention" | "unknown";
    message: string;
    gaps: Array<{
      account: string;
      title: string;
      role: string | null;
      gap_fte: DecimalStr;
      href: string;
    }>;
    source_status: "current" | "attention" | "unknown";
    source_as_of: string | null;
    source_detail: string;
  };
  recent_changes: Array<{
    id: UUID;
    account: string;
    text: string;
    at: string | null;
    href: string;
  }>;
  sources: Array<{
    name: string;
    status: "current" | "attention" | "unknown" | "empty";
    as_of: string | null;
    detail: string;
    href?: string;
  }>;
  configuration_gaps: string[];
}

export interface CommandAccountRow {
  opportunity_id: UUID;
  hubspot_deal_id: string;
  account_id: UUID | null;
  account_name: string;
  engagement_id: UUID | null;
  engagement_name: string;
  business_unit: string | null;
  pipeline_id: string;
  stage_id: string;
  stage_label: string;
  stage_order: number;
  is_closed_won: boolean;
  sow_stage: string;
  currency: string | null;
  deal_value: DecimalStr | null;
  owner_id: UUID | null;
  owner_name: string | null;
  owner_email: string | null;
  next_action: string | null;
  next_action_due: string | null;
  period_revenue: DecimalStr | null;
  forecast_gm_pct: DecimalStr | null;
  assigned_fte: DecimalStr | null;
  required_fte: DecimalStr | null;
  financial_status: "complete" | "incomplete" | "unavailable";
  financial_blockers: string[];
}

export interface CommandAccountsPage {
  items: CommandAccountRow[];
  total: number;
  page: number;
  page_size: number;
  scope_label: string;
  configuration_gaps: string[];
}

function params(values: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export function getCommandOverview(scope: CommandScope): Promise<CommandOverview> {
  return request<CommandOverview>(
    `/command-center/overview${params({ ...scope })}`,
  );
}

export function getCommandAccounts(
  scope: CommandScope,
  options: { search?: string; health?: string; page: number; page_size: number },
): Promise<CommandAccountsPage> {
  return request<CommandAccountsPage>(
    `/command-center/accounts${params({ ...scope, focus: undefined, currency: undefined, ...options })}`,
  );
}

export async function downloadCommandAccounts(
  scope: CommandScope,
  search?: string,
  health = "all",
): Promise<void> {
  const text = await request<string>(
    `/command-center/accounts.csv${params({ ...scope, focus: undefined, currency: undefined, search, health })}`,
  );
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "dealgate-command-center.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
