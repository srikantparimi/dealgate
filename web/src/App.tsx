import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuditPage } from "./pages/Audit";
import { DealDetailPage } from "./pages/DealDetail";
import { DealListPage } from "./pages/DealList";
import { UsersAdminPage } from "./pages/UsersAdmin";
import { AppShell } from "./ui/AppShell";
import { Nav, type NavItem } from "./ui/Nav";

const AUDIT_ROLES = new Set(["Finance", "Legal", "CEO", "SystemAdmin"]);

function navForRole(role: string): NavItem[] {
  const items: NavItem[] = [{ to: "/deals", label: "Deals" }];
  if (AUDIT_ROLES.has(role)) {
    items.push({ to: "/audit", label: "Audit" });
  }
  if (role === "SystemAdmin") {
    // Client-side gate for the admin section; the API still enforces
    // `require_role("SystemAdmin")` so the real gate cannot be bypassed.
    items.push({ to: "/admin/users", label: "Users" });
  }
  return items;
}

export function App() {
  // Sprint 1 hard-codes the shell user; role-gated nav still checks so the
  // real gate (server-side) doesn't drift from what the UI shows.
  const user = { name: "Sprint 1", role: "SystemAdmin" };
  return (
    <BrowserRouter>
      <AppShell user={user} nav={<Nav items={navForRole(user.role)} />}>
        <Routes>
          <Route path="/" element={<Navigate to="/deals" replace />} />
          <Route path="/deals" element={<DealListPage />} />
          <Route path="/deals/:id" element={<DealDetailPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/admin/users" element={<UsersAdminPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
