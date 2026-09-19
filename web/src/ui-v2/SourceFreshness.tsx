import { RefreshCcw } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface SourceFreshnessProps {
  source: ReactNode;
  asOf?: ReactNode;
  basis?: ReactNode;
  className?: string;
}

/**
 * Small inline caption for tables/panels backed by an integration.
 * Spec §5: always label sample, freshness and financial basis.
 */
export function SourceFreshness({
  source,
  asOf,
  basis,
  className,
}: SourceFreshnessProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-secondary text-text-secondary",
        className,
      )}
    >
      <RefreshCcw className="h-3 w-3" aria-hidden />
      <span>Source: {source}</span>
      {asOf ? <span>· as of {asOf}</span> : null}
      {basis ? <span>· {basis}</span> : null}
    </span>
  );
}
