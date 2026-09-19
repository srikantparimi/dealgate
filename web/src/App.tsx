import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/RequireAuth";
import { useAuth } from "./auth/AuthProvider";
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
import { AppShell } from "./ui-v2/AppShell";
import { CommandCenterPage } from "./pages/v2/CommandCenter";
import { SowApprovalsPage } from "./pages/v2/SowApprovals";
import { SowStudioPage } from "./pages/v2/SowStudio";
import { SowWorkspacePage } from "./pages/v2/SowWorkspace";
import { CEOExceptionDecisionPage } from "./pages/v2/CEOExceptionDecision";
import { PipelinePage } from "./pages/v2/Pipeline";
import { AgreementsRegisterPage } from "./pages/v2/AgreementsRegister";
import { SignedHandoffPage } from "./pages/v2/SignedHandoff";
import { RenewalsV2Page } from "./pages/v2/RenewalsV2";
import { MyWorkPage } from "./pages/v2/MyWork";
import { DiscoveryPage } from "./pages/v2/Discovery";
import { MarginLabPage } from "./pages/v2/MarginLab";
import { ProjectsActualsPage } from "./pages/v2/ProjectsActuals";
import { ReportsPage } from "./pages/v2/Reports";
import { SettingsShellPage } from "./pages/v2/SettingsShell";

const CAPABILITY_WRITE_ROLES = new Set(["Delivery", "SystemAdmin"]);
const CAPABILITY_DELETE_ROLES = new Set(["SystemAdmin"]);

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
              <AppShell>
                <Routes>
                  <Route
                    path="/"
                    element={<Navigate to="/command" replace />}
                  />

                  {/* Existing (legacy) pages — kept live for Wave 1. Wave 2
                   * will migrate them behind the new routes below. */}
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
                  <Route
                    path="/actuals/import"
                    element={<ActualsImportPage />}
                  />
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

                  {/* V2 route stubs (spec §3) — Wave 2 will replace these
                   * redirects with the real pages. The paths are already
                   * live so the primary nav and command palette work today. */}
                  <Route path="/command" element={<CommandCenterPage />} />
                  <Route path="/pipeline" element={<PipelinePage />} />
                  <Route path="/agreements" element={<AgreementsRegisterPage />} />
                  <Route path="/sows" element={<SowApprovalsPage />} />
                  <Route path="/sows/new" element={<SowStudioPage />} />
                  <Route path="/sows/:id" element={<SowWorkspacePage />} />
                  <Route path="/sows/:id/:tab" element={<SowWorkspacePage />} />
                  <Route
                    path="/sows/:id/exception"
                    element={<CEOExceptionDecisionPage />}
                  />
                  <Route path="/handoffs" element={<SignedHandoffPage />} />
                  <Route path="/handoffs/:id" element={<SignedHandoffPage />} />
                  <Route path="/renewals-v2" element={<RenewalsV2Page />} />
                  <Route path="/work" element={<MyWorkPage />} />
                  <Route path="/discovery" element={<DiscoveryPage />} />
                  <Route path="/margin-lab" element={<MarginLabPage />} />
                  <Route path="/projects" element={<ProjectsActualsPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/settings" element={<SettingsShellPage />} />
                  <Route path="/settings/:section" element={<SettingsShellPage />} />
                </Routes>
              </AppShell>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
