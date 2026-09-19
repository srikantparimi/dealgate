import { ChevronRight } from "lucide-react";
import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import type { AuthUser } from "../auth/AuthProvider";
import { cn } from "../lib/cn";
import { GlobalSearch } from "./GlobalSearch";
import { NAV_GROUPS } from "./PrimaryNavigation";
import { NotificationDrawer } from "./NotificationDrawer";
import { ProfileMenu } from "./ProfileMenu";

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
  const crumbs = useMemo(() => buildCrumbs(pathname), [pathname]);

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
