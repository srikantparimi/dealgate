/**
 * Settings → General (spec §18).
 *
 * Workspace-level metadata + defaults. Every field on this page is either
 * a display preference (safe to change) or a note about how the setting
 * currently lives in the governance record (never editable here — spec
 * §18 is explicit that "policy changes and historical data edits are
 * never casual switches", so we route those to their governed sections).
 *
 * No client-side math. No fake writes. Where an API to persist a value
 * does not yet exist, the field renders read-only and explains why.
 */

import { EmptyState } from "../../../ui-v2/EmptyState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { DirectCostCategories } from "./DirectCostCategories";

interface FieldRow {
  label: string;
  value: string;
  scope: "display" | "governed";
  note?: string;
}

const FIELDS: FieldRow[] = [
  {
    label: "Workspace name",
    value: "SmarTek21",
    scope: "display",
    note: "Header label only. Legal-entity names live under Legal entities.",
  },
  {
    label: "Reporting currency",
    value: "USD",
    scope: "governed",
    note:
      "Applies to future records. Existing SOWs keep the currency captured " +
      "at approval time.",
  },
  {
    label: "Business timezone",
    value: "America/New_York",
    scope: "display",
    note:
      "Used for banner timestamps. Every audit row still stores UTC and its " +
      "own local timezone.",
  },
  {
    label: "Fiscal calendar",
    value: "Calendar year (Jan – Dec)",
    scope: "governed",
    note: "Governs weekly forecast + actuals grouping. Changes require Finance.",
  },
  {
    label: "Working calendars",
    value: "US · India",
    scope: "governed",
    note: "Drives HR lead-time and start-date warnings.",
  },
  {
    label: "Notification routing",
    value: "Per-user preferences",
    scope: "display",
    note: "Individual routing lives under Profile → Notification preferences.",
  },
];

interface EntityRow {
  name: string;
  country: string;
  status: "active" | "read_only";
}

const LEGAL_ENTITIES: EntityRow[] = [
  { name: "SmarTek21, Inc.", country: "United States", status: "active" },
  { name: "SmarTek21 Software Pvt Ltd", country: "India", status: "active" },
];

export function GeneralSection() {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="General"
        subtitle={
          "Workspace defaults. Preferences are safe to change; governed " +
          "fields apply to future records only. Existing SOWs and approvals " +
          "keep the values captured at their approval time."
        }
      />

      <section aria-label="Workspace fields" className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {FIELDS.map((f) => (
            <div
              key={f.label}
              className="rounded-panel border border-divider bg-surface p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-secondary text-text-secondary uppercase tracking-wide">
                  {f.label}
                </span>
                <StatusBadge
                  tone={f.scope === "display" ? "primarySubtle" : "warn"}
                  label={
                    f.scope === "display"
                      ? "Display preference"
                      : "Applies to future records"
                  }
                />
              </div>
              <p className="mt-2 text-section text-text">{f.value}</p>
              {f.note ? (
                <p className="mt-2 text-secondary text-text-secondary">
                  {f.note}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <DirectCostCategories />

      <section
        aria-label="Legal entities"
        className="flex flex-col gap-3"
      >
        <div className="flex flex-col gap-1">
          <h2 className="text-section text-text">Legal entities</h2>
          <p className="text-secondary text-text-secondary">
            Editable only via a governed change. Renaming an entity here does
            not rename an executed agreement or SOW.
          </p>
        </div>
        {LEGAL_ENTITIES.length === 0 ? (
          <EmptyState
            title="No legal entities recorded"
            description="Ask a SystemAdmin to add the first entity."
          />
        ) : (
          <div className="overflow-hidden rounded-panel border border-divider">
            <table className="w-full border-collapse text-body">
              <thead className="bg-primary-subtle/30">
                <tr>
                  <th className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
                    Entity
                  </th>
                  <th className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
                    Country
                  </th>
                  <th className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {LEGAL_ENTITIES.map((e) => (
                  <tr
                    key={e.name}
                    className="border-t border-divider"
                  >
                    <td className="px-3 py-2 text-text">{e.name}</td>
                    <td className="px-3 py-2 text-text-secondary">
                      {e.country}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge
                        tone={e.status === "active" ? "ok" : "neutral"}
                        label={e.status === "active" ? "Active" : "Read-only"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
