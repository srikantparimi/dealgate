import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  getApprovalPackage,
  getCeoException,
  listCeoExceptions,
  patchCeoRationale,
  postCeoDecision,
  type ApprovalPackage,
  type CeoDecision,
  type CeoException,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { Metric } from "../../ui-v2/Metric";
import { RecordHeader } from "../../ui-v2/RecordHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { Label } from "../../ui-v2/primitives/label";
import { GeographyTable } from "./ceo-exception/GeographyTable";
import {
  ConditionsEditor,
  allConditionsComplete,
  type Condition,
} from "./ceo-exception/ConditionsEditor";
import {
  formatPercent,
  formatUsd,
  formatPpGap,
} from "./ceo-exception/format";

type DecisionMode = "approve" | "approve_conditions" | "request_changes" | "decline";

/**
 * CEO exception decision page (spec §14). Explains the project first,
 * then asks for a decision. Not a tab — dedicated route with its own
 * sticky action column.
 */
export function CEOExceptionDecisionPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();

  // We land on `/sows/:sowId/exception` — resolve the pending exception
  // for this SOW's approval package.
  const [exception, setException] = useState<CeoException | null>(null);
  const [pkg, setPkg] = useState<ApprovalPackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [degraded, setDegraded] = useState<string[]>([]);

  const [rationale, setRationale] = useState("");
  const [rationaleSaved, setRationaleSaved] = useState(false);
  const [mode, setMode] = useState<DecisionMode>("approve");
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [validUntil, setValidUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedDecision, setSavedDecision] = useState<CeoDecision | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    const degradedList: string[] = [];
    (async () => {
      try {
        const list = await listCeoExceptions("all");
        // The exception is keyed by package id; we cannot filter by SOW id
        // server-side today so pick the newest without a decision.
        const pending = list.items.find((e) => e.decision === null);
        if (!pending) {
          if (!cancelled) {
            setException(null);
            setLoading(false);
          }
          return;
        }
        const full = await getCeoException(pending.id);
        try {
          const p = await getApprovalPackage(full.package_id);
          if (!cancelled) setPkg(p);
        } catch (err) {
          if (err instanceof ApiError) degradedList.push("getApprovalPackage");
        }
        if (cancelled) return;
        setException(full);
        setRationale(full.rationale_text ?? "");
        setRationaleSaved(!!full.rationale_text);
        setSavedDecision(full.decision);
        setDegraded(degradedList);
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Could not load exception",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const brief = exception?.brief_json ?? null;

  const proposedRevenue = useMemo(
    () =>
      formatUsd(brief?.revenue.blended ?? null) ??
      formatUsd(
        brief
          ? String(
              (Number(brief.revenue.us ?? 0) +
                Number(brief.revenue.india ?? 0)) as number,
            )
          : null,
      ),
    [brief],
  );
  const eligibleCost = useMemo(
    () =>
      formatUsd(brief?.cost.blended ?? null) ??
      formatUsd(
        brief
          ? String(
              (Number(brief.cost.us ?? 0) +
                Number(brief.cost.india ?? 0)) as number,
            )
          : null,
      ),
    [brief],
  );
  const combinedGm = useMemo(
    () => formatPercent(brief?.gm.blended.value ?? null),
    [brief],
  );
  const priceGap = useMemo(() => {
    if (!brief) return null;
    const usGap = formatPpGap(brief.gm.us.value, brief.gm.us.floor);
    const inGap = formatPpGap(brief.gm.india.value, brief.gm.india.floor);
    if (usGap && inGap) return `${usGap} / ${inGap}`;
    return usGap ?? inGap ?? null;
  }, [brief]);

  const saveRationale = async () => {
    if (!exception) return;
    setSaveError(null);
    setBusy(true);
    try {
      const updated = await patchCeoRationale(exception.id, {
        rationale_text: rationale,
      });
      setException(updated);
      setRationaleSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const conditionsReady = allConditionsComplete(conditions);
  const requiresRationale = mode !== "request_changes";
  const canSubmit =
    !!exception &&
    !busy &&
    (requiresRationale ? rationaleSaved && rationale.trim().length > 0 : true) &&
    (mode !== "approve_conditions" || conditionsReady) &&
    (mode !== "decline" || rationale.trim().length > 0);

  const submit = async () => {
    if (!exception) return;
    setBusy(true);
    setSaveError(null);
    try {
      const decision: CeoDecision =
        mode === "decline"
          ? "reject"
          : mode === "request_changes"
            ? "return_for_changes"
            : "approve";
      const conditionsText =
        mode === "approve_conditions"
          ? conditions
              .map(
                (c) =>
                  `${c.text} — owner: ${c.owner}, due: ${c.due}, evidence: ${c.evidence}`,
              )
              .join("\n")
          : null;
      const updated = await postCeoDecision(exception.id, {
        decision,
        conditions_text: conditionsText,
        valid_until: validUntil || null,
      });
      setException(updated);
      setSavedDecision(updated.decision);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  };

  if (!id) {
    return <EmptyState title="Missing SOW id" />;
  }

  if (loading) {
    return (
      <p className="p-6 text-body text-text-secondary">
        Loading exception brief…
      </p>
    );
  }

  if (loadError) {
    return (
      <ErrorState
        title="Could not load CEO exception"
        description={loadError}
        onRetry={() => nav(0)}
      />
    );
  }

  if (!exception || !brief) {
    return (
      <EmptyState
        title="No pending CEO exception"
        description="This SOW does not have a pending margin exception. If you expected one, the request may have been decided or voided."
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() => nav(`/sows/${id}`)}
          >
            Back to workspace
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <RecordHeader
        eyebrow={brief.client.name}
        title="CEO margin exception"
        identity={
          <>
            <span>Exception ID {exception.id.slice(-8)}</span>
            <span>Package {exception.package_id.slice(-8)}</span>
            {pkg ? (
              <>
                <span data-testid="sow-version">
                  SOW v {pkg.sow_version_id.slice(-8)}
                </span>
                <span data-testid="gm-version">
                  GM v {pkg.gm_model_id.slice(-8)}
                </span>
                <span>
                  Policy v {pkg.policy_version_id?.slice(-8) ?? "—"}
                </span>
              </>
            ) : (
              <span className="text-warning">
                Package version unavailable
              </span>
            )}
          </>
        }
        status={
          <>
            <StatusBadge
              tone={brief.gm.us.passes ? "ok" : "danger"}
              label={`US ${brief.gm.us.passes ? "passes" : "below floor"}`}
            />
            <StatusBadge
              tone={brief.gm.india.passes ? "ok" : "danger"}
              label={`India ${brief.gm.india.passes ? "passes" : "below floor"}`}
            />
            {savedDecision ? (
              <StatusBadge tone="ok" label={`Decision: ${savedDecision}`} />
            ) : (
              <StatusBadge tone="warn" label="Awaiting decision" />
            )}
          </>
        }
      />

      {degraded.length > 0 ? (
        <p className="text-secondary text-warning">
          Degraded: {degraded.join(", ")}
        </p>
      ) : null}

      <section
        aria-label="Top metrics"
        className="grid gap-3 sm:grid-cols-4"
      >
        <Metric label="Proposed revenue" value={proposedRevenue ?? "Unavailable"} />
        <Metric label="Eligible cost" value={eligibleCost ?? "Unavailable"} />
        <Metric label="Combined GM" value={combinedGm ?? "Unavailable"} />
        <Metric label="Price gap to policy" value={priceGap ?? "Unavailable"} />
      </section>

      <GeographyTable brief={brief} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4" style={{ maxWidth: "960px" }}>
          <TextSection title="Project outcome & scope" body={brief.scope} />
          <TextSection
            title="Why the exception"
            body={brief.finance_recommendation}
          />
          <TextSection
            title="Business rationale"
            body={rationale || "No rationale saved yet."}
          />
          <TextSection
            title="Client constraints & future value"
            body={brief.client.context}
          />
          <BulletSection
            title="Alternatives considered"
            items={brief.alternatives}
          />
          <TextSection
            title="Delivery feasibility"
            body={brief.delivery_recommendation}
          />
          <TextSection
            title="Downside sensitivity & recovery"
            body={
              brief.gross_profit_shortfall_usd
                ? `Gross profit shortfall vs floor: ${formatUsd(brief.gross_profit_shortfall_usd)}.`
                : "No shortfall figure supplied."
            }
          />
          <BulletSection
            title="Evidence links"
            items={brief.sources.map((s, i) => String((s as { title?: string }).title ?? `Source ${i + 1}`))}
          />
        </div>

        <aside className="lg:col-span-1">
          <div className="sticky top-6 space-y-4">
            <section
              aria-label="Rationale"
              className="rounded-panel border border-divider bg-surface p-4"
            >
              <h2 className="text-section text-text mb-3">Rationale</h2>
              <Label htmlFor="rationale">Business rationale</Label>
              <textarea
                id="rationale"
                data-testid="ceo-rationale-input"
                className="mt-1 w-full min-h-[8rem] rounded-control border border-input-border bg-surface p-2 text-body text-text focus-visible:outline-focus"
                value={rationale}
                onChange={(e) => {
                  setRationale(e.target.value);
                  setRationaleSaved(false);
                }}
                placeholder="Why this exception is warranted."
              />
              <div className="mt-3 flex items-center justify-between gap-2">
                <p className="text-secondary text-text-secondary">
                  {rationaleSaved
                    ? "Rationale saved."
                    : "Save the rationale before approving."}
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={busy || rationale.trim() === ""}
                  onClick={saveRationale}
                >
                  Save rationale
                </Button>
              </div>
            </section>

            <section
              aria-label="Decision"
              data-testid="ceo-decision-panel"
              className="rounded-panel border border-divider bg-surface p-4 space-y-3"
            >
              <h2 className="text-section text-text">Decision</h2>
              <fieldset className="space-y-2">
                <legend className="text-secondary text-text-secondary uppercase">
                  Choose action
                </legend>
                {(
                  [
                    ["approve", "Approve exception"],
                    ["approve_conditions", "Approve with conditions"],
                    ["request_changes", "Request changes"],
                    ["decline", "Decline"],
                  ] as const
                ).map(([m, label]) => (
                  <label
                    key={m}
                    className="flex items-center gap-2 text-body text-text"
                  >
                    <input
                      type="radio"
                      name="decision-mode"
                      value={m}
                      checked={mode === m}
                      onChange={() => setMode(m)}
                    />
                    {label}
                  </label>
                ))}
              </fieldset>

              {mode === "approve_conditions" ? (
                <div className="space-y-2">
                  <Label>Conditions</Label>
                  <ConditionsEditor
                    conditions={conditions}
                    onChange={setConditions}
                  />
                </div>
              ) : null}

              <div>
                <Label htmlFor="valid-until">Approval valid until</Label>
                <Input
                  id="valid-until"
                  type="date"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                />
              </div>

              {saveError ? (
                <p className="text-secondary text-danger">{saveError}</p>
              ) : null}

              <Button
                type="button"
                data-testid="ceo-decision-submit"
                disabled={!canSubmit}
                onClick={submit}
                variant={mode === "decline" ? "destructive" : "primary"}
                title={
                  !canSubmit
                    ? mode === "decline"
                      ? "A decline reason is required."
                      : mode === "approve_conditions" && !conditionsReady
                        ? "Every condition needs an owner and due date."
                        : "Save a rationale before approving."
                    : undefined
                }
              >
                {mode === "decline"
                  ? "Record decline"
                  : mode === "request_changes"
                    ? "Send back for changes"
                    : mode === "approve_conditions"
                      ? "Approve with conditions"
                      : "Approve exception"}
              </Button>
              {!canSubmit && mode === "approve" ? (
                <p className="text-secondary text-text-secondary">
                  A saved rationale is required before you can approve.
                </p>
              ) : null}
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}

function TextSection({ title, body }: { title: string; body: string }) {
  return (
    <section
      aria-label={title}
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-2">{title}</h2>
      <p className="text-body text-text whitespace-pre-line">{body}</p>
    </section>
  );
}

function BulletSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section
      aria-label={title}
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-2">{title}</h2>
      {items.length === 0 ? (
        <p className="text-body text-text-secondary">None listed.</p>
      ) : (
        <ul className="list-disc pl-5 space-y-1 text-body text-text">
          {items.map((it, idx) => (
            <li key={idx}>{it}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
