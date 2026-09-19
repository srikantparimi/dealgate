import { Menu } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useAuth } from "../auth/AuthProvider";
import { cn } from "../lib/cn";
import { PreferencesProvider } from "./preferences";
import { PrimaryNavigation } from "./PrimaryNavigation";
import { Button } from "./primitives/button";
import { Sheet, SheetContent, SheetTrigger } from "./primitives/sheet";
import { TooltipProvider } from "./primitives/tooltip";
import { Toaster } from "./primitives/toaster";
import { WorkspaceHeader } from "./WorkspaceHeader";

/**
 * DealGate V2 application shell.
 *
 * Composition:
 *   - Left: 194px `PrimaryNavigation` (spec §3, promoted to 224px on
 *     large displays).
 *   - Right: 70px `WorkspaceHeader` + main content region with 24–28px
 *     padding.
 *   - Below 1024px the sidebar collapses into a right-drawer opened by
 *     the burger menu in the header.
 *
 * Auth wiring is untouched — the shell reads `useAuth()` and hides
 * nav items the user's role list does not intersect (server enforces).
 *
 * Toast + Tooltip + Preferences providers live here so every page can
 * emit toasts and use tooltips without extra wiring.
 */

export interface AppShellProps {
  children: ReactNode;
  /** Optional workspace label; defaults to "SmarTek21". */
  workspaceName?: string;
}

export function AppShell({ children, workspaceName }: AppShellProps) {
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <PreferencesProvider>
      <TooltipProvider delayDuration={200}>
        <Toaster>
          <div
            className={cn(
              "flex min-h-screen bg-canvas text-text",
              "font-sans text-body antialiased",
            )}
          >
            {/* Desktop sidebar */}
            <aside
              aria-label="Primary navigation"
              className="hidden lg:flex shrink-0"
            >
              <PrimaryNavigation
                groups={groups}
                workspaceName={workspaceName}
              />
            </aside>

            {/* Main column */}
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-center gap-2 border-b border-divider bg-surface px-4 lg:hidden">
                <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
                  <SheetTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Open navigation"
                    >
                      <Menu className="h-5 w-5" aria-hidden />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-64 p-0">
                    <div onClick={() => setDrawerOpen(false)}>
                      <PrimaryNavigation
                        groups={groups}
                        workspaceName={workspaceName}
                      />
                    </div>
                  </SheetContent>
                </Sheet>
              </div>

              <WorkspaceHeader user={user} />

              <main
                className={cn(
                  "flex-1 px-6 py-6 sm:px-6 lg:px-6",
                  "max-w-full",
                )}
                style={{ paddingInline: "var(--page-x, 24px)" }}
              >
                {children}
              </main>
            </div>
          </div>
        </Toaster>
      </TooltipProvider>
    </PreferencesProvider>
  );
}
