/**
 * ApprovalQueue — inbox of packages waiting for the current user's role.
 *
 * The server is the sole source of truth on who can decide what. This page
 * asks for the two "pending" statuses and lets the reviewer approve /
 * reject / request changes inline. A click on a row navigates to
 * :file:`ApprovalPackageDetail.tsx` for the full snapshot.
 *
 * No math in the browser (blueprint §2). The floors block on the detail
 * page renders whatever the API sends; the inline actions post the
 * decision and re-fetch the row.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  decideApprovalPackage,
  listApprovalPackages,
  type ApprovalDecision,
  type ApprovalFunction,
  type ApprovalPackage,
  type ApprovalPackageStatus,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

const STATUS_TONE: Record<ApprovalPackageStatus, "ok" | "warn" | "block" | "neutral"> = {
  pending_delivery_hr: "warn",
  pending_finance_legal: "warn",
  pending_ceo_exception: "block",
  ready_to_sign: "ok",
  voided: "neutral",
  rejected: "block",
};

const ROLE_TO_FUNCTION: Record<string, ApprovalFunction> = {
  Delivery: "delivery",
  HR: "hr",
  Finance: "finance",
  Legal: "legal",
};

function pickFunction(groups: readonly string[]): ApprovalFunction | null {
  for (const g of groups) {
    if (g in ROLE_TO_FUNCTION) return ROLE_TO_FUNCTION[g];
  }
  return null;
}

function useOptionalAuth() {
  try {
    const { user } = useAuth();
    return user;
  } catch {
    return null;
  }
}

export function ApprovalQueuePage() {
  const user = useOptionalAuth();
  const groups = user?.groups ?? [];
  const fn = useMemo(() => pickFunction(groups), [groups]);

  const [items, setItems] = useState<ApprovalPackage[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setError(null);
    try {
      // The server filters by role; the browser asks for both pending
      // statuses so a Finance user sees packages that just cleared
      // Delivery/HR.
      const [d, f] = await Promise.all([
        listApprovalPackages({ status: "pending_delivery_hr" }),
        listApprovalPackages({ status: "pending_finance_legal" }),
      ]);
      const merged = [...d.items, ...f.items];
      merged.sort((a, b) => (a.submitted_at ?? "").localeCompare(b.submitted_at ?? ""));
      setItems(merged);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const alreadyDecided = useCallback(
    (pkg: ApprovalPackage) => {
      if (!fn) return true;
      return pkg.approvals.some((a) => a.function === fn);
    },
    [fn],
  );

  const relevant = useMemo(() => {
    if (!fn) return items;
    if (fn === "delivery" || fn === "hr") {
      return items.filter((p) => p.status === "pending_delivery_hr");
    }
    return items.filter((p) => p.status === "pending_finance_legal");
  }, [items, fn]);

  const decide = useCallback(
    async (pkg: ApprovalPackage, decision: ApprovalDecision) => {
      if (!fn) return;
      const key = `${pkg.id}:${decision}`;
      setBusy((prev) => new Set(prev).add(key));
      try {
        await decideApprovalPackage(pkg.id, fn, { decision });
        await load();
      } catch (e) {
        setError(e);
      } finally {
        setBusy((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [fn, load],
  );

  const cols: Column<ApprovalPackage>[] = [
    {
      key: "id",
      header: "Package",
      render: (p) => (
        <Link to={`/approvals/${p.id}`} style={{ color: "#1d4ed8" }}>
          {p.id.slice(0, 8)}…
        </Link>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (p) => (
        <StatusChip tone={STATUS_TONE[p.status]}>{p.status}</StatusChip>
      ),
    },
    {
      key: "submitted_at",
      header: "Submitted",
      render: (p) => (p.submitted_at ? p.submitted_at.slice(0, 19) + "Z" : "—"),
    },
    {
      key: "actions",
      header: "Actions",
      render: (p) => {
        if (!fn) return <span style={{ color: "#6b7280" }}>Read-only</span>;
        if (alreadyDecided(p)) {
          return <span style={{ color: "#6b7280" }}>Decided</span>;
        }
        return (
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              onClick={() => decide(p, "approve")}
              disabled={busy.has(`${p.id}:approve`)}
              data-testid={`approve-${p.id}`}
              style={{
                padding: "4px 10px",
                background: "#065f46",
                color: "white",
                border: "none",
                borderRadius: 4,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => decide(p, "reject")}
              disabled={busy.has(`${p.id}:reject`)}
              data-testid={`reject-${p.id}`}
              style={{
                padding: "4px 10px",
                background: "#991b1b",
                color: "white",
                border: "none",
                borderRadius: 4,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Reject
            </button>
            <button
              type="button"
              onClick={() => decide(p, "request_changes")}
              disabled={busy.has(`${p.id}:request_changes`)}
              data-testid={`request-${p.id}`}
              style={{
                padding: "4px 10px",
                background: "#b45309",
                color: "white",
                border: "none",
                borderRadius: 4,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Request changes
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Approvals"
        subtitle={
          fn ? (
            <span>
              Signed in as <strong>{fn}</strong> reviewer.
            </span>
          ) : (
            <span>Governance read-only.</span>
          )
        }
      />
      {error ? <ErrorState error={error} retry={load} /> : null}
      {relevant.length === 0 ? (
        <EmptyState
          title="Nothing to review"
          hint="Packages awaiting your function will appear here."
        />
      ) : (
        <Table
          ariaLabel="Approval packages"
          columns={cols}
          rows={relevant.map((p) => ({ ...p }))}
        />
      )}
    </div>
  );
}
