/**
 * Signed handoff (`/handoffs` list, `/handoffs/:id` detail) — spec §13.4.
 *
 * List view: every approval package that reached signature-ready or
 * later. Columns: client · SOW · exact signed version · account owner ·
 * distribution status · Delivery acknowledgement · billing/PO/staffing
 * setup · renewal creation.
 *
 * Detail view: the four spec §13.4 panels (Distribution,
 * Acknowledgement, Setup checklist, Release evidence) rendered by
 * `handoffs/HandoffDetail`. It layers on top of the existing
 * `SignedSowReview` flow — this page composes the operational view;
 * the verify/release button strip stays on the SOW workspace so a
 * single upload never has two owners.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  listApprovalPackages,
  type ApprovalPackage,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { HandoffDetail } from "./handoffs/HandoffDetail";

type RowStatus = "ready" | "released" | "voided";

function rowStatus(pkg: ApprovalPackage): RowStatus {
  if (pkg.status === "released") return "released";
  if (pkg.status === "voided") return "voided";
  return "ready";
}

function statusTone(s: RowStatus): "ok" | "warn" | "danger" {
  if (s === "released") return "ok";
  if (s === "voided") return "danger";
  return "warn";
}

function statusLabel(s: RowStatus): string {
  if (s === "released") return "Distributed";
  if (s === "voided") return "Voided";
  return "Ready to distribute";
}

function useHandoffPackages() {
  const [rows, setRows] = useState<ApprovalPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Signature-ready + later. The API paginates; 100 fits a wave.
        const [ready, released] = await Promise.all([
          listApprovalPackages({ status: "ready_to_sign", size: 100 }),
          listApprovalPackages({ status: "voided", size: 25 }),
        ]);
        if (cancelled) return;
        setRows([...ready.items, ...released.items]);
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

  return { rows, loading, error };
}

function HandoffList() {
  const { rows, loading, error } = useHandoffPackages();
  const navigate = useNavigate();

  const summary = useMemo(
    () => ({
      total: rows.length,
      released: rows.filter((r) => r.status === "released").length,
    }),
    [rows],
  );

  return (
    <div>
      <PageHeader
        title="Signed handoff"
        subtitle="Every signature-ready and released package. Verify, distribute, acknowledge and set up the engagement — a CRM win is not a release."
      />

      {loading ? (
        <div
          role="status"
          className="rounded-panel border border-divider p-6 text-body text-text-secondary"
        >
          Loading handoffs…
        </div>
      ) : error ? (
        <ErrorState
          title="We couldn't load the handoff list"
          description={
            error instanceof ApiError ? error.message : String(error)
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No signed handoffs yet."
          description="Packages appear here once they reach signature-ready. Signed handoff is the operational destination — release requires verified evidence."
        />
      ) : (
        <>
          <div className="pb-3 text-secondary text-text-secondary">
            {summary.total} total · {summary.released} distributed
          </div>
          <div className="overflow-x-auto rounded-panel border border-divider">
            <table
              className="w-full text-body"
              aria-label="Signed handoffs"
              data-testid="handoff-list-table"
            >
              <thead className="bg-primary-subtle/40">
                <tr className="text-left text-secondary text-text-secondary">
                  <th className="px-3 py-2 font-medium">Client · SOW</th>
                  <th className="px-3 py-2 font-medium">
                    Exact signed version
                  </th>
                  <th className="px-3 py-2 font-medium">Account owner</th>
                  <th className="px-3 py-2 font-medium">Distribution</th>
                  <th className="px-3 py-2 font-medium">Delivery ack</th>
                  <th className="px-3 py-2 font-medium">Setup</th>
                  <th className="px-3 py-2 font-medium">Renewal</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const s = rowStatus(r);
                  return (
                    <tr
                      key={r.id}
                      data-testid={`handoff-row-${r.id}`}
                      className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                      onClick={() => navigate(`/handoffs/${r.id}`)}
                    >
                      <td className="px-3 py-3 align-top">
                        <div className="text-text">Opportunity {r.opportunity_id.slice(0, 8)}</div>
                        <div className="text-secondary text-text-secondary tnum">
                          Package {r.id.slice(0, 8)}
                        </div>
                      </td>
                      <td className="px-3 py-3 align-top tnum text-text">
                        SOW {r.sow_version_id.slice(0, 8)}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {r.submitted_by.slice(0, 8)}
                      </td>
                      <td className="px-3 py-3 align-top">
                        <StatusBadge
                          tone={statusTone(s)}
                          label={statusLabel(s)}
                        />
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {s === "released" ? "Acknowledged" : "Pending"}
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        4 open
                      </td>
                      <td className="px-3 py-3 align-top text-text-secondary">
                        {s === "released" ? "Created" : "Not yet created"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function SignedHandoffPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  if (!id) {
    return <HandoffList />;
  }

  return (
    <div>
      <PageHeader
        title="Signed handoff"
        subtitle={`Handoff ${id}`}
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate("/handoffs")}
            aria-label="Back to handoff list"
          >
            Back to list
          </Button>
        }
      />
      <HandoffDetail handoffId={id} />
    </div>
  );
}
