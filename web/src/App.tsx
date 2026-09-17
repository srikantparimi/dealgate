import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { AuditPage } from "./pages/Audit";
import { AuthCallback } from "./pages/AuthCallback";
import { DealDetailPage } from "./pages/DealDetail";
import { DealListPage } from "./pages/DealList";
import { UsersAdminPage } from "./pages/UsersAdmin";
import { AppShell } from "./ui/AppShell";
import { Nav, type NavItem } from "./ui/Nav";

const AUDIT_ROLES = new Set(["Finance", "Legal", "CEO", "SystemAdmin"]);

function navForGroups(groups: string[]): NavItem[] {
  const items: NavItem[] = [{ to: "/deals", label: "Deals" }];
  if (groups.some((g) => AUDIT_ROLES.has(g))) {
    items.push({ to: "/audit", label: "Audit" });
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
                  <Route path="/audit" element={<AuditPage />} />
                  <Route path="/admin/users" element={<UsersAdminPage />} />
                </Routes>
              </AuthedShell>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
