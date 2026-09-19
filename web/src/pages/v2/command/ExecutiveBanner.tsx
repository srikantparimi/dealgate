/**
 * Executive banner — spec §5 item 1.
 *
 * Dark plum surface with the editorial title "Every commitment. In view.",
 * four inline Metrics, a single lime hero action, and a freshness caption.
 * Every metric is a clickable link that opens its supporting records
 * (spec §5 last paragraph "Every metric opens its supporting records").
 *
 * The tile never fabricates a zero — a missing count renders as the
 * "Unavailable" secondary text (spec §4 state copy).
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { cn } from "../../../lib/cn";

export interface BannerMetric {
  id: string;
  label: string;
  value: string | null;
  href: string;
  description?: ReactNode;
}

export interface ExecutiveBannerProps {
  title?: string;
  subtitle?: string;
  metrics: BannerMetric[];
  freshness?: ReactNode;
  actionLabel?: string;
  actionHref?: string;
}

export function ExecutiveBanner({
  title = "Every commitment. In view.",
  subtitle,
  metrics,
  freshness,
  actionLabel = "Open approval pipeline",
  actionHref = "/sows",
}: ExecutiveBannerProps) {
  return (
    <section
      aria-label="Command center overview"
      className={cn(
        "rounded-hero bg-executive text-executive-fg p-6 sm:p-8",
      )}
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <h1
            className={cn(
              "text-page-mobile sm:text-page text-executive-fg font-semibold",
            )}
          >
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-2 text-body text-executive-muted">{subtitle}</p>
          ) : null}
        </div>
        <div className="flex-shrink-0">
          <Link
            to={actionHref}
            className={cn(
              "inline-flex items-center gap-2 rounded-control",
              "bg-hero text-hero-fg font-medium text-body",
              "px-5 h-12 transition-motion hover:opacity-95",
              "focus-visible:outline-focus",
            )}
          >
            {actionLabel}
            <ArrowUpRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </div>

      <ul
        aria-label="Executive metrics"
        className={cn(
          "mt-6 grid gap-4",
          "sm:grid-cols-2 lg:grid-cols-4",
        )}
      >
        {metrics.map((m) => (
          <li key={m.id}>
            <Link
              to={m.href}
              className={cn(
                "flex flex-col gap-1 rounded-panel p-4 h-full",
                "bg-executive-fg/5 hover:bg-executive-fg/10",
                "transition-motion focus-visible:outline-focus",
              )}
            >
              <span className="text-secondary uppercase tracking-wide text-executive-muted">
                {m.label}
              </span>
              <span
                className={cn(
                  "text-metric tnum text-executive-fg",
                  m.value === null && "text-executive-muted text-body normal-case",
                )}
              >
                {m.value ?? "Unavailable"}
              </span>
              {m.description ? (
                <span className="text-secondary text-executive-muted">
                  {m.description}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>

      {freshness ? (
        <p className="mt-4 text-secondary text-executive-muted">{freshness}</p>
      ) : null}
    </section>
  );
}
