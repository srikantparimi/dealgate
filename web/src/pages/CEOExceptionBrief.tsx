/**
 * CEO exception brief page (S4 E7, Agent V).
 *
 * Shows the pre-computed brief for a package that failed a policy floor
 * and lets the right people act on it. The page has three panels:
 *
 * 1. The brief — read-only, driven straight from ``brief_json``. Every
 *    number is a ``DecimalStr`` and is rendered as-is (no float math in
 *    the browser, per CLAUDE.md rule 2).
 * 2. The rationale — the account owner sees an editable textarea until
 *    they save. Everyone else sees the current text read-only. A "Tidy
 *    up my wording" toggle lets the owner ask Bedrock to lightly
 *    copyedit before save; the raw text is what the API stores.
 * 3. Decision — visible only to the CEO / SystemAdmin. Approve requires
 *    a saved rationale; Reject and Return skip that guard. The API
 *    still enforces every rule server-side.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { FinanceGmPanel } from "./v2/sow-workspace/staffing/FinanceGmPanel";
import { DirectCostsEditor } from "./v2/sow-workspace/staffing/DirectCostsEditor";
import { useParams } from "react-router-dom";
import {
  type CeoDecision,
  type CeoException,
  getCeoException,
  patchCeoRationale,
  postCeoDecision,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";

const DECIDE_ROLES = new Set(["CEO", "SystemAdmin"]);

function fmtMoney(v: string | null | undefined): string {
  if (!v) return "—";
  // Money is a Decimal-string on the wire — parse only for display
  // formatting; never mutate the value before it's rendered.
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function CEOExceptionBriefPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  const canDecide = groups.some((g) => DECIDE_ROLES.has(g));

  const [row, setRow] = useState<CeoException | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [rationaleDraft, setRationaleDraft] = useState("");
  const [tidy, setTidy] = useState(false);
  const [savingRat, setSavingRat] = useState(false);
  const [savingDecision, setSavingDecision] = useState(false);
  const [conditions, setConditions] = useState("");
  const [validUntil, setValidUntil] = useState("");

  const load = useCallback(() => {
    if (!id) return;
    setError(null);
    getCeoException(id)
      .then((r) => {
        setRow(r);
        setRationaleDraft(r.rationale_text ?? "");
      })
      .catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Owner is inferred from a matching rationale_set_by; before rationale
  // is set, the API decides ownership via the opportunity — the UI opens
  // the textarea for anyone who can *potentially* be the owner (i.e. the
  // API will 403 non-owners on save). Falling back to the current user
  // is a safe hint; a wrong guess just yields a 403 the UI shows.
  const rationaleEditable = useMemo(() => {
    if (!row) return false;
    if (row.decision !== null) return false;
    if (row.rationale_set_by && user?.sub === row.rationale_set_by) return true;
    // No rationale yet — allow editing; server 403s the wrong caller.
    return row.rationale_text === null;
  }, [row, user]);

  if (error) return <ErrorState error={error} retry={load} />;
  if (!row) return <EmptyState title="Loading" hint="Fetching brief." />;

  const b = row.brief_json;

  const saveRationale = async () => {
    if (!id) return;
    setSavingRat(true);
    try {
      const updated = await patchCeoRationale(id, {
        rationale_text: rationaleDraft,
        tidy,
      });
      setRow(updated);
      setRationaleDraft(updated.rationale_text ?? "");
    } catch (err) {
      setError(err);
    } finally {
      setSavingRat(false);
    }
  };

  const decide = async (decision: CeoDecision) => {
    if (!id) return;
    if (decision === "approve" && !(row.rationale_text ?? "").trim()) {
      setError(new Error("A saved rationale is required before approve."));
      return;
    }
    setSavingDecision(true);
    try {
      const updated = await postCeoDecision(id, {
        decision,
        conditions_text: decision === "approve" ? conditions || null : null,
        valid_until: decision === "approve" ? validUntil || null : null,
      });
      setRow(updated);
    } catch (err) {
      setError(err);
    } finally {
      setSavingDecision(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="CEO exception brief"
        subtitle={`${b.client.name || "Unknown client"} — ${b.scope || "no scope on file"}`}
      />
      {row.decision ? (
        <div
          data-testid="ceo-decision-banner"
          style={{
            padding: "10px 14px",
            background:
              row.decision === "approve" ? "#d1fae5" : "#fee2e2",
            color: row.decision === "approve" ? "#065f46" : "#991b1b",
            borderRadius: 8,
            marginBottom: 16,
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          Decision: {row.decision.toUpperCase().replace(/_/g, " ")}
          {row.valid_until ? ` — valid until ${row.valid_until}` : ""}
        </div>
      ) : null}

      {/* Client + scope */}
      <section data-testid="ceo-brief-client" style={{ marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 6px 0" }}>Client</h3>
        <div style={{ color: "#374151", fontSize: 14 }}>{b.client.context || "—"}</div>
        <h3 style={{ margin: "16px 0 6px 0" }}>Scope</h3>
        <div style={{ color: "#374151", fontSize: 14 }}>{b.scope || "—"}</div>
        <h3 style={{ margin: "16px 0 6px 0" }}>Team</h3>
        <div style={{ color: "#374151", fontSize: 14 }}>{b.team_summary || "—"}</div>
      </section>

      <div className="mb-6 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        {b.cost_lines !== undefined ? <DirectCostsEditor rows={b.cost_lines} /> : <div />}
        <FinanceGmPanel result={b.floors ?? { finance_summary: b.finance_summary, revenue_total: b.revenue.blended, gm_us: b.gm.us.value, gm_india: b.gm.india.value, gm_blended: b.gm.blended.value, us_floor: b.gm.us.floor ?? undefined, india_floor: b.gm.india.floor ?? undefined, us_pass: b.gm.us.passes, india_pass: b.gm.india.passes }} state="review snapshot" />
      </div>
      <p className="mb-5 text-secondary text-text-secondary">Price uplift needed · US: {fmtMoney(b.price_uplift.us)} · India: {fmtMoney(b.price_uplift.india)}. Gross-profit shortfall: {fmtMoney(b.gross_profit_shortfall_usd)}</p>

      {/* Recommendations + alternatives */}
      <section style={{ marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 6px 0" }}>Alternatives considered</h3>
        {b.alternatives.length === 0 ? (
          <div style={{ color: "#9ca3af", fontSize: 14 }}>None recorded.</div>
        ) : (
          <ul>
            {b.alternatives.map((a, i) => (
              <li key={i} style={{ fontSize: 14 }}>{a}</li>
            ))}
          </ul>
        )}
        <h3 style={{ margin: "12px 0 6px 0" }}>Finance recommendation</h3>
        <div style={{ fontSize: 14, color: "#374151" }}>{b.finance_recommendation || "—"}</div>
        <h3 style={{ margin: "12px 0 6px 0" }}>Delivery recommendation</h3>
        <div style={{ fontSize: 14, color: "#374151" }}>{b.delivery_recommendation || "—"}</div>
      </section>

      {/* Rationale */}
      <section style={{ marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 6px 0" }}>Business rationale</h3>
        {rationaleEditable ? (
          <div>
            <label htmlFor="ceo-rationale" style={{ display: "block", fontSize: 13, color: "#374151" }}>
              Explain the business reason for exceeding the policy floor
            </label>
            <textarea
              id="ceo-rationale"
              data-testid="ceo-rationale-input"
              value={rationaleDraft}
              onChange={(e) => setRationaleDraft(e.target.value)}
              rows={5}
              style={{
                width: "100%",
                padding: 8,
                fontSize: 14,
                fontFamily: "inherit",
                borderRadius: 6,
                border: "1px solid #d1d5db",
              }}
            />
            <label style={{ display: "block", fontSize: 12, color: "#6b7280", marginTop: 6 }}>
              <input
                type="checkbox"
                checked={tidy}
                onChange={(e) => setTidy(e.target.checked)}
              />{" "}
              Tidy up my wording (AI cleans wording; your original words are stored verbatim)
            </label>
            <button
              type="button"
              onClick={saveRationale}
              disabled={savingRat || !rationaleDraft.trim()}
              style={{
                marginTop: 8,
                background: "#111827",
                color: "white",
                padding: "6px 12px",
                borderRadius: 6,
                border: 0,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {savingRat ? "Saving…" : "Save rationale"}
            </button>
          </div>
        ) : (
          <div
            data-testid="ceo-rationale-readonly"
            style={{ fontSize: 14, color: "#374151", whiteSpace: "pre-wrap" }}
          >
            {row.rationale_text || <em style={{ color: "#9ca3af" }}>Not yet written.</em>}
          </div>
        )}
        {row.rationale_tidied_text && row.rationale_tidied_text !== row.rationale_text ? (
          <div style={{ marginTop: 8, fontSize: 13, color: "#6b7280" }}>
            <strong>Tidied wording:</strong> {row.rationale_tidied_text}
          </div>
        ) : null}
      </section>

      {/* Decision */}
      {canDecide && row.decision === null ? (
        <section
          data-testid="ceo-decision-panel"
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: 16,
            marginTop: 16,
          }}
        >
          <h3 style={{ margin: "0 0 8px 0" }}>Decision</h3>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
            <div style={{ minWidth: 240, flex: 1 }}>
              <label htmlFor="ceo-conditions" style={{ display: "block", fontSize: 13 }}>
                Conditions (approve only)
              </label>
              <input
                id="ceo-conditions"
                value={conditions}
                onChange={(e) => setConditions(e.target.value)}
                style={{ width: "100%", padding: 6, borderRadius: 6, border: "1px solid #d1d5db" }}
              />
            </div>
            <div>
              <label htmlFor="ceo-valid-until" style={{ display: "block", fontSize: 13 }}>
                Valid until (approve only)
              </label>
              <input
                id="ceo-valid-until"
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
                style={{ padding: 6, borderRadius: 6, border: "1px solid #d1d5db" }}
              />
            </div>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={() => decide("approve")}
              disabled={savingDecision || !(row.rationale_text ?? "").trim()}
              style={{
                background: "#059669",
                color: "white",
                padding: "6px 14px",
                borderRadius: 6,
                border: 0,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => decide("return_for_changes")}
              disabled={savingDecision}
              style={{
                background: "#d97706",
                color: "white",
                padding: "6px 14px",
                borderRadius: 6,
                border: 0,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Return for changes
            </button>
            <button
              type="button"
              onClick={() => decide("reject")}
              disabled={savingDecision}
              style={{
                background: "#dc2626",
                color: "white",
                padding: "6px 14px",
                borderRadius: 6,
                border: 0,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Reject
            </button>
          </div>
          {!(row.rationale_text ?? "").trim() ? (
            <div style={{ marginTop: 8, fontSize: 12, color: "#9ca3af" }}>
              A saved rationale is required before you can approve.
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
