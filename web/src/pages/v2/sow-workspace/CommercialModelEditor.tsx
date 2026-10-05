import { useEffect, useState } from "react";
import { Calculator, Plus, Save, Trash2 } from "lucide-react";
import { getMe, type SowFieldName } from "../../../api/client";
import {
  getCommercialProfiles,
  previewCommercial,
  saveCommercialVersion,
  type CommercialComponent,
  type CommercialPreview,
  type CommercialSchedule,
  getCommercialProposal,
  type CommercialProposal,
} from "../../../api/commercial";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import type { WorkspaceSnapshot } from "./readiness";
import { formatPercent } from "./format";
import {
  emptyPricing,
  PricingFields,
  PROFILE_LABELS,
} from "./commercial-editor/PricingFields";
import { CalendarFields } from "./commercial-editor/CalendarFields";
import { HybridFields } from "./commercial-editor/HybridFields";
import { bindCommercialSource } from "./commercial-editor/bindings";
import { MspAdjustmentsFields } from "./commercial-editor/MspAdjustmentsFields";
import { PlanTeamPanel } from "./commercial-editor/PlanTeamPanel";

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

export function CommercialModelEditor({ snap }: { snap: WorkspaceSnapshot }) {
  const [inputs, setInputs] = useState(() => initialInputs(snap));
  const [modelId, setModelId] = useState(snap.gmModel?.id ?? null);
  const [result, setResult] = useState<CommercialPreview>({
    computed: snap.gmModel?.computed,
    commercial_snapshot: snap.gmModel?.commercial_snapshot ?? undefined,
  });
  const [canWrite, setCanWrite] = useState(false);
  const [policy, setPolicy] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [proposal, setProposal] = useState<CommercialProposal | null>(null);
  // S22 · pre-fill from the SOW + auto-staffing proposal when nothing is
  // saved yet and the human has not started typing. Every value stays
  // editable; the machine never confirms costs.
  useEffect(() => {
    if (snap.gmModel?.commercial_inputs || !snap.deal) return;
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
        if (active) setPolicy(registry.policy.version);
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
  const pricePatch = (key: string, value: unknown) =>
    patch("pricing", { ...pricing, [key]: value });
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
  return (
    <section className="min-w-0 space-y-4" aria-label="Commercial model">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-section">Commercial model</h2>
        <span className="text-secondary">
          {snap.gmModel?.commercial_profile ?? inputs.profile}
        </span>
      </header>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {editable && snap.deal && (
        <PlanTeamPanel
          opportunityId={snap.deal.id}
          inputs={inputs}
          onApply={(next) => {
            replaceComponent(next);
            setDirty(true);
          }}
        />
      )}
      {notice && <p role="status">{notice}</p>}
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
            <label className="block text-secondary">
              Pricing profile
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
              {field("Service start", "service_start", "date")}
              {field("Service end", "service_end", "date")}
              {field("Timezone", "timezone")}
              {field("Currency", "currency")}
              {field("Billing cadence", "billing_cadence")}
              {field("Cost basis", "cost_basis")}
            </div>
            <label className="block text-secondary">
              Source evidence
              <textarea
                className="mt-1 min-h-20 w-full rounded-md border border-divider bg-surface p-3"
                value={inputs.source_evidence.join("\n")}
                onChange={(e) =>
                  patch("source_evidence", e.target.value.split("\n"))
                }
              />
            </label>
            {inputs.profile === "fixed_assignment" ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label>
                    Total fee
                    <Input
                      inputMode="decimal"
                      value={pricing.total_fee ?? ""}
                      onChange={(e) =>
                        pricePatch("total_fee", e.target.value || null)
                      }
                    />
                  </label>
                  <label>
                    Allocation basis
                    <Input
                      value={pricing.allocation_basis ?? ""}
                      onChange={(e) =>
                        pricePatch("allocation_basis", e.target.value || null)
                      }
                    />
                  </label>
                  <label>
                    Currency minor unit
                    <Input
                      inputMode="decimal"
                      value={pricing.minor_unit ?? ""}
                      onChange={(e) => pricePatch("minor_unit", e.target.value)}
                    />
                  </label>
                </div>
                <h3 className="text-body font-medium">
                  Service-month allocations
                </h3>
                {(pricing.allocations ?? []).map((row, i) => (
                  <div key={i} className="flex flex-wrap items-end gap-2">
                    <label className="min-w-36 flex-1">
                      Month
                      <Input
                        aria-label={`Allocation month ${i + 1}`}
                        type="date"
                        value={row.month}
                        onChange={(e) =>
                          pricePatch(
                            "allocations",
                            pricing.allocations!.map((r, j) =>
                              j === i ? { ...r, month: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <Location
                      value={row.location}
                      label={`Allocation location ${i + 1}`}
                      onChange={(v) =>
                        pricePatch(
                          "allocations",
                          pricing.allocations!.map((r, j) =>
                            j === i ? { ...r, location: v } : r,
                          ),
                        )
                      }
                    />
                    <label className="min-w-24 flex-1">
                      Weight
                      <Input
                        aria-label={`Allocation weight ${i + 1}`}
                        value={row.weight}
                        onChange={(e) =>
                          pricePatch(
                            "allocations",
                            pricing.allocations!.map((r, j) =>
                              j === i ? { ...r, weight: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <Remove
                      label={`Delete allocation ${i + 1}`}
                      onClick={() =>
                        pricePatch(
                          "allocations",
                          pricing.allocations!.filter((_, j) => j !== i),
                        )
                      }
                    />
                  </div>
                ))}
                <Button
                  variant="secondary"
                  onClick={() =>
                    pricePatch("allocations", [
                      ...(pricing.allocations ?? []),
                      { month: "", location: "", weight: "" },
                    ])
                  }
                >
                  <Plus className="h-4 w-4" /> Add allocation
                </Button>
              </>
            ) : inputs.profile === "recurring_msp" ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label>
                    Proration
                    <select
                      className="block h-10 w-full rounded-md border border-divider bg-surface px-3"
                      value={pricing.proration ?? ""}
                      onChange={(e) =>
                        pricePatch("proration", e.target.value || null)
                      }
                    >
                      <option value="">Unconfirmed</option>
                      <option value="calendar_days">Calendar days</option>
                      <option value="full_month">Full month</option>
                    </select>
                  </label>
                  <label>
                    Included scope
                    <Input
                      value={pricing.included_scope ?? ""}
                      onChange={(e) =>
                        pricePatch("included_scope", e.target.value || null)
                      }
                    />
                  </label>
                </div>
                {(pricing.fees ?? []).map((row, i) => (
                  <div key={i} className="flex flex-wrap items-end gap-2">
                    <Location
                      label={`Fee location ${i + 1}`}
                      value={row.location}
                      onChange={(v) =>
                        pricePatch(
                          "fees",
                          pricing.fees!.map((r, j) =>
                            j === i ? { ...r, location: v } : r,
                          ),
                        )
                      }
                    />
                    <label className="flex-1">
                      Monthly fee
                      <Input
                        aria-label={`Monthly fee ${i + 1}`}
                        inputMode="decimal"
                        value={row.amount ?? ""}
                        onChange={(e) =>
                          pricePatch(
                            "fees",
                            pricing.fees!.map((r, j) =>
                              j === i
                                ? { ...r, amount: e.target.value || null }
                                : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <Remove
                      label={`Delete fee ${i + 1}`}
                      onClick={() =>
                        pricePatch(
                          "fees",
                          pricing.fees!.filter((_, j) => j !== i),
                        )
                      }
                    />
                  </div>
                ))}
                <Button
                  variant="secondary"
                  onClick={() =>
                    pricePatch("fees", [
                      ...(pricing.fees ?? []),
                      { location: "", amount: null },
                    ])
                  }
                >
                  <Plus className="h-4 w-4" /> Add monthly fee
                </Button>
                <MspAdjustmentsFields
                  pricing={pricing}
                  onChange={(value) => patch("pricing", value)}
                />
              </>
            ) : inputs.profile === "hybrid" ? (
              <HybridFields component={inputs} onChange={replaceComponent} />
            ) : (
              <PricingFields
                component={inputs}
                onChange={(pricing) => patch("pricing", pricing)}
              />
            )}
            {(inputs.profile === "calendar_staff_aug" ||
              inputs.profile === "fixed_assignment" ||
              inputs.profile === "recurring_msp" ||
              inputs.pricing?.calendar_estimates ||
              inputs.staffing.length > 0) && (
              <CalendarFields component={inputs} onChange={replaceComponent} />
            )}
            <h3 className="text-body font-medium">Period costs</h3>
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
                  Loaded cost
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
              <Plus className="h-4 w-4" /> Add period cost
            </Button>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={inputs.costs_confirmed}
                onChange={(e) => patch("costs_confirmed", e.target.checked)}
              />
              All delivery costs confirmed
            </label>
            <label className="block">
              Change reason
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
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
      {result.commercial_snapshot && (
        <>
          <p className="text-secondary">
            {calculationState === "stale_preview"
              ? "Unsaved preview; edits not calculated"
              : calculationState === "preview"
                ? "Unsaved preview"
                : dirty
                  ? "Saved calculation; edits not calculated"
                  : "Saved calculation"}
          </p>
          <Schedule schedule={result.commercial_snapshot.schedule} />
        </>
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
