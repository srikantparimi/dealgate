import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

/**
 * Status chip — v2.1 spec.
 *
 * A 22px pill with a 4px radius, 6px coloured dot before the word.
 * Colour alone never encodes state, so `StatusBadge` upstream always
 * pairs the chip with a written label.
 *
 * Five variants:
 *   - neutral  — informational / unknown state
 *   - success  — pass / ok / done
 *   - warning  — at-risk / caution
 *   - danger   — blocked / failed
 *   - progress — in-progress / active (uses the single violet accent)
 *
 * Legacy tone names (`ok`, `warn`, `primarySubtle`, `executive`) are kept
 * as aliases so v2.0 pages don't break — see the alias map below.
 */
export const badgeVariants = cva(
  cn(
    "inline-flex items-center gap-[6px] rounded-chip",
    "h-[22px] px-[8px]",
    "text-[12px] leading-[1] font-medium",
    "border",
  ),
  {
    variants: {
      tone: {
        neutral: "bg-surface-sunken text-text border-border",
        success:
          "bg-success-surface text-success border-success/20",
        warning:
          "bg-warning-surface text-warning border-warning/20",
        danger:
          "bg-danger-surface text-danger border-danger/20",
        progress:
          "bg-primary-subtle text-primaryText border-primary/20",
        // Legacy aliases — same rendering as the v2.1 name.
        ok: "bg-success-surface text-success border-success/20",
        warn: "bg-warning-surface text-warning border-warning/20",
        primarySubtle:
          "bg-primary-subtle text-primaryText border-primary/20",
        executive:
          "bg-plum text-onPlum border-plumLine",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

/** Small coloured dot that precedes the label. */
const dotClassByTone: Record<string, string> = {
  neutral: "bg-text-secondary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  progress: "bg-primary",
  // Legacy aliases keep their historical mapping.
  ok: "bg-success",
  warn: "bg-warning",
  primarySubtle: "bg-primary",
  executive: "bg-lime",
};

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  /**
   * Set to `false` to hide the leading coloured dot. `StatusBadge` renders
   * its own icon; the dot is redundant when an icon is already present, so
   * `StatusBadge` opts out with this flag.
   */
  showDot?: boolean;
}

export function Badge({
  className,
  tone,
  showDot = true,
  children,
  ...props
}: BadgeProps) {
  const toneKey = (tone ?? "neutral") as string;
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
      {showDot ? (
        <span
          aria-hidden
          className={cn(
            "inline-block h-[6px] w-[6px] rounded-avatar shrink-0",
            dotClassByTone[toneKey] ?? "bg-text-secondary",
          )}
        />
      ) : null}
      {children}
    </span>
  );
}
