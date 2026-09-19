import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, type BadgeProps } from "./primitives/badge";
import { cn } from "../lib/cn";

/**
 * Named status badge — v2.1 spec.
 *
 * Five variants are the source of truth:
 *   `neutral | success | warning | danger | progress`
 *
 * The v2.0 tone names (`ok`, `warn`, `primarySubtle`) are still accepted
 * so existing call sites keep working; they map onto the new variants at
 * render time. The `security` alias remains for the settings page.
 *
 * Rendering is dot + word (v2.1 addendum rule: colour alone never encodes
 * state — the dot survives grayscale and colour-blindness; the word is
 * always there). An optional icon is still supported for callers that
 * previously relied on it; when an icon is shown the leading dot is
 * hidden so the chip stays 22px tall.
 */
export type StatusTone =
  // v2.1 canonical names
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "progress"
  // Legacy aliases kept for backwards compatibility.
  | "ok"
  | "warn"
  | "primarySubtle";

const ALIAS: Record<StatusTone, "neutral" | "success" | "warning" | "danger" | "progress"> = {
  neutral: "neutral",
  success: "success",
  warning: "warning",
  danger: "danger",
  progress: "progress",
  ok: "success",
  warn: "warning",
  primarySubtle: "progress",
};

export interface StatusBadgeProps
  extends Omit<BadgeProps, "tone" | "children" | "showDot"> {
  tone: StatusTone;
  label: ReactNode;
  /**
   * Optional lucide icon shown before the label. When present, the leading
   * coloured dot is suppressed so the chip stays 22px tall.
   */
  icon?: LucideIcon;
  /** Set to `false` to hide any icon (label still required). */
  showIcon?: boolean;
}

export function StatusBadge({
  tone,
  label,
  icon: Icon,
  showIcon = true,
  className,
  ...rest
}: StatusBadgeProps) {
  const canonical = ALIAS[tone];
  const hasIcon = Boolean(Icon) && showIcon;
  return (
    <Badge
      tone={canonical}
      showDot={!hasIcon}
      className={cn(className)}
      {...rest}
    >
      {hasIcon && Icon ? <Icon className="h-3 w-3" aria-hidden /> : null}
      <span>{label}</span>
    </Badge>
  );
}
