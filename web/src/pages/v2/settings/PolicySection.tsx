/**
 * Settings → Margin policy (spec §18).
 *
 * Read-only summary of the effective floors + FX convention. Tabs:
 * Current / Pending / History. "Propose change" opens a structured
 * proposal card that explicitly notes that only Finance can publish and
 * a floor lower than the current cannot be published without CEO
 * review — the server enforces that gate, so this is a UX reminder
 * only (CLAUDE.md rule 5, blueprint §2).
 *
 * The current policy card echoes spec §18 verbatim: US 35% · India 50%
 * · mixed-component rule · cost definition · allocation requirement ·
 * exception authority.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  listPolicies,
  type ActivePolicy,
  type PolicyVersionRow,
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

type TabId = "current" | "pending" | "history";

export function PolicySection() {
  const [rows, setRows] = useState<PolicyVersionRow[]>([]);
  const [active, setActive] = useState<ActivePolicy | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listPolicies()
      .then((res) => {
        setRows(res.items);
        setActive(res.active);
      })
      .catch((err) => {
        setError(err);
        setRows([]);
        setActive(null);
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
        <PageHeader title="Margin policy" />
        <ErrorState
          title="We couldn't load the margin policy."
          description="Retry to try again."
          onRetry={load}
        />
      </div>
    );
  }

  const params = new URLSearchParams(location.search);
  const activeTab = (params.get("tab") as TabId) || "current";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Margin policy"
        subtitle={
          "US floor 35% · India floor 50% · mixed-component rule · cost " +
          "definition · allocation requirement · exception authority. Every " +
          "change is versioned; the CEO is the only exception authority."
        }
      />

      <CurrentPolicyCard active={active} loading={loading} />

      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          const next = new URLSearchParams(location.search);
          next.set("tab", v);
          navigate({ search: next.toString() }, { replace: true });
        }}
      >
        <TabsList aria-label="Policy tabs">
          <TabsTrigger value="current">Current policy</TabsTrigger>
          <TabsTrigger value="pending">Pending changes</TabsTrigger>
          <TabsTrigger value="history">
            History
            <span className="ml-1 text-secondary text-text-secondary">
              ({rows.length})
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="current">
          <CurrentPolicyDetail active={active} />
        </TabsContent>

        <TabsContent value="pending">
          <ProposeChangePanel />
        </TabsContent>

        <TabsContent value="history">
          {loading ? (
            <EmptyState title="Loading" description="Fetching policy history." />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No versions yet"
              description="Blueprint defaults are in effect until Finance publishes the first version."
            />
          ) : (
            <PolicyHistoryTable rows={rows} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CurrentPolicyCard({
  active,
  loading,
}: {
  active: ActivePolicy | null;
  loading: boolean;
}) {
  if (loading && !active) {
    return (
      <div
        className="h-24 rounded-panel border border-divider bg-surface animate-pulse"
        aria-hidden
      />
    );
  }
  if (!active) return null;
  return (
    <div
      aria-label="Active policy summary"
      className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex items-center gap-3">
        <StatusBadge
          tone={active.is_default ? "warn" : "ok"}
          label={active.is_default ? "Defaults in effect" : "Active"}
        />
        <span className="text-secondary text-text-secondary">
          {active.effective_from
            ? `Effective ${active.effective_from}`
            : "No version published — blueprint defaults apply."}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 text-body sm:grid-cols-3">
        <SummaryCell label="US floor" value={active.us_floor} />
        <SummaryCell label="India floor" value={active.india_floor} />
        <SummaryCell label="FX convention" value={active.fx_convention} />
      </div>
    </div>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-divider bg-canvas px-3 py-2">
      <p className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </p>
      <p className="text-section text-text tnum">{value}</p>
    </div>
  );
}

function CurrentPolicyDetail({ active }: { active: ActivePolicy | null }) {
  return (
    <div className="flex flex-col gap-4 rounded-panel border border-divider bg-surface p-4">
      <div>
        <h3 className="text-section text-text">Policy in effect</h3>
        <p className="mt-1 text-secondary text-text-secondary">
          These rules govern every SOW approval. Blueprint §2 is the source of
          truth if this panel and the blueprint ever diverge.
        </p>
      </div>
      <ul className="flex flex-col gap-2 text-body text-text">
        <li>
          <strong>US floor:</strong> {active?.us_floor ?? "0.3500"} — a US-only
          SOW below this margin requires a CEO exception.
        </li>
        <li>
          <strong>India floor:</strong> {active?.india_floor ?? "0.5000"} — an
          India-only SOW below this margin requires a CEO exception.
        </li>
        <li>
          <strong>Mixed-component rule:</strong> a SOW with both US and India
          resources must clear <em>both</em> component floors independently — a
          strong blended margin does not offset a failing component.
        </li>
        <li>
          <strong>Cost definition:</strong> fully-loaded cost including
          benefits, tools, travel and subcontractor spend booked to the SOW.
        </li>
        <li>
          <strong>Allocation requirement:</strong> every resource line must be
          bound to a WBS phase before a package can be submitted.
        </li>
        <li>
          <strong>Exception authority:</strong> CEO only. A delegation may
          extend authority for a bounded window; the delegate and the CEO both
          appear in the audit trail.
        </li>
      </ul>
    </div>
  );
}

function ProposeChangePanel() {
  return (
    <div className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4">
      <h3 className="text-section text-text">Propose a change</h3>
      <p className="text-body text-text-secondary">
        A policy change is not a switch on this page. A proposal captures the
        new values, reason, effective date, scope and impact preview; Finance
        publishes it and the CEO signs off if a floor moves down. Every
        publish creates an immutable version.
      </p>
      <ol className="ml-5 list-decimal text-body text-text">
        <li>Draft the new values (US floor, India floor, FX convention).</li>
        <li>Record the reason and the target effective date.</li>
        <li>
          Review the impact preview — which in-flight packages would need
          re-evaluation.
        </li>
        <li>
          Submit for approval. A floor decrease requires CEO sign-off; the
          server enforces this even if the UI is bypassed.
        </li>
      </ol>
      <p className="text-secondary text-text-secondary">
        No draft proposals in flight.
      </p>
    </div>
  );
}

function PolicyHistoryTable({ rows }: { rows: PolicyVersionRow[] }) {
  return (
    <div className="overflow-hidden rounded-panel border border-divider">
      <table className="w-full border-collapse text-body">
        <thead className="bg-primary-subtle/30">
          <tr>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Effective from
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              US floor
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              India floor
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              FX
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
              <td className="px-3 py-2 text-text tnum">{v.us_floor}</td>
              <td className="px-3 py-2 text-text tnum">{v.india_floor}</td>
              <td className="px-3 py-2 text-text-secondary">
                {v.fx_convention}
              </td>
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
      <PageHeader title="Margin policy" />
      <EmptyState
        title="You don't have access to this section."
        description="Ask a SystemAdmin or Finance lead if you need to view or change the margin policy."
      />
    </div>
  );
}
