/**
 * Staffing tab (spec §15). Weekly resource capacity + approved/proposed
 * allocation with conflict flags. Filters: role, location, skill and
 * delivery owner.
 *
 * "Proposed staffing does NOT authorize employment or an external
 * commitment." The status column and the drawer copy both reinforce that.
 * The right-side Sheet shows committed work + availability appropriate
 * to the role — cost is not shown to roles without permission.
 */

import { useMemo, useState } from "react";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { Input } from "../../../ui-v2/primitives/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../../../ui-v2/primitives/sheet";
import type { DeliveryResourceLineRow } from "../../../api/client";

export interface StaffingRow {
  id: string;
  personName: string | null;
  role: string;
  seniority: string;
  location: "US" | "India";
  allocationPct: string;
  startDate: string;
  endDate: string;
  /** Server-flagged conflict: over-allocation, HR lead-time, etc. */
  conflict?: { code: string; message: string; severity: "amber" | "red" } | null;
  /** True when the row has no confirmed person yet — proposed only. */
  proposed: boolean;
}

export interface StaffingTabProps {
  rows: StaffingRow[];
  /** Some roles do not have access to per-person cost / rate columns
   *  (spec §19). This flag hides the salary-adjacent columns entirely. */
  showCost?: boolean;
}

/** Convenience helper so callers (or tests) can shape a resource line into
 *  a staffing row without duplicating property mapping. */
export function toStaffingRow(
  line: DeliveryResourceLineRow,
  conflict?: StaffingRow["conflict"],
): StaffingRow {
  return {
    id: line.id,
    personName: line.person_name,
    role: line.role,
    seniority: line.seniority,
    location: line.location,
    allocationPct: line.allocation_pct,
    startDate: line.start_date,
    endDate: line.end_date,
    conflict: conflict ?? null,
    proposed: line.person_name === null,
  };
}

export function StaffingTab({ rows, showCost = false }: StaffingTabProps) {
  const [role, setRole] = useState<string>("");
  const [location, setLocation] = useState<string>("");
  const [owner, setOwner] = useState<string>("");
  const [detail, setDetail] = useState<StaffingRow | null>(null);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (role && !r.role.toLowerCase().includes(role.toLowerCase())) return false;
      if (location && r.location !== location) return false;
      if (owner && !(r.personName ?? "").toLowerCase().includes(owner.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [rows, role, location, owner]);

  return (
    <section aria-label="Weekly staffing" className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div>
          <label
            htmlFor="staffing-role"
            className="text-secondary text-text-secondary uppercase tracking-wide"
          >
            Role
          </label>
          <Input
            id="staffing-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="Any"
          />
        </div>
        <div>
          <label
            htmlFor="staffing-location"
            className="text-secondary text-text-secondary uppercase tracking-wide"
          >
            Location
          </label>
          <select
            id="staffing-location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="mt-1 h-10 w-full rounded-control border border-input-border bg-surface px-2 text-body text-text focus-visible:outline-focus"
          >
            <option value="">Any</option>
            <option value="US">US</option>
            <option value="India">India</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="staffing-owner"
            className="text-secondary text-text-secondary uppercase tracking-wide"
          >
            Delivery owner
          </label>
          <Input
            id="staffing-owner"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="Any"
          />
        </div>
        <div className="flex items-end">
          <p className="text-secondary text-text-secondary">
            Proposed staffing does not authorize employment.
          </p>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No staffing rows match these filters."
          description="Clear filters or adjust the role, location or owner."
        />
      ) : (
        <div className="overflow-x-auto rounded-panel border border-divider">
          <table
            className="w-full text-body"
            aria-label="Weekly staffing"
            data-testid="staffing-table"
          >
            <thead className="bg-primary-subtle/40">
              <tr className="text-left text-secondary text-text-secondary">
                <th className="px-3 py-2 font-medium">Person</th>
                <th className="px-3 py-2 font-medium">Role · Seniority</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 font-medium text-right">Allocation</th>
                <th className="px-3 py-2 font-medium">Start</th>
                <th className="px-3 py-2 font-medium">End</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Conflict</th>
                {showCost ? (
                  <th className="px-3 py-2 font-medium">Cost visible?</th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  data-testid={`staffing-row-${r.id}`}
                  className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                  onClick={() => setDetail(r)}
                >
                  <td className="px-3 py-3 align-top text-text">
                    {r.personName ?? (
                      <span className="text-text-secondary">To hire</span>
                    )}
                  </td>
                  <td className="px-3 py-3 align-top text-text-secondary">
                    {r.role} · {r.seniority}
                  </td>
                  <td className="px-3 py-3 align-top text-text-secondary">
                    {r.location}
                  </td>
                  <td className="px-3 py-3 align-top tnum text-text text-right">
                    {r.allocationPct}%
                  </td>
                  <td className="px-3 py-3 align-top tnum text-text-secondary">
                    {r.startDate}
                  </td>
                  <td className="px-3 py-3 align-top tnum text-text-secondary">
                    {r.endDate}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <StatusBadge
                      tone={r.proposed ? "warn" : "ok"}
                      label={r.proposed ? "Proposed" : "Approved"}
                    />
                  </td>
                  <td className="px-3 py-3 align-top">
                    {r.conflict ? (
                      <StatusBadge
                        tone={conflictTone(r.conflict.severity)}
                        label={r.conflict.code.replace(/_/g, " ")}
                      />
                    ) : (
                      <span className="text-text-secondary">None</span>
                    )}
                  </td>
                  {showCost ? (
                    <td className="px-3 py-3 align-top text-text-secondary">
                      Yes (role-appropriate)
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Sheet
        open={detail !== null}
        onOpenChange={(o) => (o ? undefined : setDetail(null))}
      >
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>
              {detail?.personName ?? "Proposed placement"} · {detail?.role}
            </SheetTitle>
            <SheetDescription>
              Committed work and availability appropriate to this role.
              Proposed staffing does not authorize employment or an external
              commitment.
            </SheetDescription>
          </SheetHeader>
          {detail ? (
            <dl className="mt-4 grid grid-cols-2 gap-y-2 text-body">
              <dt className="text-text-secondary">Location</dt>
              <dd className="text-text">{detail.location}</dd>
              <dt className="text-text-secondary">Allocation</dt>
              <dd className="tnum text-text">{detail.allocationPct}%</dd>
              <dt className="text-text-secondary">Window</dt>
              <dd className="tnum text-text">
                {detail.startDate} → {detail.endDate}
              </dd>
              <dt className="text-text-secondary">Status</dt>
              <dd className="text-text">
                {detail.proposed ? "Proposed" : "Approved"}
              </dd>
              {detail.conflict ? (
                <>
                  <dt className="text-text-secondary">Conflict</dt>
                  <dd className="text-danger">{detail.conflict.message}</dd>
                </>
              ) : null}
            </dl>
          ) : null}
        </SheetContent>
      </Sheet>
    </section>
  );
}

function conflictTone(sev: "amber" | "red"): StatusTone {
  return sev === "red" ? "danger" : "warn";
}
