import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { AdviserIntakePage } from "./pages/AdviserIntake";
import { AdviserDetailPage, AdviserListPage } from "./pages/AdviserList";
import { AuditPage } from "./pages/Audit";
import { AuthCallback } from "./pages/AuthCallback";
import { ClientDetailPage } from "./pages/ClientDetail";
import { ClientListPage } from "./pages/ClientList";
import { DealDetailPage } from "./pages/DealDetail";
import { DealListPage } from "./pages/DealList";
import { GMSandboxPage } from "./pages/GMSandbox";
import { LegacyImportPage } from "./pages/LegacyImport";
import { LegacyReconciliationPage } from "./pages/LegacyReconciliation";
import { MyTasksPage } from "./pages/MyTasks";
import { NotificationSettingsPage } from "./pages/NotificationSettings";
import { PolicyAdminPage } from "./pages/PolicyAdmin";
import { RateCardsPage } from "./pages/RateCards";
import { UsersAdminPage } from "./pages/UsersAdmin";
import { AppShell } from "./ui/AppShell";
import { Nav, type NavItem } from "./ui/Nav";

const AUDIT_ROLES = new Set(["Finance", "Legal", "CEO", "SystemAdmin"]);
// Legacy import (S6) — Finance/CEO/SystemAdmin. The API enforces the same
// gate; the nav link is a UX hint, not a security boundary.
const LEGACY_IMPORT_ROLES = new Set(["Finance", "CEO", "SystemAdmin"]);
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

function canSeeGmSandbox(groups: string[]): boolean {
  return groups.some((g) => GM_SANDBOX_ROLES.has(g));
}

function navForGroups(groups: string[]): NavItem[] {
  const items: NavItem[] = [
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
  if (groups.includes("SystemAdmin")) {
    // Client-side gate for the admin section; the API still enforces
    // `require_role("SystemAdmin")` so the real gate cannot be bypassed.
    items.push({ to: "/admin/users", label: "Users" });
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
                  <Route path="/deals" element={<DealListPage />} />
                  <Route path="/deals/:id" element={<DealDetailPage />} />
                  <Route path="/clients" element={<ClientListPage />} />
                  <Route path="/clients/:id" element={<ClientDetailPage />} />
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
                  <Route path="/legacy/import" element={<LegacyImportPage />} />
                  <Route
                    path="/legacy/reconciliation/:batchId"
                    element={<LegacyReconciliationPage />}
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
