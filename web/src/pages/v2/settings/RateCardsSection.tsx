/**
 * Settings → Rate cards (spec §18).
 *
 * Tabs: Current / Scheduled / Archived. Columns match spec: effective
 * from, row count, published_at, notes, version status.
 *
 * The API today exposes a single "publish new version" flow keyed to an
 * effective_from date. We derive the three tabs client-side:
 *  - Current  = the row where is_active is true (may be none — blueprint
 *               defaults then apply and we say so honestly).
 *  - Scheduled = versions whose effective_from is in the future.
 *  - Archived  = every superseded version (was active in the past).
 *
 * A new rate card does not retroactively re-price approved GM — the
 * subtitle says so, and the underlying API is versioned so the
 * approval package always points at the version it used.
 *
 * Compensation-level fields are never shown here — the row_count is
 * public metadata. Restricted (cost) fields only render on the detail
 * drawer once the server's `redact_costs` gate authorises the caller.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  listRateCards,
  type RateCardVersionSummary,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../ui-v2/primitives/tabs";

type TabId = "current" | "scheduled" | "archived";

const TAB_ORDER: { id: TabId; label: string; emptyTitle: string; emptyDesc: string }[] = [
  {
    id: "current",
    label: "Current",
    emptyTitle: "No active rate card",
    emptyDesc:
      "Blueprint defaults are in effect until Finance publishes the first version.",
  },
  {
    id: "scheduled",
    label: "Scheduled",
    emptyTitle: "No scheduled versions",
    emptyDesc:
      "A version scheduled to take effect on a future date will appear here.",
  },
  {
    id: "archived",
    label: "Archived",
    emptyTitle: "No archived versions",
    emptyDesc:
      "Superseded versions are kept for evidence; none have been retired yet.",
  },
];

function bucket(rows: RateCardVersionSummary[]): Record<TabId, RateCardVersionSummary[]> {
  const today = new Date().toISOString().slice(0, 10);
  const current: RateCardVersionSummary[] = [];
  const scheduled: RateCardVersionSummary[] = [];
  const archived: RateCardVersionSummary[] = [];
  for (const r of rows) {
    if (r.is_active) current.push(r);
    else if (r.effective_from > today) scheduled.push(r);
    else archived.push(r);
  }
  return { current, scheduled, archived };
}

export function RateCardsSection() {
  const [rows, setRows] = useState<RateCardVersionSummary[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listRateCards()
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState />;
    }
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Rate cards"
          subtitle="Cost and bill bands by role, grade and geography."
        />
        <ErrorState
          title="We couldn't load rate cards."
          description="Retry to try again — filters are preserved."
          onRetry={load}
        />
      </div>
    );
  }

  const buckets = bucket(rows);
  const params = new URLSearchParams(location.search);
  const activeTab = (params.get("tab") as TabId) || "current";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Rate cards"
        subtitle={
          "Cost and bill bands by role, grade and geography. Publishing a new " +
          "version never retroactively re-prices an approved GM — every " +
          "approval package pins the version it used."
        }
      />

      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          const next = new URLSearchParams(location.search);
          next.set("tab", v);
          navigate({ search: next.toString() }, { replace: true });
        }}
      >
        <TabsList aria-label="Rate card tabs">
          {TAB_ORDER.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
              <span className="ml-1 text-secondary text-text-secondary">
                ({buckets[t.id].length})
              </span>
            </TabsTrigger>
          ))}
        </TabsList>

        {TAB_ORDER.map((t) => (
          <TabsContent key={t.id} value={t.id}>
            {loading ? (
              <EmptyState
                title="Loading"
                description="Fetching rate cards."
              />
            ) : buckets[t.id].length === 0 ? (
              <EmptyState title={t.emptyTitle} description={t.emptyDesc} />
            ) : (
              <RateCardTable rows={buckets[t.id]} />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function RateCardTable({ rows }: { rows: RateCardVersionSummary[] }) {
  return (
    <div className="overflow-hidden rounded-panel border border-divider">
      <table className="w-full border-collapse text-body">
        <thead className="bg-primary-subtle/30">
          <tr>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Effective from
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Rows
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Published
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Notes
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.id} className="border-t border-divider">
              <td className="px-3 py-2 text-text tnum">{v.effective_from}</td>
              <td className="px-3 py-2 text-text tnum">{v.row_count}</td>
              <td className="px-3 py-2 text-text-secondary">
                {new Date(v.published_at).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-text-secondary">
                {v.notes ?? "—"}
              </td>
              <td className="px-3 py-2">
                {v.is_active ? (
                  <StatusBadge tone="ok" label="Active" />
                ) : (
                  <StatusBadge tone="neutral" label="Superseded" />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ForbiddenState() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Rate cards" />
      <EmptyState
        title="You don't have access to this section."
        description="Ask a SystemAdmin, Finance, Delivery or HR lead if you need to view rate cards."
      />
    </div>
  );
}
