import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

/**
 * Compact rectangular status badge (spec §2). Colour is supplementary —
 * `StatusBadge` upstream always sets the accompanying text label.
 */
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[6px] px-2 py-[2px] text-secondary font-medium",
  {
    variants: {
      tone: {
        neutral: "bg-divider text-text",
        primarySubtle: "bg-primary-subtle text-primary",
        ok: "bg-success-surface text-success",
        warn: "bg-warning-surface text-warning",
        danger: "bg-danger-surface text-danger",
        executive: "bg-executive text-executive-fg",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
