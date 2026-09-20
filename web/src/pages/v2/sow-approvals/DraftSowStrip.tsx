/**
 * SOWs in progress — the way back to unfinished work (S10-10).
 *
 * The approvals board lists approval *packages*, so a SOW that had not
 * reached one appeared in no lane at all, including "Draft intake". Combined
 * with a staffing grid that reset on refresh and a studio that carried its
 * state only in the URL, a reload looked exactly like data loss: the
 * opportunity, the SOW version and the extracted fields were all safely
 * stored, and no screen in the product would ever show them again.
 *
 * This is that screen. Each row goes back to wherever the SOW actually is —
 * the staffing gate if there is no margin yet, the confirmation screen if
 * there is.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listDraftSows, type DraftSowRow } from "../../../api/client";
import { StatusBadge } from "../../../ui-v2/StatusBadge";

export interface DraftSowStripProps {
  load?: typeof listDraftSows;
}

export function DraftSowStrip({ load = listDraftSows }: DraftSowStripProps) {
  const [rows, setRows] = useState<DraftSowRow[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    load(true)
      .then((res) => {
        if (!cancelled) setRows(res.drafts);
      })
      .catch(() => {
        // The board below is the primary content; a failure here should not
        // take the whole page down.
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  if (!rows || rows.length === 0) return null;

  return (
    <section className="mb-6" data-testid="draft-sow-strip">
      <h3 className="text-heading-4">In progress</h3>
      <p className="mb-3 text-secondary text-text-secondary">
        Started but not yet submitted. Pick up where you left off.
      </p>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {rows.map((d) => (
          <li
            key={d.opportunity_id}
            className="flex flex-wrap items-center gap-3 px-4 py-3"
            data-testid={`draft-${d.opportunity_id}`}
          >
            <span className="font-medium">
              {d.client_name ?? "Unresolved client"}
            </span>
            <span className="text-text-secondary">
              {d.title ?? "No scope extracted"}
            </span>
            <StatusBadge tone="neutral" label={d.governance_status} />
            {/* Says what is actually outstanding, so the row is a next
             * action rather than just a link. */}
            <StatusBadge
              tone={d.has_gm ? "ok" : "warn"}
              label={d.has_gm ? "margin calculated" : "needs staffing"}
            />
            <span className="text-text-secondary">
              {d.uploaded_at ? d.uploaded_at.slice(0, 10) : ""}
            </span>
            <span className="ml-auto">
              <Link
                to={d.resume_href}
                className="text-primary underline underline-offset-2"
                data-testid={`resume-${d.opportunity_id}`}
              >
                {d.has_gm ? "Open confirmation" : "Add staffing"}
              </Link>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
