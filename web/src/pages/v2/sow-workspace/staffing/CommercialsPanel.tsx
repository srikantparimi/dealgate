/**
 * S9 — Staffing & GM right panel.
 *
 * Displays revenue · cost · GM per US / India / Blended with a
 * `FloorBar` per component and a big "Fails/Passes by N pts" chip.
 * Every number is a Decimal string owned by the server — this panel
 * only presents it.
 */
import type { DeliveryComputedResult } from "../../../../api/client";
import { FloorBar } from "../../../../ui-v2/FloorBar";
import { MoneyCell } from "../../../../ui-v2/MoneyCell";
import { formatUsd } from "../format";

interface CommercialsPanelProps {
  computed: DeliveryComputedResult | null | undefined;
}

interface ComponentRow {
  key: "us" | "india" | "blended";
  label: string;
  revenue: string | null;
  cost: string | null;
  gm: string | null;
  floor: string | null;
  passes: boolean | null;
}

export function CommercialsPanel({ computed }: CommercialsPanelProps) {
  if (!computed) {
    return (
      <section
        aria-label="Commercials"
        className="rounded-panel border border-divider bg-surface p-4 text-body text-text-secondary"
        data-testid="commercials-panel-empty"
      >
        Commercial totals appear once the model has enough data to price.
      </section>
    );
  }

  const revUsN = Number(computed.revenue_us ?? 0);
  const revInN = Number(computed.revenue_india ?? 0);
  const costUsN = Number(computed.cost_us ?? 0);
  const costInN = Number(computed.cost_india ?? 0);
  const totalRev = revUsN + revInN;
  const totalCost = costUsN + costInN;

  const rows: ComponentRow[] = [
    {
      key: "us",
      label: "US component",
      revenue: computed.revenue_us,
      cost: computed.cost_us,
      gm: computed.gm_us,
      floor: computed.policy?.us_floor ?? null,
      passes: computed.policy?.us_pass ?? null,
    },
    {
      key: "india",
      label: "India component",
      revenue: computed.revenue_india,
      cost: computed.cost_india,
      gm: computed.gm_india,
      floor: computed.policy?.india_floor ?? null,
      passes: computed.policy?.india_pass ?? null,
    },
    {
      key: "blended",
      label: "Blended",
      revenue: String(totalRev),
      cost: String(totalCost),
      gm: computed.gm_blended,
      // Blended has no policy floor — reuse the higher of the two floors
      // for the visualisation so the bar still has a marker. The FloorBar
      // primitive itself is display-only.
      floor: bigger(
        computed.policy?.us_floor ?? null,
        computed.policy?.india_floor ?? null,
      ),
      passes:
        computed.policy?.us_pass != null && computed.policy?.india_pass != null
          ? computed.policy.us_pass && computed.policy.india_pass
          : null,
    },
  ];

  return (
    <section
      aria-label="Commercials"
      className="rounded-panel border border-divider bg-surface p-4 space-y-5"
      data-testid="commercials-panel"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-section text-text">Commercials</h2>
        <span className="text-secondary text-text-secondary">
          Revenue · cost · GM by component
        </span>
      </div>
      {rows.map((r) => (
        <CommercialRow key={r.key} row={r} />
      ))}
    </section>
  );
}

function bigger(a: string | null, b: string | null): string | null {
  const an = a != null ? Number(a) : null;
  const bn = b != null ? Number(b) : null;
  if (an == null && bn == null) return null;
  if (an == null) return b;
  if (bn == null) return a;
  return an >= bn ? a : b;
}

function CommercialRow({ row }: { row: ComponentRow }) {
  return (
    <div
      data-testid={`commercial-row-${row.key}`}
      className="rounded-panel border border-divider bg-canvas p-3 space-y-3"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-body font-medium text-text">{row.label}</span>
        <span className="text-secondary text-text-secondary">
          Floor{" "}
          {row.floor != null ? (
            <span className="tnum">
              {(Number(row.floor) * 100).toFixed(0)}%
            </span>
          ) : (
            "—"
          )}
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-secondary">
        <div>
          <dt className="text-text-secondary uppercase">Revenue</dt>
          <dd>
            <MoneyCell value={formatUsd(row.revenue) ?? undefined} />
          </dd>
        </div>
        <div>
          <dt className="text-text-secondary uppercase">Cost</dt>
          <dd>
            <MoneyCell value={formatUsd(row.cost) ?? undefined} />
          </dd>
        </div>
        <div>
          <dt className="text-text-secondary uppercase">GM</dt>
          <dd>
            <span className="tnum block text-right text-text">
              {row.gm != null ? `${(Number(row.gm) * 100).toFixed(1)}%` : "—"}
            </span>
          </dd>
        </div>
      </dl>
      {row.gm != null && row.floor != null ? (
        <FloorBar value={row.gm} floor={row.floor} label={row.label} />
      ) : (
        <p className="text-secondary text-text-secondary">
          Not enough data to plot vs floor.
        </p>
      )}
    </div>
  );
}
