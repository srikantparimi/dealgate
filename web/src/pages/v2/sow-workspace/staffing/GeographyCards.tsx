/**
 * GeographyCards — DealGate v2.1 prototype (lines 240–247, 441–445).
 *
 * Three side-by-side geography cards:
 *   - Combined · informational (no gate; big number)
 *   - US component · floor 35%
 *   - India component · floor 50%
 *
 * Each per-geography card carries a big 28px number, a floor bar with
 * marker + label, and a two-column key-value list underneath. This is the
 * primary visual anchor for "does this SOW pass its floors" — Sales can
 * see the gap without opening the CEO exception page.
 */
import type { DeliveryComputedResult } from "../../../../api/client";
import { FloorBar } from "../../../../ui-v2/FloorBar";
import { StatusBadge, type StatusTone } from "../../../../ui-v2/StatusBadge";
import { cn } from "../../../../lib/cn";

interface GeographyCardsProps {
  computed: DeliveryComputedResult | null | undefined;
  /** US floor as a Decimal string, defaults to "0.35" per policy. */
  usFloor?: string;
  /** India floor as a Decimal string, defaults to "0.50" per policy. */
  indiaFloor?: string;
}

function pct(v: string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n <= 1 ? n * 100 : n;
}

function usd(v: string | null | undefined): string | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function gapChip(gm: number | null, floor: number): {
  tone: StatusTone;
  label: string;
} {
  if (gm == null) return { tone: "neutral", label: "Revenue required" };
  const gap = gm - floor;
  if (gap >= 0) {
    return { tone: "success", label: `Passes by ${gap.toFixed(1)} pts` };
  }
  return { tone: "danger", label: `Fails by ${(-gap).toFixed(1)} pts` };
}

export function GeographyCards({
  computed,
  usFloor = "0.35",
  indiaFloor = "0.50",
}: GeographyCardsProps) {
  const usGm = pct(computed?.gm_us ?? null);
  const inGm = pct(computed?.gm_india ?? null);
  const blendedGm = pct(computed?.gm_blended ?? null);
  const usFloorPct = pct(usFloor) ?? 35;
  const inFloorPct = pct(indiaFloor) ?? 50;
  const usRev = usd(computed?.revenue_us ?? null);
  const usCost = usd(computed?.cost_us ?? null);
  const inRev = usd(computed?.revenue_india ?? null);
  const inCost = usd(computed?.cost_india ?? null);
  const totalRev =
    computed?.revenue_us != null && computed?.revenue_india != null
      ? usd(
          String(
            Number(computed.revenue_us) + Number(computed.revenue_india),
          ),
        )
      : null;
  const totalCost =
    computed?.cost_us != null && computed?.cost_india != null
      ? usd(
          String(Number(computed.cost_us) + Number(computed.cost_india)),
        )
      : null;
  const totalGp =
    computed?.revenue_us != null &&
    computed?.revenue_india != null &&
    computed?.cost_us != null &&
    computed?.cost_india != null
      ? usd(
          String(
            Number(computed.revenue_us) +
              Number(computed.revenue_india) -
              (Number(computed.cost_us) + Number(computed.cost_india)),
          ),
        )
      : null;

  const usChip = gapChip(usGm, usFloorPct);
  const inChip = gapChip(inGm, inFloorPct);

  return (
    <section
      aria-label="Margin tests"
      className="grid gap-4 twoColumnCollapse:grid-cols-3"
      data-testid="staffing-geography-cards"
    >
      <GeoCard
        eyebrow="Combined · informational"
        chip={<StatusBadge tone="neutral" label="Not a gate" />}
        gmPct={blendedGm}
        kv={[
          ["Revenue", totalRev ?? "Unavailable"],
          ["Delivery cost", totalCost ?? "Unavailable"],
          ["Gross profit", totalGp ?? "Unavailable"],
        ]}
      />
      <GeoCard
        eyebrow="US component · floor 35%"
        chip={<StatusBadge tone={usChip.tone} label={usChip.label} />}
        gmPct={usGm}
        floorBar={
          computed?.gm_us != null ? (
            <FloorBar value={computed.gm_us} floor={usFloor} label="US" showChip={false} />
          ) : null
        }
        kv={[
          ["Revenue", usRev ?? "Unavailable"],
          ["Cost", usCost ?? "Unavailable"],
        ]}
      />
      <GeoCard
        eyebrow="India component · floor 50%"
        chip={<StatusBadge tone={inChip.tone} label={inChip.label} />}
        gmPct={inGm}
        floorBar={
          computed?.gm_india != null ? (
            <FloorBar
              value={computed.gm_india}
              floor={indiaFloor}
              label="India"
              showChip={false}
            />
          ) : null
        }
        kv={[
          ["Revenue", inRev ?? "Unavailable"],
          ["Cost", inCost ?? "Unavailable"],
        ]}
      />
    </section>
  );
}

function GeoCard({
  eyebrow,
  chip,
  gmPct,
  floorBar,
  kv,
}: {
  eyebrow: string;
  chip: React.ReactNode;
  gmPct: number | null;
  floorBar?: React.ReactNode;
  kv: [string, string][];
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-card border border-border bg-surface p-5",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.06em] font-semibold text-text-secondary">
          {eyebrow}
        </span>
        {chip}
      </div>
      <div className="text-[28px] font-semibold leading-none tracking-[-0.02em] tnum text-text">
        {gmPct != null ? `${gmPct.toFixed(1)}%` : "—"}
        <span className="ml-[6px] text-[13px] font-normal text-text-secondary">
          GM
        </span>
      </div>
      {floorBar ?? null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[6px] text-[13px]">
        {kv.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-text-secondary">{k}</dt>
            <dd className="text-right font-medium text-text tnum">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
