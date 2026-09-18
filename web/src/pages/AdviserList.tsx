import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { AdviserEstimate } from "../api/client";
import { getAdviserEstimate, listAdviserEstimates } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { Table, type Column } from "../ui/Table";
import { EstimateCard } from "./AdviserIntake";

const LEADER_ROLES = new Set([
  "SalesLeader",
  "SystemAdmin",
  "CEO",
  "Finance",
  "Legal",
  "HR",
]);

/**
 * Past-estimates table. Non-leaders see their own drafts; leaders can flip
 * to "All owners" to review the org's pipeline. Reads never mutate the row.
 */
export function AdviserListPage() {
  const { user } = useAuth();
  const isLeader = (user?.groups ?? []).some((g) => LEADER_ROLES.has(g));
  const [rows, setRows] = useState<AdviserEstimate[]>([]);
  const [owner, setOwner] = useState<"me" | "all">("me");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listAdviserEstimates({ owner })
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [owner]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<AdviserEstimate>[] = [
    {
      key: "submitted_at",
      header: "Submitted",
      render: (r) => new Date(r.submitted_at).toLocaleString(),
    },
    {
      key: "client",
      header: "Client",
      render: (r) =>
        (r.inputs as Record<string, unknown>)?.["client_name"] as string ?? "—",
    },
    {
      key: "team",
      header: "Team size",
      render: (r) => r.team.length,
    },
    {
      key: "cost_base",
      header: "Base cost",
      render: (r) =>
        r.cost_base
          ? `$${Number(r.cost_base).toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })}`
          : "—",
    },
    {
      key: "confidence",
      header: "Confidence",
      render: (r) => r.confidence,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Adviser estimates"
        subtitle="Past drafts. Every row is immutable — re-draft for changes."
        right={
          <Link
            to="/adviser/new"
            aria-label="New estimate"
            style={{
              background: "#111827",
              color: "white",
              textDecoration: "none",
              padding: "6px 12px",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            New estimate
          </Link>
        }
      />

      {isLeader ? (
        <div style={{ marginBottom: 12 }}>
          <label
            style={{ fontSize: 12, color: "#374151", marginRight: 8 }}
            htmlFor="adviser-owner-filter"
          >
            Owner
          </label>
          <select
            id="adviser-owner-filter"
            aria-label="Owner filter"
            value={owner}
            onChange={(e) => setOwner(e.target.value as "me" | "all")}
          >
            <option value="me">Mine</option>
            <option value="all">All owners</option>
          </select>
        </div>
      ) : null}

      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching estimates." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No estimates yet"
          hint="Head to the intake to draft your first."
        />
      ) : (
        <Table
          ariaLabel="Adviser estimates"
          columns={columns}
          rows={rows}
          onRowClick={(r) => navigate(`/adviser/${r.id}`)}
        />
      )}
    </div>
  );
}

/**
 * One-estimate detail view. Wraps :func:`EstimateCard` from AdviserIntake so
 * the presentation stays in a single place.
 */
export function AdviserDetailPage() {
  const { id } = useParams();
  const [estimate, setEstimate] = useState<AdviserEstimate | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!id) return;
    setError(null);
    getAdviserEstimate(id)
      .then(setEstimate)
      .catch(setError);
  }, [id]);

  if (error) return <ErrorState error={error} />;
  if (!estimate) return <EmptyState title="Loading" hint="Fetching estimate." />;

  return (
    <div>
      <PageHeader
        title={
          (estimate.inputs as Record<string, unknown>)?.["client_name"] as string ??
          "Estimate"
        }
        subtitle="Read-only. Any change requires a new draft."
      />
      <div
        role="note"
        data-testid="adviser-label"
        style={{
          background: "#fef3c7",
          border: "1px solid #fcd34d",
          color: "#78350f",
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 16,
        }}
      >
        {estimate.label}
      </div>
      <EstimateCard estimate={estimate} />
    </div>
  );
}
