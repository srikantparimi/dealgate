import {
  Building2,
  ClipboardList,
  FileCheck2,
  FilePlus2,
  Handshake,
  LayoutDashboard,
  LineChart,
  ChartNoAxesCombined,
  RefreshCcw,
  Settings,
  ShieldCheck,
  Sparkles,
  Truck,
  Upload,
  Users,
  type LucideIcon,
  Briefcase,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "../lib/cn";

/**
 * Grouped navigation as defined in spec §3. Role gating is UX only — every
 * API endpoint still enforces its own role checks. A missing item is a hint
 * that the caller should stay off the page, not a security boundary.
 */

export interface NavGroup {
  id: string;
  label: string;
  items: NavItemDef[];
}

export interface NavItemDef {
  to: string;
  label: string;
  icon: LucideIcon;
  /** If set, at least one group must intersect the user's roles. */
  requireAny?: readonly string[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "workspace",
    label: "Workspace",
    items: [
      { to: "/command", label: "Command center", icon: LayoutDashboard },
      { to: "/work", label: "My work", icon: ClipboardList },
    ],
  },
  {
    id: "business",
    label: "Business",
    items: [
      { to: "/pipeline", label: "Pipeline", icon: Building2 },
      { to: "/sows", label: "SOWs & approvals", icon: FileCheck2 },
      { to: "/projects", label: "Projects", icon: Truck },
      { to: "/forecast", label: "Forecast", icon: ChartNoAxesCombined,
        requireAny: ["Delivery", "Finance", "CEO", "SystemAdmin", "Sales", "SalesLeader"] },
      { to: "/portfolio", label: "Portfolio", icon: Briefcase,
        requireAny: ["Delivery", "Finance", "CEO", "SystemAdmin", "HR", "Sales", "SalesLeader", "Presales"] },
      { to: "/people", label: "People", icon: Users,
        requireAny: ["HR", "SystemAdmin"] },
    ],
  },
  {
    id: "supporting",
    label: "Supporting work",
    items: [
      { to: "/renewals", label: "Renewals", icon: RefreshCcw },
      { to: "/agreements", label: "NDA & MSA", icon: ShieldCheck },
      { to: "/discovery", label: "AI discovery", icon: Sparkles },
      { to: "/reports", label: "Reports", icon: LineChart },
      { to: "/handoffs", label: "Signed handoff", icon: Handshake },
      { to: "/sows/new", label: "New SOW studio", icon: FilePlus2 },
    ],
  },
  {
    id: "administration",
    label: "Administration",
    items: [
      // S22 P5: the FY forecast model master -> dry run -> load. Writers only.
      { to: "/import/forecast-model", label: "Import the forecast model", icon: Upload,
        requireAny: ["Delivery", "Finance", "SystemAdmin", "Sales", "SalesLeader"] },
      {
        to: "/settings",
        label: "Settings",
        icon: Settings,
        requireAny: ["SystemAdmin", "Finance", "Legal", "CEO"],
      },
    ],
  },
];

export function filterItems(
  items: NavItemDef[],
  groups: readonly string[],
): NavItemDef[] {
  return items.filter((item) => {
    if (!item.requireAny) return true;
    return item.requireAny.some((role) => groups.includes(role));
  });
}

export interface PrimaryNavigationProps {
  groups: readonly string[];
  workspaceName?: string;
  className?: string;
}

export function PrimaryNavigation({
  groups,
  workspaceName = "SmarTek21",
  className,
}: PrimaryNavigationProps) {
  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex h-full w-sidebar flex-col gap-2 border-r border-divider bg-navigation py-4",
        className,
      )}
    >
      <div className="px-4 pb-2">
        <p className="text-secondary text-text-secondary uppercase tracking-wide">
          {workspaceName}
        </p>
        <p className="text-section text-text">DealGate</p>
      </div>

      <ul className="flex flex-1 flex-col gap-4 overflow-y-auto px-2 pb-4">
        {NAV_GROUPS.map((group) => {
          const visible = filterItems(group.items, groups);
          if (visible.length === 0) return null;
          return (
            <li key={group.id}>
              <p className="px-2 pb-1 text-secondary text-text-secondary uppercase tracking-wide">
                {group.label}
              </p>
              <ul className="flex flex-col gap-[2px]">
                {visible.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      className={({ isActive }) =>
                        cn(
                          "group flex min-h-9 items-center gap-2 rounded-control px-2 py-1.5 text-body",
                          "text-text-secondary transition-motion",
                          "hover:bg-primary-subtle hover:text-text",
                          "focus-visible:outline-focus",
                          isActive && "bg-primary-subtle text-primary font-medium",
                        )
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" aria-hidden />
                      <span className="truncate">{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}

      </ul>
    </nav>
  );
}
