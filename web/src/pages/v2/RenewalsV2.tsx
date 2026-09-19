/**
 * Renewals V2 (`/renewals-v2`) — spec §16.
 *
 * Tabs: Action required / Weekly follow-ups / Upcoming / Closed.
 * The weekly view lists trigger date, reminder event, owner, delivery
 * outcome and recorded response.
 *
 * Data: `listRenewals` for the list, `patchRenewal` for updates. Row
 * click opens a right Sheet (`RenewalWorkspaceSheet`) that gathers the
 * update note + a fixed-enum outcome. "Client interested" is not one
 * of those enums — the dropdown enforces that.
 *
 * Reminder maths (spec §16) live in `renewals/reminders.ts` and are
 * unit-tested independently of the table view.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  listRenewals,
  type RenewalRow,
  type RenewalStatus,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Input } from "../../ui-v2/primitives/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { RenewalWorkspaceSheet } from "./renewals/RenewalWorkspaceSheet";
import { computeReminderPlan } from "./renewals/reminders";

type TabKey = "action" | "weekly" | "upcoming" | "closed";

const TABS: { key: TabKey; label: string }[] = [
  { key: "action", label: "Action required" },
  { key: "weekly", label: "Weekly follow-ups" },
  { key: "upcoming", label: "Upcoming" },
  { key: "closed", label: "Closed" },
];

function inTab(row: RenewalRow, tab: TabKey): boolean {
  const d = row.days_until_end;
  if (tab === "closed")
    return row.status === "closed" || row.status === "churn";
  if (tab === "action") return row.status === "open" && d <= 30;
  if (tab === "weekly")
    return row.status === "open" && d <= 60 && d > 30;
  if (tab === "upcoming") return row.status === "open" && d > 60;
  return false;
}

function healthTone(row: RenewalRow): "ok" | "warn" | "danger" | "neutral" {
  if (row.status === "closed") return "neutral";
  if (row.status === "churn") return "danger";
  if (row.days_until_end <= 14) return "danger";
  if (row.days_until_end <= 60) return "warn";
  return "ok";
}

function healthLabel(row: RenewalRow): string {
  if (row.status === "closed") return "Closed";
  if (row.status === "churn") return "Churn";
  if (row.days_until_end <= 14) return "Immediate";
  if (row.days_until_end <= 60) return "Weekly review";
  return "On track";
}

function statusLabel(status: RenewalStatus, days: number): string {
  if (status === "closed") return "Closed";
  if (status === "extended") return "Extended";
  if (status === "churn") return "Not renewing";
  if (days <= 0) return "Overdue";
  if (days <= 14) return "Notice window";
  if (days <= 60) return "Weekly review";
  return "Upcoming";
}

export function RenewalsV2Page() {
  const [rows, setRows] = useState<RenewalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<TabKey>("action");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<RenewalRow | null>(null);
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const res = await listRenewals({ size: 200 });
      setRows(res.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await listRenewals({ size: 200 });
        if (cancelled) return;
        setRows(res.items);
      } catch (err) {
        if (cancelled) return;
        setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (!inTab(r, tab)) return false;
      if (!query) return true;
      const q = query.toLowerCase();
      return (
        (r.hubspot_deal_id?.toLowerCase().includes(q) ?? false) ||
        r.opportunity_id.toLowerCase().includes(q) ||
        (r.outcome_summary?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [rows, tab, query]);

  const counts = useMemo(() => {
    return TABS.reduce<Record<TabKey, number>>(
      (acc, t) => {
        acc[t.key] = rows.filter((r) => inTab(r, t.key)).length;
        return acc;
      },
      { action: 0, weekly: 0, upcoming: 0, closed: 0 },
    );
  }, [rows]);

  const emptyReason: Record<TabKey, string> = {
    action: "No renewals need immediate action.",
    weekly: "No renewals in the weekly-review window.",
    upcoming: "No renewals outside the two-month window.",
    closed: "No closed renewals to show.",
  };

  return (
    <div>
      <PageHeader
        title="Renewals"
        subtitle="Two calendar months before expiry, plus weekly follow-ups until the outcome is verified. A CRM win is not a signed renewal."
      />

      <div className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
          <TabsList aria-label="Renewal tabs">
            {TABS.map((t) => (
              <TabsTrigger key={t.key} value={t.key}>
                {t.label} ({counts[t.key]})
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="sm:w-64">
          <Input
            type="search"
            aria-label="Search renewals"
            placeholder="Search deal, opportunity or note"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsContent value={tab} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading renewals…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load renewals"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title={emptyReason[tab]}
              description="Switch tabs, adjust the search or wait for the next reminder trigger."
            />
          ) : tab === "weekly" ? (
            <WeeklyTable
              rows={filtered}
              today={today}
              onRowClick={setDetail}
            />
          ) : (
            <StandardTable rows={filtered} onRowClick={setDetail} />
          )}
        </TabsContent>
      </Tabs>

      <RenewalWorkspaceSheet
        open={detail !== null}
        onOpenChange={(o) => (o ? undefined : setDetail(null))}
        renewal={detail}
        today={today}
        onSaved={(patched) => {
          setRows((prev) =>
            prev.map((r) => (r.id === patched.id ? patched : r)),
          );
          setDetail(null);
          void reload();
        }}
      />
    </div>
  );
}

function StandardTable({
  rows,
  onRowClick,
}: {
  rows: RenewalRow[];
  onRowClick: (row: RenewalRow) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-panel border border-divider">
      <table
        className="w-full text-body"
        aria-label="Renewals"
        data-testid="renewals-table"
      >
        <thead className="bg-primary-subtle/40">
          <tr className="text-left text-secondary text-text-secondary">
            <th className="px-3 py-2 font-medium">Client · SOW</th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Signed value at risk</th>
            <th className="px-3 py-2 font-medium">Expiry</th>
            <th className="px-3 py-2 font-medium">Notice deadline</th>
            <th className="px-3 py-2 font-medium">Days remaining</th>
            <th className="px-3 py-2 font-medium">Last client update</th>
            <th className="px-3 py-2 font-medium">Stage</th>
            <th className="px-3 py-2 font-medium">Health</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              data-testid={`renewal-row-${r.id}`}
              className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
              onClick={() => onRowClick(r)}
            >
              <td className="px-3 py-3 align-top">
                <div className="text-text">
                  {r.hubspot_deal_id ?? r.opportunity_id.slice(0, 8)}
                </div>
                <div className="text-secondary text-text-secondary tnum">
                  Opp {r.opportunity_id.slice(0, 8)}
                </div>
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {r.owner_id ? r.owner_id.slice(0, 8) : "Unassigned"}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                Unavailable
              </td>
              <td className="px-3 py-3 align-top tnum text-text">
                {r.term_end}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary tnum">
                From contract
              </td>
              <td className="px-3 py-3 align-top tnum text-text">
                {r.days_until_end}
              </td>
              <td className="px-3 py-3 align-top text-text-secondary">
                {r.outcome_summary ?? "No update"}
              </td>
              <td className="px-3 py-3 align-top">
                <StatusBadge
                  tone={healthTone(r)}
                  label={statusLabel(r.status, r.days_until_end)}
                />
              </td>
              <td className="px-3 py-3 align-top">
                <StatusBadge tone={healthTone(r)} label={healthLabel(r)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WeeklyTable({
  rows,
  today,
  onRowClick,
}: {
  rows: RenewalRow[];
  today: string;
  onRowClick: (row: RenewalRow) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-panel border border-divider">
      <table
        className="w-full text-body"
        aria-label="Weekly renewal follow-ups"
        data-testid="renewals-weekly-table"
      >
        <thead className="bg-primary-subtle/40">
          <tr className="text-left text-secondary text-text-secondary">
            <th className="px-3 py-2 font-medium">Trigger date</th>
            <th className="px-3 py-2 font-medium">Reminder event</th>
            <th className="px-3 py-2 font-medium">Owner</th>
            <th className="px-3 py-2 font-medium">Delivery outcome</th>
            <th className="px-3 py-2 font-medium">Recorded response</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const plan = computeReminderPlan({
              today,
              expiryDate: r.term_end,
            });
            const nextTrigger =
              plan.weeklyOccurrences.find((d) => d >= today) ??
              plan.weeklyOccurrences[0] ??
              plan.firstAlertDate;
            return (
              <tr
                key={r.id}
                data-testid={`renewal-weekly-row-${r.id}`}
                className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                onClick={() => onRowClick(r)}
              >
                <td className="px-3 py-3 align-top tnum text-text">
                  {nextTrigger}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  Weekly check-in ({plan.weeklyOccurrences.length} scheduled)
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {r.owner_id ? r.owner_id.slice(0, 8) : "Unassigned"}
                </td>
                <td className="px-3 py-3 align-top">
                  <StatusBadge
                    tone={healthTone(r)}
                    label={statusLabel(r.status, r.days_until_end)}
                  />
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {r.outcome_summary ?? "None yet"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
