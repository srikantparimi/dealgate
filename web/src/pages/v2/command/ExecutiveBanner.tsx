/**
 * Executive banner — DealGate v2.1 prototype (lines 179–193, 344–358).
 *
 * Plum surface with:
 *   - Two decorative circles in --plum-line (::before + ::after)
 *   - Editorial headline: Fraunces 500 40px/1.05, italic em rendered in lime
 *   - Eyebrow (uppercase, 11px)
 *   - One-line lede paragraph
 *   - Lime hero button ("Open approval pipeline") + ghost secondary button
 *   - Right-side metric grid: `.bm` tiles on --plum-2 with --plum-line
 *     borders, 26px value, alert values render in --lime.
 *
 * The banner is the ONE surface where Fraunces and lime appear on a plum
 * background. Everything else on the page is Inter on canvas/surface.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../../lib/cn";

export interface BannerMetric {
  id: string;
  label: string;
  value: string | null;
  href: string;
  /** Short caption below the value (e.g. "2 blocked · median age 6 days"). */
  description?: ReactNode;
  /** `alert` metrics use lime for the value. Prototype line 193. */
  alert?: boolean;
}

export interface ExecutiveBannerProps {
  eyebrow?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  metrics: BannerMetric[];
  freshness?: ReactNode;
  actionLabel?: string;
  actionHref?: string;
  secondaryLabel?: string;
  secondaryHref?: string;
}

/** Default editorial headline. Prototype line 348: "Every commitment. In view." */
const DEFAULT_TITLE: ReactNode = (
  <>
    Every commitment.
    <br />
    <em className="italic text-lime">In view.</em>
  </>
);

export function ExecutiveBanner({
  eyebrow,
  title = DEFAULT_TITLE,
  subtitle,
  metrics,
  freshness,
  actionLabel = "Open approval pipeline",
  actionHref = "/sows",
  secondaryLabel,
  secondaryHref,
}: ExecutiveBannerProps) {
  return (
    <section
      aria-label="Executive summary"
      className={cn(
        "relative overflow-hidden rounded-panel bg-plum text-onPlum",
        "px-6 py-7 md:px-8 md:py-8",
        // Two decorative circles per prototype ::before / ::after.
        // Positioned absolutely so they never overlap the text or metrics.
        "before:content-[''] before:absolute before:-right-[120px] before:-top-[160px]",
        "before:h-[420px] before:w-[420px] before:rounded-full before:border before:border-plumLine",
        "before:pointer-events-none",
        "after:content-[''] after:absolute after:right-[40px] after:-top-[60px]",
        "after:h-[220px] after:w-[220px] after:rounded-full after:border after:border-plumLine",
        "after:pointer-events-none",
        "grid gap-6 twoColumnCollapse:grid-cols-[1.1fr_1fr]",
      )}
    >
      <div className="relative z-[1] min-w-0">
        {eyebrow ? (
          <p className="text-[11px] uppercase tracking-[0.08em] font-semibold text-onPlumSecondary">
            {eyebrow}
          </p>
        ) : null}
        <h1
          className={cn(
            "font-display font-medium text-onPlum",
            "text-[30px] leading-[1.05] tracking-[-0.015em]",
            "md:text-[40px]",
            "mt-2 mb-3",
          )}
        >
          {title}
        </h1>
        {subtitle ? (
          <p className="mb-4 max-w-[48ch] text-body text-onPlumSecondary">
            {subtitle}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <Link
            to={actionHref}
            data-testid="banner-hero-cta"
            className={cn(
              "inline-flex items-center rounded-control",
              "bg-lime text-onLime font-semibold",
              "h-9 px-4 text-body",
              "transition-motion hover:brightness-95 focus-visible:outline-focus",
            )}
          >
            {actionLabel}
          </Link>
          {secondaryLabel && secondaryHref ? (
            <Link
              to={secondaryHref}
              className={cn(
                "inline-flex items-center rounded-control",
                "border border-plumLine bg-transparent text-onPlum",
                "h-9 px-4 text-body font-medium",
                "transition-motion hover:bg-plumRaised focus-visible:outline-focus",
              )}
            >
              {secondaryLabel}
            </Link>
          ) : null}
        </div>
        {freshness ? (
          <p className="mt-4 text-secondary text-onPlumSecondary">{freshness}</p>
        ) : null}
      </div>

      <ul
        aria-label="Executive metrics"
        className="relative z-[1] grid grid-cols-2 gap-3 self-center"
      >
        {metrics.map((m) => (
          <li key={m.id}>
            <Link
              to={m.href}
              className={cn(
                "flex h-full flex-col gap-1 rounded-[10px]",
                "border border-plumLine bg-plumRaised",
                "px-4 py-3",
                "transition-motion hover:brightness-110 focus-visible:outline-focus",
              )}
              data-testid={`banner-metric-${m.id}`}
              data-alert={m.alert ? "true" : undefined}
            >
              <span
                className={cn(
                  "tnum text-[26px] leading-[1.05] font-semibold tracking-[-0.02em]",
                  m.alert ? "text-lime" : "text-onPlum",
                  m.value === null && "text-onPlumSecondary text-body font-medium",
                )}
              >
                {m.value ?? "Unavailable"}
              </span>
              <span className="text-[12px] leading-[1.4] text-onPlumSecondary">
                {m.label}
              </span>
              {m.description ? (
                <span className="text-[11px] leading-[1.45] text-onPlumSecondary/75">
                  {m.description}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
