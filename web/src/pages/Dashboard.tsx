/**
 * Dashboard hub — picks the right role dashboard for the caller. Users
 * with multiple roles (e.g. Finance + CEO) get a small selector at the
 * top; the default is the highest-authority role they hold. The API
 * enforces the real gate — this switch is UX only.
 */

import { useMemo, useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../ui/PageHeader";
import { EmptyState } from "../ui/EmptyState";
import { CEODashboard } from "./dashboards/CEODashboard";
import { DeliveryDashboardPage } from "./dashboards/DeliveryDashboard";
import { FinanceDashboardPage } from "./dashboards/FinanceDashboard";
import { HRDashboardPage } from "./dashboards/HRDashboard";
import { LegalDashboardPage } from "./dashboards/LegalDashboard";
import { SalesDashboardPage } from "./dashboards/SalesDashboard";

// Ordered high → low. First hit wins as the default; a user with Finance +
// CEO gets the CEO dashboard by default and can flip via the selector.
const ROLE_TO_VIEW = [
  { role: "SystemAdmin", view: "ceo", label: "CEO" },
  { role: "CEO", view: "ceo", label: "CEO" },
  { role: "Finance", view: "finance", label: "Finance" },
  { role: "Legal", view: "legal", label: "Legal" },
  { role: "HR", view: "hr", label: "HR" },
  { role: "Delivery", view: "delivery", label: "Delivery" },
  { role: "SalesLeader", view: "sales", label: "Sales" },
  { role: "Sales", view: "sales", label: "Sales" },
  { role: "Marketing", view: "sales", label: "Sales" },
] as const;

type ViewKey =
  | "ceo"
  | "finance"
  | "delivery"
  | "sales"
  | "hr"
  | "legal";

function availableViews(groups: readonly string[]): {
  view: ViewKey;
  label: string;
}[] {
  const seen = new Set<ViewKey>();
  const out: { view: ViewKey; label: string }[] = [];
  for (const { role, view, label } of ROLE_TO_VIEW) {
    if (!groups.includes(role)) continue;
    if (seen.has(view)) continue;
    seen.add(view);
    out.push({ view, label });
  }
  return out;
}

export function DashboardPage() {
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  const views = useMemo(() => availableViews(groups), [groups]);
  const [selected, setSelected] = useState<ViewKey | null>(
    views[0]?.view ?? null,
  );

  if (views.length === 0) {
    return (
      <div>
        <PageHeader
          title="Dashboard"
          subtitle="No role dashboard available for your account."
        />
        <EmptyState
          title="Nothing to show"
          hint="Ask an administrator to add you to a governance group."
        />
      </div>
    );
  }

  const current = selected ?? views[0].view;

  return (
    <div>
      {views.length > 1 ? (
        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              display: "inline-flex",
              gap: 8,
              alignItems: "center",
              fontSize: 14,
              color: "#374151",
            }}
          >
            <span>Role view:</span>
            <select
              aria-label="Role view"
              value={current}
              onChange={(e) => setSelected(e.target.value as ViewKey)}
              style={{
                padding: "4px 8px",
                border: "1px solid #e5e7eb",
                borderRadius: 4,
              }}
            >
              {views.map((v) => (
                <option key={v.view} value={v.view}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}

      {current === "ceo" ? <CEODashboard /> : null}
      {current === "finance" ? <FinanceDashboardPage /> : null}
      {current === "delivery" ? <DeliveryDashboardPage /> : null}
      {current === "sales" ? <SalesDashboardPage /> : null}
      {current === "hr" ? <HRDashboardPage /> : null}
      {current === "legal" ? <LegalDashboardPage /> : null}
    </div>
  );
}
