/**
 * S22 redesign · Staffing & GM tab content, organized as four local
 * sections over ONE persisted draft (never a wizard):
 *   1 Contract & pricing · 2 Team & calendars ·
 *   3 Monthly plan & expenses · 4 Review & save
 * A Scope needs / Budget supports / Currently planned summary leads the
 * page; a green margin cannot hide an understaffed plan. All seven
 * registered pricing models keep their model-specific editors. Money
 * stays server-side Decimal — this file only formats and compares for
 * display. The single readiness panel lives in the workspace shell.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Calculator, Plus, Save, Trash2 } from "lucide-react";
import {
  getMe,
  getTermAssist,
  type SowFieldName,
  type TermAssist,
  type UUID,
} from "../../../api/client";
import {
  getCommercialProfiles,
  previewCommercial,
  saveCommercialVersion,
  type CommercialComponent,
  type CommercialPreview,
  type CommercialSchedule,
  getCommercialProposal,
  type CommercialProposal,
  type StaffingAdvice,
} from "../../../api/commercial";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import type { WorkspaceSnapshot } from "./readiness";
import { formatPercent, fractionToPercent } from "./format";
import {
  emptyPricing,
  MonthlyAllocations,
  PricingFields,
  PROFILE_LABELS,
} from "./commercial-editor/PricingFields";
import { CalendarFields } from "./commercial-editor/CalendarFields";
import { HybridFields } from "./commercial-editor/HybridFields";
import { bindCommercialSource } from "./commercial-editor/bindings";
import { PlanTeamPanel, type ResolutionAction } from "./commercial-editor/PlanTeamPanel";

function initialInputs(snap: WorkspaceSnapshot): CommercialComponent {
  if (snap.gmModel?.commercial_inputs)
    return structuredClone(snap.gmModel.commercial_inputs);
  const confirmed = (name: SowFieldName) => {
    const field = snap.sow?.extracted_fields?.[name];
    return field?.status === "confirmed" && typeof field.value === "string"
      ? field.value
      : null;
  };
  const price = confirmed("price");
  return {
    component_id: crypto.randomUUID(),
    version: "1",
    source_id: snap.sow?.sow_id ?? "",
    source_version: snap.sow?.id ?? "",
    workstream_id: "",
    profile: "fixed_assignment",
    profile_version: "1",
    policy_version: "",
    source_evidence: Object.entries(snap.sow?.extracted_fields ?? {})
      .filter(([, field]) => field?.status === "confirmed")
      .map(
        ([name, field]) =>
          `SOW ${snap.sow?.id}, ${name}, page ${field?.page_ref}`,
      ),
    service_start: /^\d{4}-\d{2}-\d{2}$/.test(confirmed("term_start") ?? "")
      ? confirmed("term_start")
      : null,
    service_end: /^\d{4}-\d{2}-\d{2}$/.test(confirmed("term_end") ?? "")
      ? confirmed("term_end")
      : null,
    timezone: null,
    currency: confirmed("currency"),
    billing_cadence: null,
    cost_basis: null,
    costs_confirmed: false,
    costs: [],
    staffing: [],
    pricing: {
      total_fee: price && /^\d+(\.\d+)?$/.test(price) ? price : null,
      allocations: [],
      allocation_basis: null,
      minor_unit: "",
    },
  };
}

/**
 * In-memory draft cache so an unsaved draft survives SOW-tab navigation
 * and section movement within this session (directive §6). Deliberately
 * NOT browser storage: SOW financials stay out of localStorage. A full
 * page reload still loses unsaved edits — a listed, known gap.
 */
const draftCache = new Map<
  string,
  { inputs: CommercialComponent; reason: string; dirty: boolean }
>();

/** Test isolation hook: drafts must not leak between test renders. */
export function resetCommercialDraftCache() {
  draftCache.clear();
}

const SECTIONS = [
  { id: "contract", label: "1 · Contract & pricing" },
  { id: "team", label: "2 · Team & calendars" },
  { id: "monthly", label: "3 · Monthly plan & expenses" },
  { id: "review", label: "4 · Review & save" },
] as const;

export function CommercialModelEditor({ snap }: { snap: WorkspaceSnapshot }) {
  const draftKey = `${snap.sow?.id ?? "none"}:${snap.gmModel?.id ?? "new"}`;
  const cached = draftCache.get(draftKey);
  const [inputs, setInputs] = useState(() =>
    cached?.dirty ? cached.inputs : initialInputs(snap),
  );
  const [modelId, setModelId] = useState(snap.gmModel?.id ?? null);
  const [result, setResult] = useState<CommercialPreview>({
    computed: snap.gmModel?.computed,
    commercial_snapshot: snap.gmModel?.commercial_snapshot ?? undefined,
  });
  const [canWrite, setCanWrite] = useState(false);
  const [policy, setPolicy] = useState("");
  const [floors, setFloors] = useState<{ us: string; india: string } | null>(null);
  const [reason, setReason] = useState(cached?.dirty ? cached.reason : "");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(cached?.dirty ?? false);
  const [proposal, setProposal] = useState<CommercialProposal | null>(null);
  const [advice, setAdvice] = useState<StaffingAdvice | null>(null);
  const [resolution, setResolution] = useState<ResolutionAction | null>(null);
  const [termAssist, setTermAssist] = useState<TermAssist | null>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  // S22 click-through fix: when the SOW states a duration but the
  // contract dates are unknown, surface the server-derived end date as
  // a labeled suggestion (applied by click, never silently).
  useEffect(() => {
    if (!snap.sow?.id || inputs.service_end) {
      setTermAssist(null);
      return;
    }
    let active = true;
    getTermAssist(snap.sow.id as UUID, inputs.service_start)
      .then((result) => {
        if (active) setTermAssist(result.available ? result : null);
      })
      .catch(() => {
        /* best-effort assist */
      });
    return () => {
      active = false;
    };
  }, [snap.sow?.id, inputs.service_start, inputs.service_end]);

  // Draft survives tab navigation: every change lands in the cache.
  useEffect(() => {
    draftCache.set(draftKey, { inputs, reason, dirty });
  }, [draftKey, inputs, reason, dirty]);

  // S22 · pre-fill from the SOW + auto-staffing proposal when nothing is
  // saved yet and the human has not started typing. Every value stays
  // editable; the machine never confirms costs.
  useEffect(() => {
    if (snap.gmModel?.commercial_inputs || !snap.deal) return;
    if (draftCache.get(draftKey)?.dirty) return;
    let active = true;
    getCommercialProposal(snap.deal.id)
      .then((p) => {
        if (!active) return;
        setProposal(p);
      })
      .catch(() => {
        /* read-only roles or signed basis: the empty editor stands */
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap.deal?.id]);
  useEffect(() => {
    if (!proposal || dirty || snap.gmModel?.commercial_inputs) return;
    setInputs(structuredClone(proposal.component));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal]);
  const [calculationState, setCalculationState] = useState<
    "saved" | "preview" | "stale_preview"
  >("saved");
  useEffect(() => {
    let active = true;
    getMe()
      .then((me) => {
        if (active)
          setCanWrite(
            me.groups.some((g) => ["Delivery", "SystemAdmin"].includes(g)),
          );
      })
      .catch(() => {
        if (active) setCanWrite(false);
      });
    getCommercialProfiles()
      .then((registry) => {
        if (!active) return;
        setPolicy(registry.policy.version);
        setFloors({
          us: registry.policy.us_floor,
          india: registry.policy.india_floor,
        });
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Commercial policy unavailable",
          );
      });
    return () => {
      active = false;
    };
  }, []);
  const [pendingProfile, setPendingProfile] = useState<string | null>(null);
  const supported = Object.prototype.hasOwnProperty.call(
    PROFILE_LABELS,
    inputs.profile,
  );
  const rawRestricted =
    !!snap.gmModel?.commercial_profile && !snap.gmModel.commercial_inputs;
  const signedBasis =
    snap.approvalPackage?.sow_version_id === snap.sow?.id &&
    (snap.approvalPackage?.status === "released" ||
      snap.signedSow?.verify_status === "verified");
  const editable = canWrite && supported && !rawRestricted && !signedBasis;
  const pricing = inputs.pricing ?? {};
  const replaceComponent = (next: CommercialComponent) => {
    setInputs(next);
    setNotice("");
    setDirty(true);
    setCalculationState((state) =>
      state === "saved" ? state : "stale_preview",
    );
  };
  const patch = (key: keyof CommercialComponent, value: unknown) => {
    setInputs((p) => ({ ...p, [key]: value }));
    setNotice("");
    setDirty(true);
    setCalculationState((state) =>
      state === "saved" ? state : "stale_preview",
    );
  };
  async function calculate(save: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const body = bindCommercialSource(inputs, {
        policy_version: policy,
        source_id: snap.sow!.sow_id,
        source_version: snap.sow!.id,
      });
      if (save) {
        const response = await saveCommercialVersion(snap.deal!.id, {
          sow_version_id: snap.sow!.id,
          expected_gm_model_id: modelId,
          inputs: body,
          change_reason: reason,
        });
        setModelId(response.gm_model.id);
        setInputs(response.gm_model.commercial_inputs ?? body);
        setResult({
          computed: response.gm_model.computed,
          commercial_snapshot:
            response.gm_model.commercial_snapshot ?? undefined,
        });
        setNotice("Commercial version saved.");
        setDirty(false);
        draftCache.delete(draftKey);
        setCalculationState("saved");
      } else {
        setResult(await previewCommercial(body));
        setCalculationState("preview");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Commercial request failed");
    } finally {
      setBusy(false);
    }
  }
  // S22 click-through fix ("GM is not calculated"): preview runs by
  // itself, debounced, whenever the draft has enough to compute — the
  // server's Decimal engine does the math and the result is labeled
  // provisional. Saving (the human attestation) stays a manual action.
  const lastAutoPreview = useRef("");
  useEffect(() => {
    if (!editable || !policy || !snap.sow || busy) return;
    const computable =
      !!inputs.service_start &&
      !!inputs.service_end &&
      (!!inputs.pricing?.total_fee || inputs.staffing.length > 0);
    if (!computable) return;
    const body = JSON.stringify(inputs);
    if (body === lastAutoPreview.current) return;
    const timer = setTimeout(() => {
      lastAutoPreview.current = body;
      void calculate(false);
    }, 1200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs, editable, policy, busy]);

  function field(label: string, key: keyof CommercialComponent, type = "text") {
    return (
      <label className="space-y-1 text-secondary">
        {label}
        <Input
          type={type}
          placeholder="Unconfirmed"
          value={String(inputs[key] ?? "")}
          onChange={(e) => patch(key, e.target.value || null)}
        />
      </label>
    );
  }
  const goTo = (id: string) => {
    sectionRefs.current[id]?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };
  const handleResolve = (action: ResolutionAction) => {
    setResolution(action);
    if (action === "fee" || action === "term") goTo("contract");
  };

  // Display-only effort totals for the summary strip (people × allocation).
  const plannedPeople = inputs.staffing.reduce((sum, row) => sum + (row.quantity || 0), 0);
  const plannedFteRaw = inputs.staffing.reduce(
    (sum, row) => sum + (row.quantity || 0) * (Number(row.allocation) || 0),
    0,
  );
  const plannedFte = Math.round(plannedFteRaw * 100) / 100;
  const scopeNeeds = advice?.estimate?.required_fte ?? null;
  const budgetSupports =
    advice && advice.affordability === "calculated" ? advice.max_fte_at_target : null;
  const understaffed =
    scopeNeeds !== null &&
    Number.isFinite(Number(scopeNeeds)) &&
    plannedFte < Number(scopeNeeds);

  const sectionStatus: Record<string, string> = {
    contract: pricing.total_fee
      ? `${PROFILE_LABELS[inputs.profile] ?? inputs.profile} · fee ${inputs.currency ?? ""} ${pricing.total_fee}`
      : `${PROFILE_LABELS[inputs.profile] ?? inputs.profile}`,
    team:
      inputs.staffing.length > 0
        ? `${inputs.staffing.length} role${inputs.staffing.length === 1 ? "" : "s"} · ${plannedFte} FTE`
        : "No roles yet",
    monthly:
      (pricing.allocations?.length ?? 0) + inputs.costs.length > 0
        ? `${pricing.allocations?.length ?? 0} allocations · ${inputs.costs.length} expenses`
        : "Nothing planned yet",
    review: dirty ? "Unsaved draft" : "Saved",
  };

  const sectionShell = (
    id: (typeof SECTIONS)[number]["id"],
    children: ReactNode,
  ) => (
    <section
      key={id}
      id={`sgm-${id}`}
      ref={(el) => {
        sectionRefs.current[id] = el;
      }}
      aria-label={SECTIONS.find((s) => s.id === id)!.label}
      data-testid={`sgm-section-${id}`}
      className="rounded-panel border border-divider bg-surface p-4 space-y-4 scroll-mt-24"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-section text-text">
          {SECTIONS.find((s) => s.id === id)!.label}
        </h3>
        <span className="text-secondary text-text-secondary">
          {sectionStatus[id]}
        </span>
      </header>
      {children}
    </section>
  );

  return (
    <section className="min-w-0 space-y-4" aria-label="Staffing & GM plan">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-section">Staffing & GM</h2>
        <span className="flex items-center gap-2 text-secondary">
          <span data-testid="draft-state">{dirty ? "Unsaved draft" : "Saved"}</span>
          <span>{snap.gmModel?.commercial_profile ?? inputs.profile}</span>
        </span>
      </header>
      {error && (
        <p role="alert" data-testid="commercial-error" className="text-danger">
          {error}
        </p>
      )}

      {/* Scope needs / Budget supports / Currently planned — one summary
          above the four sections. Unknown stays Unknown, never zero. */}
      <div
        data-testid="sgm-summary"
        className="rounded-panel border border-divider bg-surface p-4"
      >
        <dl className="grid gap-3 sm:grid-cols-3 text-body">
          <div>
            <dt className="text-secondary text-text-secondary">Scope needs</dt>
            <dd className="text-text" data-testid="summary-scope">
              {scopeNeeds !== null
                ? `${scopeNeeds} FTE${advice?.estimate?.duration_weeks ? ` over ${advice.estimate.duration_weeks} weeks` : ""} (AI draft)`
                : "Unknown — no scope estimate yet"}
            </dd>
          </div>
          <div>
            <dt className="text-secondary text-text-secondary">Budget supports</dt>
            <dd className="text-text" data-testid="summary-budget">
              {budgetSupports !== null
                ? `up to ${budgetSupports} FTE at the ${fractionToPercent(advice!.inputs.target_gm)}% target`
                : "Unknown — fee, duration or rates missing"}
            </dd>
          </div>
          <div>
            <dt className="text-secondary text-text-secondary">Currently planned</dt>
            <dd className="text-text" data-testid="summary-planned">
              {inputs.staffing.length > 0
                ? `${plannedPeople} ${plannedPeople === 1 ? "person" : "people"} · ${plannedFte} FTE`
                : "No team planned yet"}
            </dd>
          </div>
        </dl>
        {understaffed && (
          <p role="alert" data-testid="summary-understaffed" className="mt-2 text-danger">
            The planned team covers {plannedFte} of the ~{scopeNeeds} FTE the
            scope needs. A passing margin does not make this plan
            delivery-ready — close the staffing gap or change the scope, fee
            or term.
          </p>
        )}
      </div>

      {/* Section navigation: free movement, status labels, no wizard. */}
      <nav aria-label="Plan sections" className="flex flex-wrap gap-2">
        {SECTIONS.map((section) => (
          <Button
            key={section.id}
            type="button"
            variant="secondary"
            onClick={() => goTo(section.id)}
          >
            {section.label}
          </Button>
        ))}
      </nav>

      {notice && <p role="status">{notice}</p>}
      {resolution && (
        <div
          role="note"
          data-testid="resolution-note"
          className="rounded-panel border border-primary/40 bg-primary-subtle/30 p-3 text-secondary space-y-1"
        >
          {resolution === "fee" && (
            <p className="text-text">
              Increase the fee: edit the contract fee in Contract & pricing
              below, then re-run the suggestion. A fee change on a submitted
              basis follows the existing material-change and re-approval rules.
            </p>
          )}
          {resolution === "term" && (
            <p className="text-text">
              Change the term: adjust the contract dates in Contract & pricing.
              Role dates default from them; rows you overrode keep their own
              dates — review them after the change.
            </p>
          )}
          {resolution === "scope" && (
            <p className="text-text">
              Reduce the scope: scope lives on the SOW itself. Agree the change
              with the client, upload the revised SOW in the Documents tab, and
              confirm it in the Scope tab — the estimate can then be
              regenerated against the new scope. The original demand stays
              traceable to the prior SOW version.
            </p>
          )}
          {resolution === "exception" && (
            <p className="text-text">
              Request a GM exception: save this version and submit for
              approval — when the margin is below the policy floor the
              existing workflow adds the CEO exception step with its required
              evidence. An exception approves the financial deviation only; it
              does not cure missing staff, skills or coverage.
            </p>
          )}
          <button type="button" className="underline" onClick={() => setResolution(null)}>
            Dismiss
          </button>
        </div>
      )}
      {proposal && !snap.gmModel?.commercial_inputs && (
        <div
          role="note"
          data-testid="commercial-proposal-banner"
          className="rounded-panel border border-primary/40 bg-primary-subtle/30 p-3 text-secondary"
        >
          <p className="text-text">
            Proposed from the SOW and auto-staffing — every value below is
            editable; nothing is confirmed until you save.
          </p>
          {proposal.warnings.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-text-secondary">
              {proposal.warnings.map((w, i) => (
                <li key={i} data-testid="proposal-warning">{w}</li>
              ))}
            </ul>
          )}
          {dirty && (
            <button
              type="button"
              data-testid="proposal-reset"
              className="mt-2 underline"
              onClick={() => {
                setInputs(structuredClone(proposal.component));
                setDirty(false);
              }}
            >
              Reset to proposal
            </button>
          )}
        </div>
      )}
      {signedBasis && (
        <p role="status">
          Signed financial basis. Changes require a separate amendment version.
        </p>
      )}
      {rawRestricted ? (
        <p>Commercial cost details are restricted.</p>
      ) : supported ? (
        <>
          <fieldset disabled={!editable || busy} className="min-w-0 space-y-4">
            {sectionShell(
              "contract",
              <>
                <label className="block text-secondary">
                  Engagement pricing model
                  <select
                    aria-label="Pricing profile"
                    className="mt-1 h-10 w-full rounded-md border border-divider bg-surface px-3"
                    value={inputs.profile}
                    onChange={(e) => setPendingProfile(e.target.value)}
                  >
                    {Object.entries(PROFILE_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                {pendingProfile && (
                  <section
                    aria-label="Confirm pricing model change"
                    className="space-y-3 border-l-4 border-warning p-3"
                  >
                    <p>
                      Replace {PROFILE_LABELS[inputs.profile]} pricing terms with{" "}
                      {PROFILE_LABELS[pendingProfile]}? Existing pricing rows will
                      be removed from this draft. Source evidence, service dates,
                      staffing and period costs are retained.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => setPendingProfile(null)}
                      >
                        Keep current model
                      </Button>
                      <Button
                        onClick={() => {
                          setInputs((previous) => ({
                            ...previous,
                            profile: pendingProfile,
                            pricing: emptyPricing(pendingProfile),
                          }));
                          setPendingProfile(null);
                          setDirty(true);
                          setCalculationState((state) =>
                            state === "saved" ? state : "stale_preview",
                          );
                          setNotice("");
                        }}
                      >
                        Replace pricing terms
                      </Button>
                    </div>
                  </section>
                )}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {field("Workstream", "workstream_id")}
                  {field("Contract start", "service_start", "date")}
                  {field("Contract end", "service_end", "date")}
                  {field("Contract timezone", "timezone")}
                  {field("Contract currency", "currency")}
                  {field("Billing schedule", "billing_cadence")}
                </div>
                <p className="text-secondary text-text-secondary">
                  {inputs.service_start && inputs.service_end
                    ? `Stated term: ${inputs.service_start} to ${inputs.service_end}.`
                    : "Contract dates unknown — they stay unknown until set; nothing is guessed. A SOW stating only a duration (e.g. seven weeks from kickoff) needs the kickoff date here."}
                </p>
                {termAssist && !inputs.service_end && (
                  <div
                    className="flex flex-wrap items-center gap-2"
                    data-testid="editor-term-assist"
                  >
                    {termAssist.suggested_end ? (
                      <>
                        <Button
                          type="button"
                          variant="secondary"
                          data-testid="editor-term-assist-apply"
                          onClick={() => patch("service_end", termAssist.suggested_end)}
                        >
                          Use {termAssist.suggested_end} (start +{" "}
                          {termAssist.weeks
                            ? `${termAssist.weeks} weeks`
                            : `${termAssist.months} months`}
                          )
                        </Button>
                        <span className="text-secondary text-text-secondary">
                          Derived from the SOW: “{termAssist.quote}”
                        </span>
                      </>
                    ) : (
                      <span className="text-secondary text-text-secondary">
                        The SOW states{" "}
                        {termAssist.weeks
                          ? `${termAssist.weeks} weeks`
                          : `${termAssist.months} months`}{" "}
                        (“{termAssist.quote}”). Enter the contract start
                        (kickoff) and the end date will be suggested here.
                      </span>
                    )}
                  </div>
                )}
                {inputs.profile === "hybrid" ? (
                  <HybridFields component={inputs} onChange={replaceComponent} />
                ) : (
                  <PricingFields
                    component={inputs}
                    onChange={(value) => patch("pricing", value)}
                    monthlyAllocationsElsewhere={inputs.profile === "fixed_assignment"}
                  />
                )}
                <details className="text-secondary">
                  <summary className="cursor-pointer py-1">Advanced pricing details</summary>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {field("Cost basis", "cost_basis")}
                  </div>
                </details>
                <details className="text-secondary">
                  <summary className="cursor-pointer py-1">
                    Source document & evidence
                  </summary>
                  <label className="block text-secondary mt-2">
                    Evidence lines (document, field, page — from SOW version{" "}
                    {snap.sow?.version_no ?? "—"})
                    <textarea
                      aria-label="Source evidence"
                      className="mt-1 min-h-20 w-full rounded-md border border-divider bg-surface p-3"
                      value={inputs.source_evidence.join("\n")}
                      onChange={(e) =>
                        patch("source_evidence", e.target.value.split("\n"))
                      }
                    />
                  </label>
                </details>
              </>,
            )}

            {sectionShell(
              "team",
              <>
                {floors && (
                  <p className="text-secondary text-text-secondary">
                    Configured policy floors: US {formatPercent(floors.us, 0)} ·
                    India {formatPercent(floors.india, 0)}. These apply per
                    geography at approval — a blended margin alone does not
                    pass them.
                  </p>
                )}
                {editable && snap.deal && (
                  <PlanTeamPanel
                    opportunityId={snap.deal.id}
                    inputs={inputs}
                    advice={advice}
                    onAdvice={setAdvice}
                    onApply={replaceComponent}
                    onResolve={handleResolve}
                  />
                )}
                {(inputs.profile === "calendar_staff_aug" ||
                  inputs.profile === "fixed_assignment" ||
                  inputs.profile === "recurring_msp" ||
                  inputs.pricing?.calendar_estimates ||
                  inputs.staffing.length > 0) && (
                  <CalendarFields component={inputs} onChange={replaceComponent} />
                )}
              </>,
            )}

            {sectionShell(
              "monthly",
              <>
                {inputs.profile === "fixed_assignment" && (
                  <MonthlyAllocations
                    pricing={pricing}
                    onChange={(value) => patch("pricing", value)}
                  />
                )}
                <h3 className="text-body font-medium">Other delivery expenses</h3>
                <p className="text-secondary text-text-secondary">
                  Travel, licences, subcontractors — anything that hits
                  delivery cost beyond the team above.
                </p>
                {inputs.costs.map((row, i) => (
                  <div
                    key={row.source_id}
                    className="flex flex-wrap items-end gap-2"
                  >
                    <label className="min-w-36 flex-1">
                      Month
                      <Input
                        aria-label={`Cost month ${i + 1}`}
                        type="date"
                        value={row.month}
                        onChange={(e) =>
                          patch(
                            "costs",
                            inputs.costs.map((r, j) =>
                              j === i ? { ...r, month: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <Location
                      label={`Cost location ${i + 1}`}
                      value={row.location}
                      onChange={(v) =>
                        patch(
                          "costs",
                          inputs.costs.map((r, j) =>
                            j === i ? { ...r, location: v } : r,
                          ),
                        )
                      }
                    />
                    <label className="min-w-24 flex-1">
                      Expense amount
                      <Input
                        aria-label={`Loaded cost ${i + 1}`}
                        inputMode="decimal"
                        value={row.amount ?? ""}
                        onChange={(e) =>
                          patch(
                            "costs",
                            inputs.costs.map((r, j) =>
                              j === i
                                ? { ...r, amount: e.target.value || null }
                                : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <Remove
                      label={`Delete cost ${i + 1}`}
                      onClick={() =>
                        patch(
                          "costs",
                          inputs.costs.filter((_, j) => j !== i),
                        )
                      }
                    />
                  </div>
                ))}
                <Button
                  variant="secondary"
                  onClick={() =>
                    patch("costs", [
                      ...inputs.costs,
                      {
                        source_id: crypto.randomUUID(),
                        month: "",
                        location: "",
                        amount: null,
                      },
                    ])
                  }
                >
                  <Plus className="h-4 w-4" /> Add expense
                </Button>
                {result.commercial_snapshot && (
                  <>
                    <h3 className="text-body font-medium">Monthly schedule</h3>
                    <p className="text-secondary">
                      {calculationState === "stale_preview"
                        ? "Provisional — edits since the last calculation are not reflected"
                        : calculationState === "preview"
                          ? "Provisional preview — not the saved plan"
                          : dirty
                            ? "Saved calculation; edits not calculated"
                            : "Saved calculation"}
                    </p>
                    <Schedule schedule={result.commercial_snapshot.schedule} />
                  </>
                )}
              </>,
            )}

            {sectionShell(
              "review",
              <>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={inputs.costs_confirmed}
                    onChange={(e) => patch("costs_confirmed", e.target.checked)}
                  />
                  All delivery costs confirmed
                </label>
                <p className="text-secondary text-text-secondary">
                  A human attestation — AI proposals never set this.
                </p>
                <label className="block">
                  Version note (why this version exists)
                  <Input
                    aria-label="Change reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
              </>,
            )}
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!editable || busy || !policy || !snap.sow}
              onClick={() => void calculate(false)}
            >
              <Calculator className="h-4 w-4" /> Preview
            </Button>
            <Button
              disabled={
                !editable ||
                busy ||
                !policy ||
                !reason.trim() ||
                !snap.sow ||
                !snap.deal
              }
              onClick={() => void calculate(true)}
            >
              <Save className="h-4 w-4" /> Save version
            </Button>
          </div>
        </>
      ) : (
        <div className="space-y-3">
          <p role="alert" className="text-danger">
            Unsupported commercial model: {inputs.profile}. Existing inputs are
            preserved; preview and save are unavailable for this model.
          </p>
          <h3 className="font-medium">Source evidence</h3>
          <ul className="list-inside list-disc">
            {inputs.source_evidence.map((evidence, index) => (
              <li key={index}>{evidence}</li>
            ))}
          </ul>
          <fieldset disabled={!canWrite || signedBasis || busy} className="min-w-0 space-y-3">
            <label className="block text-secondary">
              Replacement pricing profile
              <select aria-label="Replacement pricing profile" value={pendingProfile ?? ""}
                className="mt-1 h-10 w-full rounded-md border border-divider bg-surface px-3"
                onChange={(event) => setPendingProfile(event.target.value || null)}>
                <option value="">Select confirmed model</option>
                {Object.entries(PROFILE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
            <p>Replacing pricing clears unsupported terms from this draft. The saved version and source evidence are retained.</p>
            <Button disabled={!pendingProfile} onClick={() => {
              if (!pendingProfile) return;
              replaceComponent({ ...inputs, profile: pendingProfile, pricing: emptyPricing(pendingProfile) });
              setPendingProfile(null);
            }}>Replace unsupported pricing terms</Button>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button disabled variant="secondary"><Calculator className="h-4 w-4" /> Preview</Button>
            <Button disabled><Save className="h-4 w-4" /> Save version</Button>
          </div>
        </div>
      )}
      {supported && !rawRestricted && result.commercial_snapshot && (
        <p className="text-secondary">
          {calculationState === "stale_preview"
            ? "Unsaved preview; edits not calculated"
            : calculationState === "preview"
              ? "Unsaved preview"
              : dirty
                ? "Saved calculation; edits not calculated"
                : "Saved calculation"}
        </p>
      )}
      {result.computed && (
        <p>
          {!result.computed.complete
            ? "GM incomplete"
            : result.computed.policy.requires_ceo
              ? "CEO exception required"
              : "GM within policy"}
        </p>
      )}
      {result.computed && (
        <p className="text-secondary text-text-secondary" data-testid="approval-flow-note">
          {result.computed.complete && !result.computed.policy.requires_ceo
            ? "Approval flow: margin is within policy, so submission routes to the configured function reviews only — no CEO step."
            : "Approval flow: the configured function reviews plus the CEO exception step, which is added automatically while the margin is below a policy floor or not yet assessed."}
          {dirty || calculationState !== "saved"
            ? " This is a provisional calculation — Save version to publish it to the approval flow."
            : ""}
        </p>
      )}
      {result.computed && (
        <dl className="grid grid-cols-2 gap-2 text-body">
          <dt>US GM</dt>
          <dd>{formatPercent(result.computed.gm_us) ?? "Unassessed"}</dd>
          <dt>India GM</dt>
          <dd>{formatPercent(result.computed.gm_india) ?? "Unassessed"}</dd>
        </dl>
      )}
    </section>
  );
}

function Location({
  value,
  label,
  onChange,
}: {
  value: string;
  label: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="min-w-28 flex-1">
      Location
      <select
        aria-label={label}
        className="block h-10 w-full rounded-md border border-divider bg-surface px-3"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Unconfirmed</option>
        <option value="US">US</option>
        <option value="India">India</option>
      </select>
    </label>
  );
}
function Remove({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="ghost" aria-label={label} title={label} onClick={onClick}>
      <Trash2 className="h-4 w-4" />
    </Button>
  );
}
function Schedule({ schedule }: { schedule: CommercialSchedule }) {
  return (
    <div className="min-w-0 space-y-2">
      <h3 className="text-body font-medium">
        {schedule.component?.workstream_id ?? "Monthly schedule"}
      </h3>
      <p className="text-secondary">{schedule.status}</p>
      {schedule.missing.map((item, i) => (
        <p key={i} className="text-warning">
          {item.reason ?? item.field ?? item.key}
        </p>
      ))}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-body">
          <thead>
            <tr>
              {["Month", "Location", "Revenue", "Cost"].map((label) => (
                <th className="p-2" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {schedule.rows.map((row, i) => (
              <tr className="border-t border-divider" key={i}>
                <td className="p-2 whitespace-nowrap">{row.month}</td>
                <td className="p-2">{row.location}</td>
                <td className="p-2">{row.revenue}</td>
                <td className="p-2">{row.cost ?? "Unconfirmed"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!!schedule.calendar_rows?.length && (
        <section aria-label="Calendar calculation details" className="min-w-0 space-y-3">
          <h4 className="font-medium">Calendar calculation details</h4>
          {schedule.calendar_rows.map((row, index) => (
            <div key={`${row.assignment.assignment_id}-${row.month}-${index}`} className="min-w-0 border-t border-divider pt-3">
              <p>{row.assignment.role} / {row.assignment.location} / {row.month}</p>
              <p className="text-secondary">{row.period_start} to {row.period_end}; {row.assignment.quantity} people; allocation {row.assignment.allocation}</p>
              <p className="text-secondary">
                {row.assignment.cost_rate_basis === "monthly" ? "Monthly cost per person" :
                  row.assignment.cost_rate_basis === null ? "Unconfirmed cost basis" : "Loaded cost per paid hour"}:
                {" "}{row.assignment.currency ?? "Unconfirmed currency"} {row.assignment.cost_rate ?? "Unconfirmed"} / {row.assignment.cost_version ?? "Unconfirmed source"}
              </p>
              {row.assignment.cost_rate_basis === "monthly" && (
                <p className="text-secondary">Partial-month cost policy: {row.assignment.cost_proration === "full_month" ? "Full monthly allocation" : "Unconfirmed"}</p>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-body">
                  <thead><tr>{["Scheduled hours", "Billable hours", "Paid hours"].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
                  <tbody><tr>{[row.scheduled_hours, row.billable_hours, row.paid_hours].map((value, i) => <td className="p-2" key={i}>{value ?? "Unconfirmed"}</td>)}</tr></tbody>
                </table>
              </div>
              <details>
                <summary className="cursor-pointer py-2">Daily hours and exceptions</summary>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-body">
                    <thead><tr>{["Date", "Scheduled hours", "Billable hours", "Paid hours", "Exception"].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
                    <tbody>{row.days.map(day => <tr key={day.day} className="border-t border-divider">
                      <td className="whitespace-nowrap p-2">{day.day}</td><td className="p-2">{day.scheduled_hours}</td><td className="p-2">{day.billable_hours}</td><td className="p-2">{day.paid_hours}</td><td className="p-2">{day.reason ?? ""}</td>
                    </tr>)}</tbody>
                  </table>
                </div>
              </details>
            </div>
          ))}
        </section>
      )}
      {schedule.children?.map((child, i) => (
        <Schedule key={i} schedule={child} />
      ))}
    </div>
  );
}
