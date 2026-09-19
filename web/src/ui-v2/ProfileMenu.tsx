import {
  ChevronDown,
  HelpCircle,
  LogOut,
  Monitor,
  MoonStar,
  Rows2,
  Rows3,
  Sun,
  User as UserIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth, type AuthUser } from "../auth/AuthProvider";
import { cn } from "../lib/cn";
import { Button } from "./primitives/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./primitives/dropdown-menu";
import { usePreferences, type Appearance, type Density } from "./preferences";

/**
 * Profile menu (spec §4).
 *
 * - Name, role, workspace at the top.
 * - Links to My profile and Notification preferences.
 * - Appearance and Density preferences (persisted to `localStorage`).
 * - Help + Sign out.
 *
 * A role here is a *display* — administrator access does not grant CEO
 * authority. Every gate that matters lives on the server.
 */

export interface ProfileMenuProps {
  user: AuthUser | null;
  className?: string;
  workspaceName?: string;
}

export function ProfileMenu({
  user,
  workspaceName = "SmarTek21",
  className,
}: ProfileMenuProps) {
  const { logout } = useAuth();
  const { appearance, density, setAppearance, setDensity } = usePreferences();

  const initials = (user?.name ?? "User")
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn("gap-2 text-text", className)}
          aria-label="Open profile menu"
        >
          <span
            aria-hidden
            className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-primary-subtle text-primary text-secondary font-semibold"
          >
            {initials || "?"}
          </span>
          <span className="hidden max-w-[8rem] truncate sm:inline">
            {user?.name ?? "Local dev"}
          </span>
          <ChevronDown className="h-3 w-3" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>Signed in</DropdownMenuLabel>
        <div className="px-3 pb-2">
          <p className="text-body text-text">{user?.name ?? "Local dev"}</p>
          <p className="text-secondary text-text-secondary">
            {user?.role ?? "User"} · {workspaceName}
          </p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings" className="flex items-center gap-2">
            <UserIcon className="h-4 w-4" aria-hidden />
            My profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/settings/notifications" className="flex items-center gap-2">
            <UserIcon className="h-4 w-4" aria-hidden />
            Notification preferences
          </Link>
        </DropdownMenuItem>

        <DropdownMenuSeparator />
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={appearance}
          onValueChange={(value) => setAppearance(value as Appearance)}
        >
          <DropdownMenuRadioItem value="system">
            <Monitor className="mr-2 h-4 w-4" aria-hidden /> System
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">
            <Sun className="mr-2 h-4 w-4" aria-hidden /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <MoonStar className="mr-2 h-4 w-4" aria-hidden /> Dark
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />
        <DropdownMenuLabel>Density</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={density}
          onValueChange={(value) => setDensity(value as Density)}
        >
          <DropdownMenuRadioItem value="comfortable">
            <Rows2 className="mr-2 h-4 w-4" aria-hidden /> Comfortable
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="compact">
            <Rows3 className="mr-2 h-4 w-4" aria-hidden /> Compact
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a
            href="https://ui.shadcn.com/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2"
          >
            <HelpCircle className="h-4 w-4" aria-hidden /> Help
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            logout();
          }}
        >
          <LogOut className="mr-2 h-4 w-4" aria-hidden />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
