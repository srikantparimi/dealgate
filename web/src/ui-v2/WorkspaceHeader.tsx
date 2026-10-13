import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { AuthUser } from "../auth/AuthProvider";
import { cn } from "../lib/cn";
import { GlobalSearch } from "./GlobalSearch";
import { NAV_GROUPS } from "./PrimaryNavigation";
import { NotificationDrawer } from "./NotificationDrawer";
import { ProfileMenu } from "./ProfileMenu";
import { getDeal, getCurrentSowVersion, getSowVersion } from "../api/client";
import { BU_FROM_SLUG, getEngagement } from "../api/engagements";
import { workspaceTitle } from "../pages/v2/sow-workspace/readiness";

/**
 * Quiet 70px header (spec §3). Left: breadcrumb derived from the URL and
 * the primary navigation labels. Right: global search trigger,
 * notifications bell and profile menu.
 */

export interface WorkspaceHeaderProps {
  user: AuthUser | null;
  className?: string;
}

interface Crumb {
  label: string;
  to?: string;
}

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) {
    return [{ label: "Command center" }];
  }
  if (segments[0] === "engagements" && segments[1] === "new") {
    return [{ label: "Portfolio forecast", to: "/portfolio" }, { label: "New engagement" }];
  }
  // S22 P5: a business-unit tab reads as its BU, never the slug; the importer hangs off the portfolio.
  if (segments[0] === "portfolio" && segments[1] && BU_FROM_SLUG[segments[1]]) {
    return [{ label: "Portfolio forecast", to: "/portfolio" }, { label: BU_FROM_SLUG[segments[1]] }];
  }
  if (segments[0] === "import" && segments[1] === "forecast-model") {
    return [{ label: "Portfolio forecast", to: "/portfolio" }, { label: "Import the forecast model" }];
  }
  if (segments[0] === "deletions") {
    return [{ label: "SOWs", to: "/sows" }, { label: "Deletion status" }];
  }
  // Resolve the primary nav label for the first segment where possible.
  const first = `/${segments[0]}`;
  const primary = NAV_GROUPS.flatMap((g) => g.items).find(
    (i) => i.to === first || i.to.startsWith(`${first}/`),
  );
  const crumbs: Crumb[] = [];
  if (primary) {
    crumbs.push({ label: primary.label, to: primary.to });
  } else {
    crumbs.push({
      label: segments[0].replace(/-/g, " "),
      to: first,
    });
  }
  for (let i = 1; i < segments.length; i += 1) {
    const path = `/${segments.slice(0, i + 1).join("/")}`;
    crumbs.push({
      label: decodeURIComponent(segments[i]).replace(/-/g, " "),
      to: i === segments.length - 1 ? undefined : path,
    });
  }
  return crumbs;
}

export function WorkspaceHeader({ user, className }: WorkspaceHeaderProps) {
  const { pathname } = useLocation();
  const sowId = /^\/sows\/([0-9a-f-]{36})(?:\/|$)/i.exec(pathname)?.[1];
  // S22: an engagement route shows client → engagement name → tab, never the UUID (bug #1).
  const engagementMatch = /^\/engagements\/([0-9a-f-]{36})(?:\/([a-z-]+))?\/?$/i.exec(pathname);
  const engagementId = engagementMatch?.[1];
  const engagementTab = engagementMatch?.[2];
  const recordId = sowId ?? engagementId;
  const [record, setRecord] = useState<{ id: string; crumbs: Crumb[] } | null>(null);
  useEffect(() => {
    if (!engagementId) return;
    let current = true;
    void (async () => {
      const engagement = await getEngagement(engagementId);
      const tabLabel = engagementTab === "forecast" ? "Forecast" : engagementTab === "setup" ? "Setup & costs" : "Allocations";
      if (current) setRecord({ id: engagementId, crumbs: [
        { label: "Portfolio forecast", to: "/portfolio" },
        { label: engagement.client_name || "Client", to: `/clients/${engagement.client_id}` },
        { label: engagement.name, to: `/engagements/${engagementId}/allocations` },
        { label: tabLabel },
      ] });
    })().catch(() => { if (current) setRecord(null); });
    return () => { current = false; };
  }, [engagementId, engagementTab]);
  useEffect(() => {
    if (!sowId) return;
    const recordId = sowId;
    let current = true;
    void (async () => {
      const deal = await getDeal(recordId);
      const shallow = await getCurrentSowVersion(recordId);
      const sow = shallow ? await getSowVersion(shallow.id) : null;
      if (current) setRecord({ id: recordId, crumbs: [
        { label: deal.client_name ?? "Client", to: deal.client_id ? `/clients/${deal.client_id}` : undefined },
        { label: workspaceTitle({ deal, sow, gmModel: null, approvalPackage: null, agreements: [], signedSow: null }) },
      ] });
    })().catch(() => { if (current) setRecord(null); });
    return () => { current = false; };
  }, [recordId]);
  const crumbs = useMemo(
    () => (recordId ? (record?.id === recordId ? record.crumbs : [{ label: engagementId ? "Engagement" : "SOW workspace" }]) : buildCrumbs(pathname)),
    [pathname, recordId, record, engagementId],
  );

  return (
    <header
      className={cn(
        "sticky top-0 z-40 flex h-header items-center gap-4 border-b border-divider bg-surface px-6",
        className,
      )}
    >
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-1 text-body text-text-secondary">
          {crumbs.map((crumb, index) => (
            <li key={`${crumb.label}-${index}`} className="flex min-w-0 items-center gap-1">
              {index > 0 ? (
                <ChevronRight className="h-3 w-3 shrink-0 text-text-secondary" aria-hidden />
              ) : null}
              {crumb.to ? (
                <Link
                  to={crumb.to}
                  className="truncate capitalize text-text hover:text-primary transition-motion"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span
                  aria-current="page"
                  className="truncate capitalize text-text"
                >
                  {crumb.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      <div className="flex items-center gap-2">
        <GlobalSearch />
        <NotificationDrawer />
        <ProfileMenu user={user} />
      </div>
    </header>
  );
}
