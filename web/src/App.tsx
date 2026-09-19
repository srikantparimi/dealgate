import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { ActualsImportPage } from "./pages/ActualsImport";
import { AdminReplayPage } from "./pages/AdminReplay";
import { AdviserIntakePage } from "./pages/AdviserIntake";
import { AdviserDetailPage, AdviserListPage } from "./pages/AdviserList";
import { ApprovalPackageDetailPage } from "./pages/ApprovalPackageDetail";
import { ApprovalQueuePage } from "./pages/ApprovalQueue";
import { AuditPage } from "./pages/Audit";
import { AuthCallback } from "./pages/AuthCallback";
import { CapabilityCatalogPage } from "./pages/CapabilityCatalog";
import { CEOExceptionBriefPage } from "./pages/CEOExceptionBrief";
import { ClientDetailPage } from "./pages/ClientDetail";
import { ClientListPage } from "./pages/ClientList";
import { ClientSowGmPage } from "./pages/ClientSowGm";
import { DashboardPage } from "./pages/Dashboard";
import { DealDetailPage } from "./pages/DealDetail";
import { DealListPage } from "./pages/DealList";
import { DeliveryModelTemplatesPage } from "./pages/DeliveryModelTemplates";
import { GMSandboxPage } from "./pages/GMSandbox";
import { LegacyImportPage } from "./pages/LegacyImport";
import { LegacyReconciliationPage } from "./pages/LegacyReconciliation";
import { MyTasksPage } from "./pages/MyTasks";
import { NotificationSettingsPage } from "./pages/NotificationSettings";
import { PolicyAdminPage } from "./pages/PolicyAdmin";
import { RateCardsPage } from "./pages/RateCards";
import { RenewalBoardPage } from "./pages/RenewalBoard";
import { UsersAdminPage } from "./pages/UsersAdmin";
import { AppShell } from "./ui/AppShell";
import { Nav, type NavItem } from "./ui/Nav";

const AUDIT_ROLES = new Set(["Finance", "Legal", "CEO", "SystemAdmin"]);
// Legacy import (S6) — Finance/CEO/SystemAdmin. The API enforces the same
// gate; the nav link is a UX hint, not a security boundary.
const LEGACY_IMPORT_ROLES = new Set(["Finance", "CEO", "SystemAdmin"]);
// Actuals CSV import (S6 E9) — Finance/SystemAdmin. Same UX-hint pattern.
const ACTUALS_ROLES = new Set(["Finance", "SystemAdmin"]);
// Roles that can drive the Opportunity Adviser intake. Reads are broader
// (any governance role); the nav link only exposes the intake path.
const ADVISER_ROLES = new Set(["Marketing", "Sales", "Presales", "SystemAdmin"]);
const GM_SANDBOX_ROLES = new Set([
  "Finance",
  "Delivery",
  "Presales",
  "SystemAdmin",
]);
// Finance-owned admin surfaces. The API also enforces role gates so hiding
// the nav link is UX only.
const RATE_CARD_ADMIN_ROLES = new Set(["Finance", "SystemAdmin"]);
// CEO exception inbox — CEO or SystemAdmin see the link. Delegates get
// the same link when logged in as themselves; the API's inbox endpoint
// resolves the active delegate at request time so the nav-side gate is
// only a UX hint (never a security boundary).
const CEO_EXCEPTION_ROLES = new Set(["CEO", "SystemAdmin"]);
// S4 E7: any governance function may read the approvals inbox. The API
// enforces per-decision role gates so this nav link is only a UX hint.
const APPROVAL_ROLES = new Set([
  "Delivery",
  "HR",
  "Finance",
  "Legal",
  "CEO",
  "SalesLeader",
  "SystemAdmin",
]);
// S5 E9: renewals inbox surfaces to Sales, CEO, Finance and SystemAdmin per
// the story. The API still enforces the per-row edit gate (account owner).
const RENEWAL_NAV_ROLES = new Set([
  "Sales",
  "SalesLeader",
  "CEO",
  "Finance",
  "SystemAdmin",
]);
// S7 wave 2: Delivery Lead / SystemAdmin curate the capability catalog.
// The API also lets Presales/Marketing/Sales read; the nav link surfaces
// the curator entry point only.
const CAPABILITY_NAV_ROLES = new Set(["Delivery", "SystemAdmin"]);
const CAPABILITY_WRITE_ROLES = new Set(["Delivery", "SystemAdmin"]);
const CAPABILITY_DELETE_ROLES = new Set(["SystemAdmin"]);

function canSeeGmSandbox(groups: string[]): boolean {
  return groups.some((g) => GM_SANDBOX_ROLES.has(g));
}

function navForGroups(groups: string[]): NavItem[] {
  const items: NavItem[] = [
    // S5 E10: every authenticated user gets a Dashboard link that routes to
    // their role's page. The Dashboard page also handles multi-role users
    // with an in-page selector; API enforces the real gate.
    { to: "/dashboard", label: "Dashboard" },
    { to: "/deals", label: "Deals" },
    { to: "/clients", label: "Clients" },
    // Available to every authenticated user; the API also enforces per-row
    // access so a stale link can never expose someone else's inbox.
    { to: "/tasks", label: "My tasks" },
  ];
  if (groups.some((g) => ADVISER_ROLES.has(g))) {
    // Client-side gate for the intake; the API still enforces the write
    // roles (Marketing/Sales/Presales/SystemAdmin) so the real gate cannot
    // be bypassed from the browser.
    items.push({ to: "/adviser/new", label: "Adviser" });
  }
  if (canSeeGmSandbox(groups)) {
    // Client-side gate; the API also enforces `require_role(...)` so this
    // link's absence is a UX hint, not a security boundary.
    items.push({ to: "/gm/sandbox", label: "GM sandbox" });
  }
  if (groups.some((g) => AUDIT_ROLES.has(g))) {
    items.push({ to: "/audit", label: "Audit" });
  }
  if (groups.some((g) => RATE_CARD_ADMIN_ROLES.has(g))) {
    items.push({ to: "/admin/rate-cards", label: "Rate cards" });
    items.push({ to: "/admin/policy", label: "Policy" });
  }
  if (groups.some((g) => LEGACY_IMPORT_ROLES.has(g))) {
    items.push({ to: "/legacy/import", label: "Legacy import" });
  }
  if (groups.some((g) => ACTUALS_ROLES.has(g))) {
    items.push({ to: "/actuals/import", label: "Actuals" });
  }
  if (groups.some((g) => CEO_EXCEPTION_ROLES.has(g))) {
    // The API still enforces role + delegate — this link is a UX hint,
    // not a security boundary.
    items.push({ to: "/ceo-exceptions", label: "CEO exceptions" });
  }
  if (groups.some((g) => APPROVAL_ROLES.has(g))) {
    items.push({ to: "/approvals", label: "Approvals" });
  }
  if (groups.some((g) => RENEWAL_NAV_ROLES.has(g))) {
    items.push({ to: "/renewals", label: "Renewals" });
  }
  if (groups.some((g) => CAPABILITY_NAV_ROLES.has(g))) {
    items.push({ to: "/admin/capabilities", label: "Capabilities" });
  }
  if (groups.includes("SystemAdmin")) {
    // Client-side gate for the admin section; the API still enforces
    // `require_role("SystemAdmin")` so the real gate cannot be bypassed.
    items.push({ to: "/admin/users", label: "Users" });
    // S6 DLQ + replay admin surface. API also enforces SystemAdmin.
    items.push({ to: "/admin/replay", label: "Replay" });
  }
  return items;
}

function AuthedShell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  return (
    <AppShell user={user} nav={<Nav items={navForGroups(groups)} />}>
      {children}
    </AppShell>
  );
}

function CapabilityCatalogRoute() {
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  const canWrite = groups.some((g) => CAPABILITY_WRITE_ROLES.has(g));
  const canDelete = groups.some((g) => CAPABILITY_DELETE_ROLES.has(g));
  return <CapabilityCatalogPage canWrite={canWrite} canDelete={canDelete} />;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AuthedShell>
                <Routes>
                  <Route path="/" element={<Navigate to="/deals" replace />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/deals" element={<DealListPage />} />
                  <Route path="/deals/:id" element={<DealDetailPage />} />
                  <Route path="/clients" element={<ClientListPage />} />
                  <Route path="/clients/:id" element={<ClientDetailPage />} />
                  <Route
                    path="/clients/:id/sows"
                    element={<ClientSowGmPage />}
                  />
                  <Route path="/tasks" element={<MyTasksPage />} />
                  <Route
                    path="/settings/notifications"
                    element={<NotificationSettingsPage />}
                  />
                  <Route path="/gm/sandbox" element={<GMSandboxPage />} />
                  <Route path="/audit" element={<AuditPage />} />
                  <Route path="/adviser" element={<AdviserListPage />} />
                  <Route path="/adviser/new" element={<AdviserIntakePage />} />
                  <Route path="/adviser/:id" element={<AdviserDetailPage />} />
                  <Route path="/admin/rate-cards" element={<RateCardsPage />} />
                  <Route path="/admin/policy" element={<PolicyAdminPage />} />
                  <Route path="/admin/users" element={<UsersAdminPage />} />
                  <Route path="/admin/replay" element={<AdminReplayPage />} />
                  <Route path="/legacy/import" element={<LegacyImportPage />} />
                  <Route path="/actuals/import" element={<ActualsImportPage />} />
                  <Route
                    path="/ceo-exceptions/:id"
                    element={<CEOExceptionBriefPage />}
                  />
                  <Route
                    path="/legacy/reconciliation/:batchId"
                    element={<LegacyReconciliationPage />}
                  />
                  <Route path="/approvals" element={<ApprovalQueuePage />} />
                  <Route
                    path="/approvals/:id"
                    element={<ApprovalPackageDetailPage />}
                  />
                  <Route path="/renewals" element={<RenewalBoardPage />} />
                  <Route
                    path="/delivery-model/templates"
                    element={<DeliveryModelTemplatesPage />}
                  />
                  <Route
                    path="/admin/capabilities"
                    element={<CapabilityCatalogRoute />}
                  />
                </Routes>
              </AuthedShell>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
