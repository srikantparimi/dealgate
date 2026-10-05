import { Plus, Trash2 } from "lucide-react";
import type {
  CalendarHours,
  CommercialCalendar,
  CommercialComponent,
  CommercialStaffing,
  CommercialStaffingRate,
} from "../../../../api/commercial";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { Field, Select } from "./Fields";

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const hours = (): CalendarHours => ({ scheduled: "", billable: "", paid: "" });
export function CalendarFields({
  component,
  onChange,
}: {
  component: CommercialComponent;
  onChange: (component: CommercialComponent) => void;
}) {
  const assignments = component.staffing;
  const rates = component.pricing?.rates ?? [];
  const update = (index: number, value: CommercialStaffing) =>
    onChange({
      ...component,
      staffing: assignments.map((row, i) => (i === index ? value : row)),
    });
  const rateFor = (row: CommercialStaffing): CommercialStaffingRate =>
    rates.find((rate) => rate.assignment_id === row.assignment_id) ?? {
      assignment_id: row.assignment_id,
      basis: "",
      rate: null,
      version: null,
      hours_per_day: null,
      proration: null,
    };
  const updateRate = (row: CommercialStaffing, rate: CommercialStaffingRate) =>
    onChange({
      ...component,
      pricing: {
        ...component.pricing,
        rates: [
          ...rates.filter((value) => value.assignment_id !== row.assignment_id),
          rate,
        ],
      },
    });
  return (
    <section aria-label="Calendar staffing" className="min-w-0 space-y-5">
      <h3 className="font-medium">Calendar staffing</h3>
      {assignments.map((row, index) => {
        const patch = (key: keyof CommercialStaffing, value: unknown) =>
          update(index, { ...row, [key]: value });
        const rate = rateFor(row);
        return (
          <section
            key={row.assignment_id}
            aria-label={`Assignment ${index + 1}`}
            className="space-y-4 border-t border-divider pt-4"
          >
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-medium">
                {row.role || `Assignment ${index + 1}`}
              </h4>
              <Button
                variant="ghost"
                size="icon"
                title="Remove assignment and its pricing rate"
                aria-label={`Remove assignment ${index + 1}`}
                onClick={() =>
                  onChange({
                    ...component,
                    staffing: assignments.filter((_, i) => i !== index),
                    ...(component.profile === "calendar_staff_aug"
                      ? {
                          pricing: {
                            ...component.pricing,
                            rates: rates.filter(
                              (value) =>
                                value.assignment_id !== row.assignment_id,
                            ),
                          },
                        }
                      : {}),
                  })
                }
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Field
                label="Role"
                value={row.role}
                onChange={(value) => patch("role", value)}
              />
              <Select
                label="Assignment location"
                value={row.location}
                options={["US", "India"]}
                onChange={(value) => patch("location", value || null)}
              />
              <label>
                Headcount
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={row.quantity || ""}
                  onChange={(event) =>
                    patch(
                      "quantity",
                      event.target.value === ""
                        ? 0
                        : Number(event.target.value),
                    )
                  }
                />
              </label>
              <Field
                label="Allocation fraction"
                type="decimal"
                value={row.allocation}
                onChange={(value) => patch("allocation", value)}
              />
              <Field
                label="Assignment start"
                type="date"
                value={row.start}
                onChange={(value) => patch("start", value || null)}
              />
              <Field
                label="Assignment end"
                type="date"
                value={row.end}
                onChange={(value) => patch("end", value || null)}
              />
              <Field
                label="Assignment timezone"
                value={row.timezone}
                onChange={(value) => patch("timezone", value)}
              />
              <Field
                label="Assignment currency"
                value={row.currency}
                onChange={(value) => patch("currency", value || null)}
              />
              <Select
                label="Cost rate basis"
                value={row.cost_rate_basis === undefined ? "hourly" : row.cost_rate_basis}
                options={[{ value: "hourly", label: "Per paid hour" }, { value: "monthly", label: "Monthly per person" }]}
                onChange={(value) => update(index, { ...row,
                  cost_rate_basis: value === "hourly" || value === "monthly" ? value : null,
                  cost_rate: null, cost_version: null, cost_proration: null,
                })}
              />
              {row.cost_rate_basis === "monthly" && (
                <Select
                  label="Partial-month cost policy"
                  value={row.cost_proration}
                  options={[{ value: "full_month", label: "Full monthly allocation" }]}
                  onChange={(value) => patch("cost_proration", value || null)}
                />
              )}
              <Field
                label={row.cost_rate_basis === "monthly" ? "Monthly cost per person" : "Loaded cost rate"}
                type="decimal"
                value={row.cost_rate}
                onChange={(value) => patch("cost_rate", value || null)}
              />
              <Field
                label="Cost source version"
                value={row.cost_version}
                onChange={(value) => patch("cost_version", value || null)}
              />
              <Field
                label="Hourly bill rate"
                type="decimal"
                value={row.bill_rate}
                onChange={(value) => patch("bill_rate", value || null)}
              />
              <Field
                label="Bill rate source version"
                value={row.rate_version}
                onChange={(value) => patch("rate_version", value || null)}
              />
            </div>
            {component.profile === "calendar_staff_aug" && (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Select
                  label="Pricing rate basis"
                  value={rate.basis}
                  options={["hourly", "daily", "monthly"]}
                  onChange={(value) =>
                    updateRate(row, { ...rate, basis: value })
                  }
                />
                <Field
                  label="Contract rate"
                  type="decimal"
                  value={rate.rate}
                  onChange={(value) =>
                    updateRate(row, { ...rate, rate: value || null })
                  }
                />
                <Field
                  label="Pricing rate version"
                  value={rate.version}
                  onChange={(value) =>
                    updateRate(row, { ...rate, version: value || null })
                  }
                />
                <Field
                  label="Billable hours per day"
                  type="decimal"
                  value={rate.hours_per_day}
                  onChange={(value) =>
                    updateRate(row, { ...rate, hours_per_day: value || null })
                  }
                />
                <Select
                  label="Monthly proration"
                  value={rate.proration}
                  options={["calendar_days", "full_month"]}
                  onChange={(value) =>
                    updateRate(row, { ...rate, proration: value || null })
                  }
                />
              </div>
            )}
            {row.calendar ? (
              <CalendarEditor
                calendar={row.calendar}
                onChange={(value) => patch("calendar", value)}
              />
            ) : (
              <Button
                variant="secondary"
                onClick={() =>
                  patch("calendar", {
                    calendar_id: "",
                    version: "",
                    timezone: row.timezone,
                    coverage_start: component.service_start ?? "",
                    coverage_end: component.service_end ?? "",
                    week: DAYS.map(hours),
                    overrides: [],
                  })
                }
              >
                <Plus className="h-4 w-4" />
                Add confirmed calendar
              </Button>
            )}
          </section>
        );
      })}
      <Button
        variant="secondary"
        onClick={() =>
          onChange({
            ...component,
            staffing: [
              ...assignments,
              {
                assignment_id: crypto.randomUUID(),
                source_id: component.source_id,
                source_version: component.source_version,
                component_id: component.component_id,
                profile_version: component.profile_version,
                policy_version: component.policy_version,
                role: "",
                location: null,
                timezone: component.timezone ?? "",
                currency: component.currency,
                quantity: 0,
                allocation: "",
                calendar: null,
                bill_rate: null,
                cost_rate: null,
                rate_version: null,
                cost_version: null,
                start: component.service_start,
                end: component.service_end,
              },
            ],
          })
        }
      >
        <Plus className="h-4 w-4" />
        Add assignment
      </Button>
    </section>
  );
}
function CalendarEditor({
  calendar,
  onChange,
}: {
  calendar: CommercialCalendar;
  onChange: (value: CommercialCalendar) => void;
}) {
  const patch = (key: keyof CommercialCalendar, value: unknown) =>
    onChange({ ...calendar, [key]: value });
  return (
    <div className="space-y-4">
      <h4 className="font-medium">Versioned work calendar</h4>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(
          [
            ["calendar_id", "Calendar source ID"],
            ["version", "Calendar version"],
            ["timezone", "Calendar timezone"],
            ["coverage_start", "Coverage start"],
            ["coverage_end", "Coverage end"],
          ] as const
        ).map(([key, label]) => (
          <Field
            key={key}
            label={label}
            value={calendar[key]}
            type={key.startsWith("coverage") ? "date" : "text"}
            onChange={(value) => patch(key, value)}
          />
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-secondary">
          <thead>
            <tr>
              <th>Day</th>
              <th>Scheduled hours</th>
              <th>Billable hours</th>
              <th>Paid hours</th>
            </tr>
          </thead>
          <tbody>
            {DAYS.map((day, index) => (
              <tr key={day}>
                <th className="pr-3 font-normal">{day}</th>
                {(["scheduled", "billable", "paid"] as const).map((key) => (
                  <td key={key} className="min-w-28 p-1">
                    <Input
                      aria-label={`${day} ${key} hours`}
                      inputMode="decimal"
                      value={calendar.week[index]?.[key] ?? ""}
                      onChange={(event) =>
                        patch(
                          "week",
                          DAYS.map((_, i) =>
                            i === index
                              ? {
                                  ...(calendar.week[i] ?? hours()),
                                  [key]: event.target.value,
                                }
                              : (calendar.week[i] ?? hours()),
                          ),
                        )
                      }
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4 className="font-medium">Holidays and service exceptions</h4>
      {calendar.overrides.map((override, index) => (
        <div key={index} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label={`Exception date ${index + 1}`}
            type="date"
            value={override.day}
            onChange={(value) =>
              patch(
                "overrides",
                calendar.overrides.map((item, i) =>
                  i === index ? { ...item, day: value } : item,
                ),
              )
            }
          />
          <Field
            label={`Exception reason ${index + 1}`}
            value={override.reason}
            onChange={(value) =>
              patch(
                "overrides",
                calendar.overrides.map((item, i) =>
                  i === index ? { ...item, reason: value } : item,
                ),
              )
            }
          />
          {(["scheduled", "billable", "paid"] as const).map((key) => (
            <Field
              key={key}
              label={`Exception ${key} hours ${index + 1}`}
              value={override.hours[key]}
              type="decimal"
              onChange={(value) =>
                patch(
                  "overrides",
                  calendar.overrides.map((item, i) =>
                    i === index
                      ? { ...item, hours: { ...item.hours, [key]: value } }
                      : item,
                  ),
                )
              }
            />
          ))}
          <Button
            variant="ghost"
            title="Delete service exception"
            aria-label={`Delete exception ${index + 1}`}
            onClick={() =>
              patch(
                "overrides",
                calendar.overrides.filter((_, i) => i !== index),
              )
            }
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button
        variant="secondary"
        onClick={() =>
          patch("overrides", [
            ...calendar.overrides,
            { day: "", hours: hours(), reason: "" },
          ])
        }
      >
        <Plus className="h-4 w-4" />
        Add calendar exception
      </Button>
    </div>
  );
}
