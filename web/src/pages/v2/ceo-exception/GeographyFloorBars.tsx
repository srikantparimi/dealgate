/**
 * S9 — visual floor bars per geography component.
 *
 * Sits above the numeric geography table so the CEO can see the gap to
 * policy in one glance (v2.1 design addendum). Both components are
 * always shown; blended is never used as a substitute (§14).
 */
import type { CeoBriefJson } from "../../../api/client";
import { FloorBar } from "../../../ui-v2/FloorBar";

export function GeographyFloorBars({ brief }: { brief: CeoBriefJson }) {
  const rows: Array<{
    key: "us" | "india";
    label: string;
    value: string | null;
    floor: string | null;
  }> = [
    {
      key: "us",
      label: "US component",
      value: brief.gm.us.value,
      floor: brief.gm.us.floor,
    },
    {
      key: "india",
      label: "India component",
      value: brief.gm.india.value,
      floor: brief.gm.india.floor,
    },
  ];
  return (
    <section
      aria-label="Geography floor visual"
      data-testid="geography-floor-visual"
      className="rounded-panel border border-divider bg-surface p-4 space-y-4"
    >
      <h2 className="text-section text-text">Gap to policy</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {rows.map((r) => (
          <div
            key={r.key}
            data-testid={`geo-bar-${r.key}`}
            className="space-y-2 rounded-panel border border-divider bg-canvas p-3"
          >
            <p className="text-body font-medium text-text">{r.label}</p>
            {r.value != null && r.floor != null ? (
              <FloorBar value={r.value} floor={r.floor} label={r.label} />
            ) : (
              <p className="text-secondary text-text-secondary">
                Not enough data to plot vs floor.
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
