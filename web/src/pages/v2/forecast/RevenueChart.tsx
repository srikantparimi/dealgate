import type { ForecastPeriod } from "../../../api/forecast";

const PLOT_HEIGHT = 184;

export function RevenueChart({
  months,
  currency,
  onMonth,
}: {
  months: ForecastPeriod[];
  currency: string;
  onMonth: (month: string) => void;
}) {
  // Numbers below affect pixel geometry only; all amounts and totals are server values.
  const values = months.flatMap((period) => [
    Number(period.signed),
    Number(period.potential),
  ]);
  const maximum = Math.max(1, ...values.filter(Number.isFinite));
  const height = (value: string) =>
    Number.isFinite(Number(value))
      ? `${(Math.max(0, Number(value)) / maximum) * PLOT_HEIGHT}px`
      : "0px";
  return (
    <section
      aria-label="Signed and potential revenue chart"
      className="my-5 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Revenue outlook / {currency}</h2>
        <div className="flex gap-4 text-secondary">
          <span className="flex items-center gap-2">
            <i className="h-3 w-3 bg-emerald-600" />
            Signed
          </span>
          <span className="flex items-center gap-2">
            <i className="h-3 w-3 bg-sky-600" />
            Potential
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <div
          className="grid items-end gap-3 border-b border-divider"
          style={{
            gridTemplateColumns: `repeat(${months.length || 1}, minmax(56px, 1fr))`,
          }}
        >
          {months.map((period) => {
            const date = new Date(`${period.start}T00:00:00Z`);
            const name = date.toLocaleDateString("en-US", {
              month: "long",
              year: "numeric",
              timeZone: "UTC",
            });
            return (
              <button
                key={period.start}
                aria-label={`Inspect ${name}`}
                title={`${name}: signed ${period.signed}, potential ${period.potential} ${currency}`}
                className="grid gap-2 px-1 focus-visible:outline-focus"
                style={{ gridTemplateRows: `${PLOT_HEIGHT}px 32px` }}
                onClick={() => onMonth(period.start)}
              >
                <span
                  className="flex items-end justify-center gap-1"
                  style={{ height: PLOT_HEIGHT }}
                  aria-hidden
                >
                  <span
                    className="w-4 bg-emerald-600"
                    style={{ height: height(period.signed) }}
                  />
                  <span
                    className="w-4 bg-sky-600"
                    style={{ height: height(period.potential) }}
                  />
                </span>
                <span className="whitespace-nowrap text-xs">
                  {date.toLocaleDateString("en-US", {
                    month: "short",
                    year: "2-digit",
                    timeZone: "UTC",
                  })}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
