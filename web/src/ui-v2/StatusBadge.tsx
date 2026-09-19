import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Info,
  ShieldAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Badge, type BadgeProps } from "./primitives/badge";
import { cn } from "../lib/cn";

/**
 * Named status badge. Colour is supplementary — every status also has a
 * word and an icon (spec §2 and §20). Callers pass a semantic `tone` plus
 * the human-readable label; the icon is chosen by tone by default but can
 * be overridden.
 */
export type StatusTone =
  | "neutral"
  | "ok"
  | "warn"
  | "danger"
  | "primarySubtle";

const iconByTone: Record<StatusTone, LucideIcon> = {
  neutral: CircleDashed,
  ok: CheckCircle2,
  warn: AlertTriangle,
  danger: XCircle,
  primarySubtle: Info,
};

const fallbackIcons: Record<string, LucideIcon> = {
  security: ShieldAlert,
};

export interface StatusBadgeProps
  extends Omit<BadgeProps, "tone" | "children"> {
  tone: StatusTone;
  label: ReactNode;
  icon?: LucideIcon;
  /** Set to `false` to hide the icon (label still required). */
  showIcon?: boolean;
}

export function StatusBadge({
  tone,
  label,
  icon,
  showIcon = true,
  className,
  ...rest
}: StatusBadgeProps) {
  const Icon = icon ?? iconByTone[tone] ?? fallbackIcons.security;
  return (
    <Badge tone={tone} className={cn("gap-1", className)} {...rest}>
      {showIcon ? <Icon className="h-3 w-3" aria-hidden /> : null}
      <span>{label}</span>
    </Badge>
  );
}
