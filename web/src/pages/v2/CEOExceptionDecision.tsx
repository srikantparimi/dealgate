/**
 * S9 — CEO exception decision page.
 *
 * Renders the `brief_json` that the SOW-first pipeline pre-drafts when
 * the auto-GM run predicts a below-floor package. Nothing is blank on
 * open. Rationale is the only field a human writes (CLAUDE.md rule 10,
 * sow-first-principles §6). Every final decision requires a rationale
 * of at least one sentence; conditional approval also requires every
 * condition to carry owner + due + evidence + blocking scope.
 *
 * Never re-computes GM. The floor bars, gap chips and geography table
 * display Decimal strings the server already computed.
 */
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
import { GeographyFloorBars } from "./ceo-exception/GeographyFloorBars";
import { GeographyTable } from "./ceo-exception/GeographyTable";
import { PackageGates } from "./ceo-exception/PackageGates";
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

type DecisionMode =
  | "approve"
  | "approve_conditions"
  | "request_changes"
  | "decline";

/** Very light "is this at least one sentence" gate: >= 12 non-space chars
 *  and ending in `.`, `!`, `?` or `…`. Keeps the assertion in one place. */
export function isSentence(text: string): boolean {
  const t = text.trim();
  if (t.replace(/\s/g, "").length < 12) return false;
  return /[.!?…]\s*$/.test(t);
}

export function CEOExceptionDecisionPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();

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
  const expectedProfit = useMemo(() => {
    if (!brief) return null;
    const rev =
      brief.revenue.blended != null
        ? Number(brief.revenue.blended)
        : Number(brief.revenue.us ?? 0) + Number(brief.revenue.india ?? 0);
    const cost =
      brief.cost.blended != null
        ? Number(brief.cost.blended)
        : Number(brief.cost.us ?? 0) + Number(brief.cost.india ?? 0);
    const p = rev - cost;
    return Number.isFinite(p) ? formatUsd(String(p)) : null;
  }, [brief]);
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
  // Rationale required for *every* final decision — the CEO cannot
  // walk away without stating why (sow-first-principles §6).
  const rationaleReady = isSentence(rationale) && rationaleSaved;
  const canSubmit =
    !!exception &&
    !busy &&
    rationaleReady &&
    (mode !== "approve_conditions" || conditionsReady);

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
                  `${c.text} — owner: ${c.owner}, due: ${c.due}, evidence: ${c.evidence}, blocks: ${blockingSummary(c)}`,
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

      <PackageGates pkg={pkg} exception={exception} />

      {degraded.length > 0 ? (
        <p className="text-secondary text-warning">
          Degraded: {degraded.join(", ")}
        </p>
      ) : null}

      <section
        aria-label="Top metrics"
        className="grid gap-3 sm:grid-cols-5"
      >
        <Metric label="Proposed revenue" value={proposedRevenue ?? "Unavailable"} />
        <Metric label="Eligible cost" value={eligibleCost ?? "Unavailable"} />
        <Metric label="Expected profit" value={expectedProfit ?? "Unavailable"} />
        <Metric label="Combined GM" value={combinedGm ?? "Unavailable"} />
        <Metric label="Price gap" value={priceGap ?? "Unavailable"} />
      </section>

      <GeographyFloorBars brief={brief} />
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
          <TextSection
            title="Contracted vs speculative future value"
            body={
              brief.team_summary ||
              "Not summarised. Contracted revenue is the base rate; speculative future value is not credited."
            }
          />
          <BulletSection
            title="Alternatives considered"
            items={brief.alternatives}
          />
          <TextSection
            title="Delivery feasibility (Delivery / HR)"
            body={brief.delivery_recommendation}
          />
          <TextSection
            title="Finance & Legal recommendation"
            body={brief.finance_recommendation}
          />
          <TextSection
            title="Downside sensitivity & recovery"
            body={
              brief.gross_profit_shortfall_usd
                ? `Gross profit shortfall vs floor: ${formatUsd(brief.gross_profit_shortfall_usd)}. Owner: engagement account team. Trigger: monthly forecast review.`
                : "No shortfall figure supplied."
            }
          />
          <BulletSection
            title="Evidence links"
            items={brief.sources.map((s, i) =>
              String(
                (s as { title?: string }).title ?? `Source ${i + 1}`,
              ),
            )}
          />
        </div>

        <aside className="lg:col-span-1">
          <div className="sticky top-6 space-y-4">
            <DecisionState savedDecision={savedDecision} />

            <ApprovablePackages brief={brief} />

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
                placeholder="Why this exception is warranted. Full sentence, ending in a period."
              />
              <div className="mt-3 flex items-center justify-between gap-2">
                <p className="text-secondary text-text-secondary">
                  {rationaleSaved
                    ? "Rationale saved."
                    : isSentence(rationale)
                      ? "Save the rationale before recording a decision."
                      : "Rationale must be at least one full sentence."}
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={busy || !isSentence(rationale)}
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
              <h2 className="text-section text-text">Decision actions</h2>
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
                    ? !rationaleReady
                      ? "Save a full-sentence rationale before recording a decision."
                      : mode === "approve_conditions" && !conditionsReady
                        ? "Every condition needs an owner, due date and evidence."
                        : undefined
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
              {!canSubmit ? (
                <p className="text-secondary text-text-secondary">
                  {!rationaleReady
                    ? "A saved, full-sentence rationale is required before any decision."
                    : "Complete the conditions to enable submission."}
                </p>
              ) : null}
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}

function DecisionState({
  savedDecision,
}: {
  savedDecision: CeoDecision | null;
}) {
  return (
    <section
      aria-label="Decision state"
      className="rounded-panel border border-divider bg-surface p-4"
      data-testid="decision-state"
    >
      <h2 className="text-section text-text mb-2">Decision state</h2>
      {savedDecision ? (
        <StatusBadge tone="ok" label={`Recorded: ${savedDecision}`} />
      ) : (
        <StatusBadge tone="warning" label="Awaiting your decision" />
      )}
    </section>
  );
}

function ApprovablePackages({
  brief,
}: {
  brief: { price_uplift: { us: string | null; india: string | null } };
}) {
  const rows: Array<{ label: string; value: string | null }> = [
    { label: "US uplift to reach floor", value: brief.price_uplift.us },
    { label: "India uplift to reach floor", value: brief.price_uplift.india },
  ];
  return (
    <section
      aria-label="Approvable package versions"
      className="rounded-panel border border-divider bg-surface p-4"
      data-testid="approvable-packages"
    >
      <h2 className="text-section text-text mb-2">
        Approvable package versions
      </h2>
      <p className="text-secondary text-text-secondary mb-2">
        Minimum price uplifts required to remove the exception:
      </p>
      <dl className="grid grid-cols-2 gap-2 text-secondary">
        {rows.map((r) => (
          <div key={r.label} className="rounded-control border border-divider p-2">
            <dt className="text-text-secondary uppercase">{r.label}</dt>
            <dd className="tnum text-text">
              {r.value != null ? formatUsd(r.value) : "—"}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function blockingSummary(c: Condition): string {
  const parts: string[] = [];
  if (c.blocksSignature) parts.push("signature");
  if (c.blocksDelivery) parts.push("delivery");
  if (c.blocksMilestones) parts.push("milestones");
  return parts.length ? parts.join(" + ") : "none";
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
