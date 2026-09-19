/**
 * DeliveryModelTemplates — S7 wave 2.
 *
 * Delivery / SystemAdmin manage the shared template catalogue. The
 * Builder header opens this page from the "Load template" picker's
 * "Manage" link (see :file:`DeliveryModelBuilder.tsx`).
 *
 * Templates are shape-only per blueprint §7 rule — no cost values are
 * carried, so the page renders phase/resource counts + engagement type
 * and offers a soft-delete. Hard delete is intentionally absent so
 * past ``gm_model.seeded_from_template`` audit rows remain resolvable.
 */

import { useCallback, useEffect, useState } from "react";
import {
  deleteDeliveryTemplate,
  listDeliveryTemplates,
  type DeliveryTemplateSummary,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";

export function DeliveryModelTemplatesPage() {
  const [items, setItems] = useState<DeliveryTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listDeliveryTemplates();
      setItems(res.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onDelete = useCallback(
    async (id: string) => {
      if (!window.confirm("Deactivate this template?")) return;
      try {
        await deleteDeliveryTemplate(id);
        await load();
      } catch (err) {
        setError(err);
      }
    },
    [load],
  );

  return (
    <div
      data-testid="delivery-templates-page"
      style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}
    >
      <h2 style={{ margin: 0 }}>Delivery-model templates</h2>
      <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
        Reusable model shapes. Cost values are never stored on a template —
        the Builder pulls cost bands from the active rate card when a
        Delivery user seeds a new opportunity.
      </p>
      {error ? <ErrorState error={error} /> : null}
      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="No templates yet"
          hint="Save an approved delivery model from the Builder's header to add one."
        />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f9fafb" }}>
              <th style={cellHead}>Name</th>
              <th style={cellHead}>Engagement</th>
              <th style={cellHead}>Phases</th>
              <th style={cellHead}>Resources</th>
              <th style={cellHead}>Costs</th>
              <th style={cellHead}>Created</th>
              <th style={cellHead}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} data-testid={`template-row-${t.id}`}>
                <td style={cell}>{t.name}</td>
                <td style={cell}>{t.engagement_type}</td>
                <td style={cell}>{t.phase_count}</td>
                <td style={cell}>{t.resource_line_count}</td>
                <td style={cell}>{t.cost_line_count}</td>
                <td style={cell}>
                  {t.created_at
                    ? new Date(t.created_at).toLocaleDateString()
                    : "—"}
                </td>
                <td style={cell}>
                  <button
                    type="button"
                    data-testid={`template-delete-${t.id}`}
                    onClick={() => onDelete(t.id)}
                    style={btnLink}
                  >
                    Deactivate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const cellHead: React.CSSProperties = {
  padding: "8px 12px",
  textAlign: "left",
  borderBottom: "1px solid #e5e7eb",
  fontSize: 12,
  color: "#374151",
};

const cell: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #f3f4f6",
  fontSize: 13,
};

const btnLink: React.CSSProperties = {
  color: "#991b1b",
  background: "none",
  border: "none",
  cursor: "pointer",
};
