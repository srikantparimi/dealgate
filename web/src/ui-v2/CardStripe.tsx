/**
 * CardStripe — v2.1 spec `elevation.stripe`.
 *
 * A 3 px left stripe marks a card as blocked / at-risk / in-progress.
 * Nothing else gets a stripe. This helper returns the Tailwind classes
 * that a card component can spread onto its root element.
 *
 * Usage:
 *   <div className={cn("card", cardStripeClass('blocked'))}>…</div>
 */
import { cn } from "../lib/cn";

export type CardStripeVariant =
  | "blocked"
  | "at-risk"
  | "in-progress"
  | null
  | undefined;

const VARIANT_CLASS: Record<Exclude<CardStripeVariant, null | undefined>, string> = {
  blocked: "border-l-[3px] border-l-danger",
  "at-risk": "border-l-[3px] border-l-warning",
  "in-progress": "border-l-[3px] border-l-primary",
};

/** Return the tailwind classes for the 3px left stripe. */
export function cardStripeClass(variant: CardStripeVariant): string {
  if (!variant) return "";
  return VARIANT_CLASS[variant];
}

export interface CardStripeProps {
  variant: CardStripeVariant;
  className?: string;
}

/**
 * Convenience component wrapper — returns a `<div>` that applies the
 * stripe. Prefer the class helper `cardStripeClass()` inside existing
 * cards; use this component when you want the JSX to name the intent.
 */
export function CardStripe({
  variant,
  className,
  children,
}: CardStripeProps & { children?: React.ReactNode }) {
  return (
    <div
      className={cn(cardStripeClass(variant), className)}
      data-stripe={variant ?? undefined}
    >
      {children}
    </div>
  );
}
