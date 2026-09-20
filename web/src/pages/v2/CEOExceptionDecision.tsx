/**
 * S9 — CEO exception decision page.
 *
 * Renders the `brief_json` that the SOW-first pipeline pre-drafts when
 * the auto-GM run predicts a below-floor package. Nothing is blank on
 * open. Rationale is the only field a human writes (CLAUDE.md rule 10,
 * sow-first §6). Every final decision requires a rationale
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
import { RecordHeader } from "../../ui-v2/RecordHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { cardStripeClass, type CardStripeVariant } from "../../ui-v2/CardStripe";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { Label } from "../../ui-v2/primitives/label";
import { cn } from "../../lib/cn";
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
  // walk away without stating why (sow-first §6).
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
              tone={brief.gm.us.passes ? "success" : "danger"}
              label={`US ${brief.gm.us.passes ? "passes" : "below floor"}`}
            />
            <StatusBadge
              tone={brief.gm.india.passes ? "success" : "danger"}
              label={`India ${brief.gm.india.passes ? "passes" : "below floor"}`}
            />
            {savedDecision ? (
              <StatusBadge tone="success" label={`Decision: ${savedDecision}`} />
            ) : (
              <StatusBadge tone="warning" label="Awaiting CEO · 2 days" />
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

      {/* Four metric cards; the fourth carries stripe-bad + bad-color value
       * per prototype line 473. */}
      <section
        aria-label="Top metrics"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <MetricCard
          label="Proposed revenue"
          value={proposedRevenue ?? "Unavailable"}
          hint="Fixed price · package terms"
        />
        <MetricCard
          label="Eligible delivery cost"
          value={eligibleCost ?? "Unavailable"}
          hint="HR-validated · rate card"
        />
        <MetricCard
          label="Gross profit · combined GM"
          value={expectedProfit ?? "Unavailable"}
          suffix={combinedGm ?? undefined}
          hint="Informational; components govern"
        />
        <MetricCard
          label="Price increase to reach policy"
          value={priceGap ?? "Unavailable"}
          hint="Or price shortfall at current price"
          stripe="blocked"
          valueTone="danger"
        />
      </section>

      <GeographyTable brief={brief} />
      <GeographyFloorBars brief={brief} />

      <div className="grid gap-6 twoColumnCollapse:grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)] items-start">
        <div className="space-y-4">
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

        <aside>
          <div
            className={cn(
              "sticky top-[80px] flex flex-col gap-[14px]",
              "rounded-card border border-border bg-surface p-5",
            )}
            aria-label="Decision"
            data-testid="ceo-decision-panel"
          >
            <div>
              <div className="text-[11px] uppercase tracking-[0.06em] font-semibold text-text-secondary">
                Decision
              </div>
              <div className="mt-1 text-body font-semibold text-text">
                CEO
              </div>
              <div className="mt-1 text-[12px] text-text-secondary">
                Approvable versions: SOW v{pkg?.sow_version_id.slice(-6) ?? "—"}
                {" · "}GM v{pkg?.gm_model_id.slice(-6) ?? "—"}.
              </div>
            </div>

            <ApprovablePackages brief={brief} />

            <div>
              <div className="text-[11px] uppercase tracking-[0.06em] font-semibold text-text-secondary mb-2">
                Conditions
              </div>
              <ConditionsEditor
                conditions={conditions}
                onChange={setConditions}
              />
            </div>

            <div>
              <Label htmlFor="valid-until">Approval valid until</Label>
              <Input
                id="valid-until"
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </div>

            <div>
              <div className="text-[11px] uppercase tracking-[0.06em] font-semibold text-text-secondary mb-2">
                Rationale (required)
              </div>
              <textarea
                id="rationale"
                data-testid="ceo-rationale-input"
                className={cn(
                  "w-full min-h-[72px] rounded-control border border-input-border",
                  "bg-surface px-[10px] py-2 text-body text-text",
                  "focus-visible:outline-focus resize-y",
                )}
                value={rationale}
                onChange={(e) => {
                  setRationale(e.target.value);
                  setRationaleSaved(false);
                }}
                placeholder="Why this exception is acceptable, in your words."
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="text-[12px] text-text-secondary">
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
            </div>

            <fieldset className="grid gap-2">
              <legend className="sr-only">Decision mode</legend>
              {(
                [
                  ["approve_conditions", "Approve with conditions", "primary" as const],
                  ["approve", "Approve exception", "secondary" as const],
                  ["request_changes", "Request changes", "secondary" as const],
                  ["decline", "Decline", "destructive" as const],
                ] as const
              ).map(([m, label]) => (
                <label
                  key={m}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-2",
                    "rounded-control border border-borderStrong bg-surface",
                    "px-[14px] h-9 text-body font-medium transition-motion",
                    m === "decline" && "text-danger",
                    mode === m && "border-primary bg-primary-subtle text-primaryText",
                    mode === m && m === "decline" && "border-danger bg-danger-surface text-danger",
                  )}
                >
                  <input
                    className="sr-only"
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
              <p className="text-[12px] text-text-secondary">
                {!rationaleReady
                  ? "A saved, full-sentence rationale is required before any decision."
                  : "Complete the conditions to enable submission."}
              </p>
            ) : null}

            <p className="text-[12px] text-text-muted">
              Every decision records your identity, time, versions and rationale.
              It cannot waive Legal or staffing requirements.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  suffix,
  stripe,
  valueTone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  suffix?: string;
  stripe?: CardStripeVariant;
  valueTone?: "default" | "danger";
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-card border border-border bg-surface p-5",
        cardStripeClass(stripe),
      )}
    >
      <span className="text-[12px] text-text-secondary">{label}</span>
      <span
        className={cn(
          "text-metric tnum",
          valueTone === "danger" ? "text-danger" : "text-text",
        )}
      >
        {value}
        {suffix ? (
          <span className="ml-2 text-[16px] font-medium text-text-secondary">
            {suffix}
          </span>
        ) : null}
      </span>
      {hint ? (
        <span className="text-[11px] text-text-muted">{hint}</span>
      ) : null}
    </div>
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
