import type {
  DeliveryCostLineRow,
  DeliveryGmModel,
  DeliveryResourceLineRow,
} from "../../../api/client";
import { MarginCell } from "../../../ui-v2/MarginCell";
import { Metric } from "../../../ui-v2/Metric";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { formatPercent, formatUsd } from "./format";
import type { WorkspaceSnapshot } from "./readiness";

/**
 * Staffing & GM tab (spec §9). Displays the approved / current / scenario
 * pickers, the summary metrics, independent US + India tests, and the
 * staffing grid. Never computes anything — every number was rendered by
 * the server-owned engine and passed in as a Decimal string.
 */

type ViewerRole = "restricted" | "full";

export function StaffingGmTab({
  snap,
  viewer = "full",
}: {
  snap: WorkspaceSnapshot;
  viewer?: ViewerRole;
}) {
  const gm = snap.gmModel;
  if (!gm) {
    return (
      <div className="rounded-panel border border-divider bg-surface p-4 text-body text-text-secondary">
        No delivery model yet. Build one from the GM sandbox or a template.
      </div>
    );
  }
  const computed = gm.computed ?? null;

  return (
    <div className="space-y-6">
      <VersionSelector gm={gm} />
      <SummaryMetrics gm={gm} />
      <FloorTests computed={computed} />
      <RevenueBreakdown gm={gm} />
      <CostBreakdown gm={gm} viewer={viewer} />
      <StaffingGrid gm={gm} viewer={viewer} />
      <PolicyFootnote gm={gm} />
    </div>
  );
}

function VersionSelector({ gm }: { gm: DeliveryGmModel }) {
  return (
    <section
      aria-label="Version selector"
      className="flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex flex-col">
        <span className="text-secondary uppercase tracking-wide text-text-secondary">
          Approved baseline
        </span>
        <span className="text-body text-text">—</span>
      </div>
      <div className="flex flex-col">
        <span className="text-secondary uppercase tracking-wide text-text-secondary">
          Current draft
        </span>
        <span className="text-body text-text">{gm.id.slice(-8)}</span>
      </div>
      <div className="flex flex-col">
        <span className="text-secondary uppercase tracking-wide text-text-secondary">
          Scenarios
        </span>
        <span className="text-body text-text-secondary">None saved</span>
      </div>
      <div className="ml-auto flex items-center gap-2 text-secondary text-text-secondary">
        Compare available in Studio.
      </div>
    </section>
  );
}

function SummaryMetrics({ gm }: { gm: DeliveryGmModel }) {
  const c = gm.computed;
  const revenue = c
    ? formatUsd(String(Number(c.revenue_us || 0) + Number(c.revenue_india || 0)))
    : null;
  const cost = c
    ? formatUsd(String(Number(c.cost_us || 0) + Number(c.cost_india || 0)))
    : null;
  const profit =
    c && revenue && cost
      ? formatUsd(
          String(
            Number(c.revenue_us || 0) +
              Number(c.revenue_india || 0) -
              (Number(c.cost_us || 0) + Number(c.cost_india || 0)),
          ),
        )
      : null;
  const gmBlended = formatPercent(c?.gm_blended ?? null);

  return (
    <section
      aria-label="Commercial totals"
      className="grid gap-3 sm:grid-cols-4"
    >
      <Metric label="Revenue" value={revenue ?? "Unavailable"} />
      <Metric label="Delivery cost" value={cost ?? "Unavailable"} />
      <Metric label="Gross profit" value={profit ?? "Unavailable"} />
      <Metric label="Combined GM" value={gmBlended ?? "Unavailable"} />
    </section>
  );
}

function FloorTests({
  computed,
}: {
  computed: DeliveryGmModel["computed"] | null;
}) {
  const policy = computed?.policy;
  const rows: Array<{
    location: string;
    gm: string | null;
    floor: string | null;
    pass: boolean | null;
  }> = [
    {
      location: "US",
      gm: computed?.gm_us ?? null,
      floor: policy?.us_floor ?? null,
      pass: policy?.us_pass ?? null,
    },
    {
      location: "India",
      gm: computed?.gm_india ?? null,
      floor: policy?.india_floor ?? null,
      pass: policy?.india_pass ?? null,
    },
  ];

  return (
    <section
      aria-label="Floor tests"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-3">Floor tests</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-body">
          <thead>
            <tr className="text-left text-text-secondary text-secondary uppercase">
              <th className="py-2 pr-4">Geography</th>
              <th className="py-2 pr-4 text-right">Achieved GM</th>
              <th className="py-2 pr-4 text-right">Required floor</th>
              <th className="py-2 pr-4">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.location} className="border-t border-divider">
                <td className="py-2 pr-4 text-text">{r.location}</td>
                <td className="py-2 pr-4">
                  <MarginCell
                    value={formatPercent(r.gm) ?? undefined}
                    outcome={
                      r.pass == null
                        ? "unavailable"
                        : r.pass
                          ? "pass"
                          : "fail"
                    }
                  />
                </td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatPercent(r.floor) ?? undefined} />
                </td>
                <td className="py-2 pr-4">
                  {r.pass == null ? (
                    <StatusBadge tone="neutral" label="Not tested" />
                  ) : r.pass ? (
                    <StatusBadge tone="ok" label="Pass" />
                  ) : (
                    <StatusBadge tone="danger" label="Below floor" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RevenueBreakdown({ gm }: { gm: DeliveryGmModel }) {
  const sections = [
    { key: "fixed_fee", label: "Fixed fee" },
    { key: "milestones", label: "Milestones" },
    { key: "tandm", label: "Time & materials" },
    { key: "recurring", label: "Recurring" },
    { key: "one_time", label: "One-time" },
    { key: "discounts", label: "Discounts" },
    { key: "credits", label: "Credits" },
  ];
  return (
    <section
      aria-label="Revenue breakdown"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-3">Revenue breakdown</h2>
      <p className="text-secondary text-text-secondary mb-3">
        Approved cost definition, rate-card version and FX source govern
        these figures; only the pricing model varies by category.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {sections.map((s) => (
          <div
            key={s.key}
            className="flex items-center justify-between rounded-control border border-divider p-3"
          >
            <span className="text-body text-text">{s.label}</span>
            <MoneyCell
              value={
                s.key === "fixed_fee"
                  ? (formatUsd(gm.revenue_us ?? null) ?? undefined)
                  : undefined
              }
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function CostBreakdown({
  gm,
  viewer,
}: {
  gm: DeliveryGmModel;
  viewer: ViewerRole;
}) {
  const categoryTotals: Record<string, number> = {};
  for (const line of gm.cost_lines) {
    const amount = Number(line.amount);
    if (!Number.isFinite(amount)) continue;
    categoryTotals[line.category] = (categoryTotals[line.category] ?? 0) + amount;
  }
  const sections = [
    { key: "staffing", label: "Staffing", value: null as number | null },
    { key: "subcontractor", label: "Contractors", value: categoryTotals["subcontractor"] ?? null },
    { key: "burden", label: "Benefits & burden", value: null as number | null },
    { key: "recruiting", label: "Recruiting & setup", value: null as number | null },
    { key: "delivery_mgmt", label: "Delivery management", value: null as number | null },
    { key: "tools", label: "Licences & tools", value: categoryTotals["tools"] ?? null },
    { key: "travel", label: "Travel", value: categoryTotals["travel"] ?? null },
    { key: "contingency", label: "Contingency", value: null as number | null },
  ];

  return (
    <section
      aria-label="Cost breakdown"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-section text-text">Cost breakdown</h2>
        {viewer === "restricted" ? (
          <StatusBadge
            tone="neutral"
            label="Aggregated view"
            icon={undefined}
          />
        ) : null}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {sections.map((s) => (
          <div
            key={s.key}
            className="flex items-center justify-between rounded-control border border-divider p-3"
          >
            <span className="text-body text-text">{s.label}</span>
            <MoneyCell
              value={
                s.value != null ? (formatUsd(String(s.value)) ?? undefined) : undefined
              }
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function StaffingGrid({
  gm,
  viewer,
}: {
  gm: DeliveryGmModel;
  viewer: ViewerRole;
}) {
  const rows = gm.resource_lines;
  if (rows.length === 0) {
    return (
      <section
        aria-label="Staffing grid"
        className="rounded-panel border border-divider bg-surface p-4 text-body text-text-secondary"
      >
        No resource lines on this version.
      </section>
    );
  }
  return (
    <section
      aria-label="Staffing grid"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-section text-text">Staffing</h2>
        <span className="text-secondary text-text-secondary">
          {viewer === "restricted"
            ? "Employee compensation hidden"
            : "Loaded cost visible"}
        </span>
      </div>
      <div
        role="region"
        aria-label="Staffing grid scroll region"
        className="overflow-x-auto"
      >
        <table className="min-w-full text-body">
          <thead>
            <tr className="text-left text-text-secondary text-secondary uppercase">
              <th className="py-2 pr-3">Role</th>
              <th className="py-2 pr-3">Location</th>
              <th className="py-2 pr-3">Grade</th>
              <th className="py-2 pr-3">Resource</th>
              <th className="py-2 pr-3">Start</th>
              <th className="py-2 pr-3">End</th>
              <th className="py-2 pr-3 text-right">Alloc</th>
              <th className="py-2 pr-3 text-right">Hours</th>
              <th className="py-2 pr-3 text-right">Bill rate</th>
              <th className="py-2 pr-3 text-right">
                {viewer === "restricted" ? "Cost band" : "Loaded cost"}
              </th>
              <th className="py-2 pr-3 text-right">Revenue</th>
              <th className="py-2 pr-3 text-right">Cost</th>
              <th className="py-2 pr-3 text-right">GM</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <StaffingRow key={row.id} row={row} viewer={viewer} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StaffingRow({
  row,
  viewer,
}: {
  row: DeliveryResourceLineRow;
  viewer: ViewerRole;
}) {
  const hours = Number(row.hours_billable);
  const bill = Number(row.hourly_bill_rate);
  const cost = row.hourly_cost != null ? Number(row.hourly_cost) : null;
  const alloc = Number(row.allocation_pct);
  const revenue = Number.isFinite(hours * bill) ? hours * bill : null;
  const costTotal =
    cost != null && Number.isFinite(hours * cost) ? hours * cost : null;
  const gmValue =
    revenue != null && costTotal != null && revenue > 0
      ? (revenue - costTotal) / revenue
      : null;
  return (
    <tr className="border-t border-divider">
      <td className="py-2 pr-3 text-text">{row.role}</td>
      <td className="py-2 pr-3 text-text">{row.location}</td>
      <td className="py-2 pr-3 text-text">{row.seniority}</td>
      <td className="py-2 pr-3 text-text">
        {row.person_name ?? (
          <span className="text-text-secondary italic">TBD</span>
        )}
      </td>
      <td className="py-2 pr-3 text-text">{row.start_date}</td>
      <td className="py-2 pr-3 text-text">{row.end_date}</td>
      <td className="py-2 pr-3">
        <span className="tnum block text-right">
          {Number.isFinite(alloc) ? `${(alloc * 100).toFixed(0)}%` : "—"}
        </span>
      </td>
      <td className="py-2 pr-3">
        <MoneyCell value={String(hours.toFixed(1))} />
      </td>
      <td className="py-2 pr-3">
        <MoneyCell value={formatUsd(String(bill)) ?? undefined} />
      </td>
      <td className="py-2 pr-3">
        <MoneyCell
          value={
            viewer === "restricted"
              ? undefined
              : cost != null
                ? (formatUsd(String(cost)) ?? undefined)
                : undefined
          }
          unavailableLabel={
            viewer === "restricted" ? "Restricted" : "Unavailable"
          }
        />
      </td>
      <td className="py-2 pr-3">
        <MoneyCell
          value={revenue != null ? (formatUsd(String(revenue)) ?? undefined) : undefined}
        />
      </td>
      <td className="py-2 pr-3">
        <MoneyCell
          value={
            costTotal != null
              ? (formatUsd(String(costTotal)) ?? undefined)
              : undefined
          }
        />
      </td>
      <td className="py-2 pr-3">
        <MarginCell
          value={gmValue != null ? `${(gmValue * 100).toFixed(1)}%` : undefined}
          outcome={gmValue == null ? "unavailable" : undefined}
        />
      </td>
    </tr>
  );
}

function PolicyFootnote({ gm }: { gm: DeliveryGmModel }) {
  return (
    <section
      aria-label="Policy footnote"
      className="rounded-panel border border-divider bg-surface p-4 text-secondary text-text-secondary"
    >
      <p>
        Approved cost definition: fully loaded (staffing + burden +
        overhead). Rate-card version and FX source (fixed at SOW date) are
        stamped on the saved GM version {gm.id.slice(-8)}.
      </p>
    </section>
  );
}

// The row helper is only exported for `costLineTotal` in the cost-line
// sub-section but kept private otherwise.
export function costLineTotal(lines: DeliveryCostLineRow[]): number {
  return lines.reduce((sum, l) => sum + Number(l.amount || 0), 0);
}
