/**
 * Staffing & GM uses one short contract section, one staffing grid and one
 * Save action. Monthly schedules remain server-derived for Forecast.
 * A Scope needs / Budget supports / Currently planned summary leads the
 * page; a green margin cannot hide an understaffed plan. All seven
 * registered pricing models keep their model-specific editors. Money
 * stays server-side Decimal — this file only formats and compares for
 * display. The single readiness panel lives in the workspace shell.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Save } from "lucide-react";
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
  getCommercialDraft,
  putCommercialDraft,
  deleteCommercialDraft,
} from "../../../api/commercial";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import type { WorkspaceSnapshot } from "./readiness";
import { formatPercent, fractionToPercent } from "./format";
import {
  emptyPricing,
  PricingFields,
  PROFILE_LABELS,
} from "./commercial-editor/PricingFields";
import { CalendarFields } from "./commercial-editor/CalendarFields";
import { HybridFields } from "./commercial-editor/HybridFields";
import { AdditionalCostsEditor } from "./commercial-editor/AdditionalCostsEditor";
import { bindCommercialSource } from "./commercial-editor/bindings";
import { PlanTeamPanel, type ResolutionAction } from "./commercial-editor/PlanTeamPanel";
import { FinanceGmPanel } from "./staffing/FinanceGmPanel";

type CommercialMissing = NonNullable<
  CommercialSchedule["missing"]
>[number];

export interface CommercialEditorStatus {
  state:
    | "idle"
    | "calculating"
    | "blocked"
    | "ready_to_preview"
    | "ready_to_save"
    | "saving";
  blocker?: string;
  blockerLabel?: string;
}

function blockerCopy(item: CommercialMissing): {
  message: string;
  label: string;
  section: "contract" | "team";
} {
  const row = item.line ? `Row ${item.line}${item.role ? ` · ${item.role}` : ""}: ` : "";
  const field = item.field ?? item.key ?? "input";
  const definitions: Record<string, [string, string, "contract" | "team"]> = {
    billing_cadence: ["confirm the billing schedule", "billing schedule", "contract"],
    service_period: ["confirm the contract start and end dates", "contract dates", "contract"],
    currency: ["confirm the contract currency", "contract currency", "contract"],
    calendar: ["enter total hours", item.line ? `row ${item.line} hours` : "hours", "team"],
    hours_billable: ["enter total hours", item.line ? `row ${item.line} hours` : "hours", "team"],
    cost_rate: ["enter the delivery cost rate", item.line ? `row ${item.line} cost rate` : "cost rate", "team"],
    cost_version: ["identify the cost rate source/version", item.line ? `row ${item.line} cost source` : "cost source", "team"],
    location: ["confirm the delivery location", item.line ? `row ${item.line} location` : "delivery location", "team"],
    costs: ["complete the additional cost", "additional cost", "team"],
    "costs.amount": ["complete the additional cost amount", "additional cost", "team"],
  };
  const [action, label, section] = definitions[field] ?? [
    item.reason ?? `complete ${field.replaceAll("_", " ")}`,
    field.replaceAll("_", " "),
    item.line ? "team" : "contract",
  ];
  return {
    message: `${row}${item.reason ?? action}. Correction: ${action}.`,
    label,
    section,
  };
}

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

function hasBlankCalendarHours(
  calendar: NonNullable<CommercialComponent["staffing"][number]["calendar"]>,
): boolean {
  const hours = [
    ...calendar.week,
    ...calendar.overrides.map((override) => override.hours),
  ];
  return hours.some(({ scheduled, billable, paid }) =>
    [scheduled, billable, paid].some((value) => value.trim() === ""),
  );
}

/**
 * Old working drafts could contain a seven-day calendar shell whose 21 hour
 * cells were empty strings. It is neither usable evidence nor valid API input.
 * The simplified editor represents that state as a missing total-hours value.
 */
function discardEmptyLegacyCalendars(
  component: CommercialComponent,
): CommercialComponent {
  const pricing =
    component.profile === "hybrid" && component.pricing?.components
      ? {
          ...component.pricing,
          components: component.pricing.components.map(
            discardEmptyLegacyCalendars,
          ),
        }
      : component.pricing;
  return {
    ...component,
    pricing,
    staffing: component.staffing.map((row) => ({
      ...row,
      calendar:
        row.calendar && hasBlankCalendarHours(row.calendar)
          ? null
          : row.calendar,
    })),
  };
}

/**
 * A role with no dates inherits the contract term. Existing explicit role
 * dates remain independent so a partial assignment is not silently widened.
 */
function inheritMissingRoleDates(
  component: CommercialComponent,
): CommercialComponent {
  const normalized = discardEmptyLegacyCalendars(component);
  return {
    ...normalized,
    staffing: normalized.staffing.map((row) => ({
      ...row,
      start: row.start || normalized.service_start,
      end: row.end || normalized.service_end,
      calendar: row.calendar
        ? {
            ...row.calendar,
            coverage_start:
              row.calendar.coverage_start || normalized.service_start || "",
            coverage_end:
              row.calendar.coverage_end || normalized.service_end || "",
          }
        : row.calendar,
    })),
  };
}

/**
 * Keep inherited role/calendar dates aligned with an edited contract term.
 * A row that differs from the previous term is an explicit override and is
 * deliberately preserved.
 */
function updateContractDate(
  component: CommercialComponent,
  key: "service_start" | "service_end",
  value: string | null,
): CommercialComponent {
  const previous = component[key];
  return {
    ...component,
    [key]: value,
    staffing: component.staffing.map((row) => {
      if (key === "service_start") {
        const calendar = row.calendar;
        return {
          ...row,
          start: !row.start || row.start === previous ? value : row.start,
          calendar:
            calendar &&
            (!calendar.coverage_start || calendar.coverage_start === previous)
              ? { ...calendar, coverage_start: value || "" }
              : calendar,
        };
      }
      const calendar = row.calendar;
      return {
        ...row,
        end: !row.end || row.end === previous ? value : row.end,
        calendar:
          calendar && (!calendar.coverage_end || calendar.coverage_end === previous)
            ? { ...calendar, coverage_end: value || "" }
            : calendar,
      };
    }),
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
  { inputs: CommercialComponent; dirty: boolean }
>();

/** Test isolation hook: drafts must not leak between test renders. */
export function resetCommercialDraftCache() {
  draftCache.clear();
}

/**
 * S22 round 3 · rule 10: a blank form is a defect. Fill every engine
 * gate the system can derive, deterministically and visibly, so GM can
 * compute without retyping facts the draft already holds. Each key is
 * filled at most once per mount, only when empty — user edits always
 * win. Returns the patched component plus plain-language notes.
 */
function deriveDraftDefaults(
  inputs: CommercialComponent,
  applied: Set<string>,
): { next: CommercialComponent; notes: string[] } {
  const next = structuredClone(inputs);
  const notes: string[] = [];
  const fill = (key: string, note: string, apply: () => void) => {
    if (applied.has(key)) return;
    applied.add(key);
    apply();
    notes.push(note);
  };
  const iso = (value: string | null | undefined) =>
    value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
  // Contract dates ← the envelope of the role dates already entered.
  const starts = next.staffing.map((r) => iso(r.start)).filter(Boolean) as string[];
  const ends = next.staffing.map((r) => iso(r.end)).filter(Boolean) as string[];
  if (!iso(next.service_start) && starts.length)
    fill("service_start", "Contract start taken from your earliest role start.", () => {
      next.service_start = [...starts].sort()[0];
    });
  if (!iso(next.service_end) && ends.length)
    fill("service_end", "Contract end taken from your latest role end.", () => {
      next.service_end = [...ends].sort().at(-1)!;
    });
  if (!next.workstream_id)
    fill("workstream_id", "Workstream defaulted to \"delivery\".", () => {
      next.workstream_id = "delivery";
    });
  if (!next.timezone)
    fill("timezone", "Contract timezone defaulted to America/Los_Angeles.", () => {
      next.timezone = "America/Los_Angeles";
    });
  if (next.profile === "fixed_assignment") {
    const pricing = next.pricing ?? {};
    if (!pricing.allocation_basis && pricing.total_fee)
      fill("allocation_basis", "Revenue allocation method defaulted to even service months.", () => {
        next.pricing = { ...pricing, allocation_basis: "even service months (defaulted)" };
      });
    const start = iso(next.service_start);
    const end = iso(next.service_end);
    if (
      start && end && pricing.total_fee &&
      !(pricing.allocations ?? []).length
    )
      fill("allocations", "Revenue is distributed evenly across the service months.", () => {
        // Revenue geography defaults to where the team delivers from
        // (the dominant staffing location); change it if revenue books
        // elsewhere. Equal weights are exact: the engine normalizes.
        const fteByLocation = new Map<string, number>();
        for (const row of next.staffing) {
          if (!row.location) continue;
          fteByLocation.set(
            row.location,
            (fteByLocation.get(row.location) ?? 0) +
              (row.quantity || 0) * (Number(row.allocation) || 0),
          );
        }
        const location =
          [...fteByLocation.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "US";
        const months: string[] = [];
        const cursor = new Date(`${start.slice(0, 7)}-01T00:00:00Z`);
        const last = new Date(`${end.slice(0, 7)}-01T00:00:00Z`);
        while (cursor <= last && months.length < 120) {
          months.push(cursor.toISOString().slice(0, 10));
          cursor.setUTCMonth(cursor.getUTCMonth() + 1);
        }
        next.pricing = {
          ...(next.pricing ?? {}),
          allocations: months.map((month) => ({ month, location, weight: "1" })),
        };
      });
  }
  return { next, notes };
}

const SECTIONS = [
  { id: "contract", label: "1 · Contract & pricing" },
  { id: "team", label: "2 · Team & additional costs" },
] as const;

export function CommercialModelEditor({
  snap,
  onStatusChange,
  onPrimaryAction,
  onSaved,
}: {
  snap: WorkspaceSnapshot;
  onStatusChange?: (status: CommercialEditorStatus | null) => void;
  onPrimaryAction?: (run: (() => void) | null) => void;
  onSaved?: (model: NonNullable<WorkspaceSnapshot["gmModel"]>) => void | Promise<void>;
}) {
  const draftKey = `${snap.sow?.id ?? "none"}:${snap.gmModel?.id ?? "new"}`;
  const cached = draftCache.get(draftKey);
  const [inputs, setInputs] = useState(() =>
    inheritMissingRoleDates(cached?.dirty ? cached.inputs : initialInputs(snap)),
  );
  const [modelId, setModelId] = useState(snap.gmModel?.id ?? null);
  const [result, setResult] = useState<CommercialPreview>({
    computed: snap.gmModel?.computed,
    commercial_snapshot: snap.gmModel?.commercial_snapshot ?? undefined,
  });
  const [canWrite, setCanWrite] = useState(false);
  const [policy, setPolicy] = useState("");
  const [floors, setFloors] = useState<{ us: string; india: string } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(cached?.dirty ?? false);
  const [proposal, setProposal] = useState<CommercialProposal | null>(null);
  const [advice, setAdvice] = useState<StaffingAdvice | null>(null);
  const [resolution, setResolution] = useState<ResolutionAction | null>(null);
  const [termAssist, setTermAssist] = useState<TermAssist | null>(null);
  // Server-persisted working draft (S22 root-cause fix): the plan
  // survives reloads and is visible on the Confirm page. updated_at is
  // the optimistic-concurrency stamp; a conflict stops auto-save loudly
  // instead of overwriting another session.
  const [draftStamp, setDraftStamp] = useState<string | null>(null);
  const [draftRestored, setDraftRestored] = useState<string | null>(null);
  const [draftError, setDraftError] = useState("");
  const draftLoaded = useRef(false);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const calculationRequest = useRef(0);
  const draftSaveRequest = useRef(0);
  const draftSaveQueue = useRef<Promise<void>>(Promise.resolve());
  const saving = useRef(false);
  const primaryActionRef = useRef<() => void>(() => {});

  useEffect(() => {
    onPrimaryAction?.(() => primaryActionRef.current());
    return () => onPrimaryAction?.(null);
  }, [onPrimaryAction]);

  useEffect(() => {
    if (!snap.deal?.id || draftLoaded.current) return;
    draftLoaded.current = true;
    let active = true;
    getCommercialDraft(snap.deal.id)
      .then((draft) => {
        if (!active || !draft.exists || !draft.inputs) return;
        setDraftStamp(draft.updated_at ?? null);
        // A live in-memory draft from this session wins; otherwise the
        // server draft is the newest working state — restore it.
        if (!draftCache.get(draftKey)?.dirty) {
          setInputs(inheritMissingRoleDates(structuredClone(draft.inputs)));
          setDirty(true);
          setDraftRestored(draft.updated_at ?? "");
        }
      })
      .catch(() => {
        /* read-only roles see no draft; the editor stands */
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap.deal?.id]);

  const draftStampRef = useRef<string | null>(null);
  draftStampRef.current = draftStamp;

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
    draftCache.set(draftKey, { inputs, dirty });
  }, [draftKey, inputs, dirty]);

  // S22 · pre-fill from the SOW + auto-staffing proposal when nothing is
  // saved yet and the human has not started typing. Every value stays
  // editable; the machine never confirms costs.
  const [proposalSettled, setProposalSettled] = useState(false);
  useEffect(() => {
    if (snap.gmModel?.commercial_inputs || !snap.deal) {
      setProposalSettled(true);
      return;
    }
    if (draftCache.get(draftKey)?.dirty) {
      setProposalSettled(true);
      return;
    }
    let active = true;
    getCommercialProposal(snap.deal.id)
      .then((p) => {
        if (!active) return;
        setProposal(p);
      })
      .catch(() => {
        /* read-only roles or signed basis: the empty editor stands */
      })
      .finally(() => {
        if (active) setProposalSettled(true);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap.deal?.id]);
  useEffect(() => {
    if (!proposal || dirty || snap.gmModel?.commercial_inputs) return;
    setInputs(inheritMissingRoleDates(structuredClone(proposal.component)));
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
  // Rule 10 autofill: whenever the draft gains the facts a default can
  // be derived from (roles with dates, a fee), fill the remaining
  // engine gates once, visibly. Runs after any change; each key fires
  // at most once per mount and never overwrites a value.
  const defaultsApplied = useRef(new Set<string>());
  const [defaultNotes, setDefaultNotes] = useState<string[]>([]);
  useEffect(() => {
    // Only while no commercial version exists: a saved version's inputs
    // round-trip untouched (the independent-editor invariants); the
    // from-scratch draft is where blanks get filled.
    if (!editable || snap.gmModel?.commercial_inputs) return;
    // Wait for the SOW proposal fetch to settle and for something
    // substantive (a team or a fee): autofilling an empty form early
    // would mark it dirty and block the richer proposal prefill.
    if (!proposalSettled) return;
    if (!inputs.staffing.length && !inputs.pricing?.total_fee) return;
    const { next, notes } = deriveDraftDefaults(inputs, defaultsApplied.current);
    if (notes.length) {
      setInputs(next);
      setDirty(true);
      setDefaultNotes((prev) => [...prev, ...notes]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs, editable, proposalSettled]);
  // Debounced auto-save of the working draft to the server. Placed
  // after `editable` so a late role check still arms the effect.
  useEffect(() => {
    if (!dirty || !editable || !snap.deal?.id || draftError) return;
    const request = ++draftSaveRequest.current;
    const timer = setTimeout(() => {
      // Serialize writes so a slow older request cannot land after a newer
      // draft. The server stamp remains the cross-session guard; the local
      // request number prevents an older response from replacing UI state.
      draftSaveQueue.current = draftSaveQueue.current
        .catch(() => undefined)
        .then(async () => {
          const saved = await putCommercialDraft(snap.deal!.id, {
            inputs,
            sow_version_id: snap.sow?.id ?? null,
            expected_updated_at: draftStampRef.current,
          });
          draftStampRef.current = saved.updated_at;
          if (request === draftSaveRequest.current)
            setDraftStamp(saved.updated_at);
        })
        .catch((e) => {
          if (request !== draftSaveRequest.current) return;
          setDraftError(
            e instanceof Error && e.message.includes("409")
              ? "Draft conflict: another session changed this draft — reload before editing further."
              : "Draft could not be auto-saved — your edits are only in this tab.",
          );
        });
    }, 2000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs, dirty, editable, snap.deal?.id, draftError]);
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
    setInputs((previous) =>
      key === "service_start" || key === "service_end"
        ? updateContractDate(
            previous,
            key,
            typeof value === "string" && value ? value : null,
          )
        : { ...previous, [key]: value },
    );
    setNotice("");
    setDirty(true);
    setCalculationState((state) =>
      state === "saved" ? state : "stale_preview",
    );
  };
  async function calculate(save: boolean) {
    const request = ++calculationRequest.current;
    saving.current = save;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      // Pressing Save is the human confirmation of the staffing and
      // additional-cost rows. Cost basis is deliberately not a user field.
      const body = bindCommercialSource({
        ...inputs,
        billing_cadence:
          inputs.billing_cadence === "on_completion"
            ? "fixed_post_delivery"
            : inputs.billing_cadence,
        cost_basis: null,
        costs_confirmed: true,
      }, {
        policy_version: policy,
        source_id: snap.sow!.sow_id,
        source_version: snap.sow!.id,
      });
      if (save) {
        const response = await saveCommercialVersion(snap.deal!.id, {
          sow_version_id: snap.sow!.id,
          expected_gm_model_id: modelId,
          inputs: body,
          change_reason: "Staffing and GM checkpoint saved",
        });
        setModelId(response.gm_model.id);
        setInputs(
          inheritMissingRoleDates(response.gm_model.commercial_inputs ?? body),
        );
        setResult({
          computed: response.gm_model.computed,
          commercial_snapshot:
            response.gm_model.commercial_snapshot ?? undefined,
        });
        setNotice("Commercial version saved.");
        setDirty(false);
        draftCache.delete(draftKey);
        setCalculationState("saved");
        // The saved version supersedes the working draft.
        setDraftStamp(null);
        setDraftRestored(null);
        if (snap.deal?.id)
          deleteCommercialDraft(snap.deal.id).catch(() => {
            /* draft cleanup is best-effort */
          });
        await onSaved?.(response.gm_model);
      } else {
        const preview = await previewCommercial(body);
        if (request !== calculationRequest.current) return;
        setResult(preview);
        setCalculationState("preview");
      }
    } catch (e) {
      if (request !== calculationRequest.current) return;
      setError(e instanceof Error ? e.message : "Commercial request failed");
    } finally {
      if (request === calculationRequest.current) {
        saving.current = false;
        setBusy(false);
      }
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
      inputs.pricing !== null;
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
          aria-label={label}
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
  const focusMissing = (item: CommercialMissing) => {
    const copy = blockerCopy(item);
    const section = sectionRefs.current[copy.section];
    section?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    window.setTimeout(() => {
      const row = item.line
        ? section?.querySelector<HTMLElement>(`[data-staffing-row="${item.line}"]`)
        : section;
      const labelByField: Record<string, string> = {
        billing_cadence: "Billing schedule",
        service_period: "Contract start",
        currency: "Contract currency",
        location: item.line ? `Location ${item.line}` : "Location 1",
        calendar: item.line ? `Hours ${item.line}` : "Hours 1",
        hours_billable: item.line ? `Hours ${item.line}` : "Hours 1",
        cost_rate: item.line ? `Cost per hour ${item.line}` : "Cost per hour 1",
      };
      const label = labelByField[item.field ?? ""];
      const exact = label
        ? [...(row?.querySelectorAll<HTMLElement>("input, select, button") ?? [])]
            .find((control) => control.getAttribute("aria-label") === label)
        : null;
      const target = exact ?? row?.querySelector<HTMLElement>("input, select, button") ?? section;
      target?.closest("details")?.setAttribute("open", "");
      target?.focus?.();
    }, 0);
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
  };

  const calculationCurrent = !dirty || calculationState === "preview";
  const firstMissing = calculationCurrent
    ? result.commercial_snapshot?.schedule.missing?.[0]
    : undefined;
  let editorStatus: CommercialEditorStatus;
  if (busy) editorStatus = { state: saving.current ? "saving" : "calculating" };
  else if (firstMissing) {
    const copy = blockerCopy(firstMissing);
    editorStatus = { state: "blocked", blocker: copy.message, blockerLabel: copy.label };
  } else if (calculationCurrent && result.computed?.complete && dirty) {
    editorStatus = { state: "ready_to_save" };
  } else if (dirty) editorStatus = { state: "ready_to_preview" };
  else editorStatus = { state: "idle" };

  primaryActionRef.current = () => {
    if (firstMissing) focusMissing(firstMissing);
    else if (calculationCurrent && result.computed?.complete && dirty) void calculate(true);
    else if (dirty) void calculate(false);
    else goTo("contract");
  };
  useEffect(() => {
    onStatusChange?.(editorStatus);
  }, [
    onStatusChange,
    editorStatus.state,
    editorStatus.blocker,
    editorStatus.blockerLabel,
  ]);
  useEffect(() => () => onStatusChange?.(null), [onStatusChange]);

  const sectionShell = (
    id: "contract" | "team",
    children: ReactNode,
  ) => (
    <section
      key={id}
      id={`sgm-${id}`}
      ref={(el) => {
        sectionRefs.current[id] = el;
      }}
      aria-label={SECTIONS.find((s) => s.id === id)?.label ?? id}
      data-testid={`sgm-section-${id}`}
      className="rounded-panel border border-divider bg-surface p-4 space-y-4 scroll-mt-24"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-section text-text">
          {SECTIONS.find((s) => s.id === id)?.label ?? id}
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
          <span data-testid="draft-state">
            {dirty
              ? draftStamp && !draftError
                ? "Draft auto-saved"
                : "Unsaved draft"
              : "Saved"}
          </span>
          <span>{snap.gmModel?.commercial_profile ?? inputs.profile}</span>
        </span>
      </header>
      {error && (
        <p role="alert" data-testid="commercial-error" className="text-danger">
          {error}
        </p>
      )}

      {/* Scope needs / Budget supports / Currently planned — one summary
          above the editor. Unknown stays Unknown, never zero. */}
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

      {notice && <p role="status">{notice}</p>}
      {defaultNotes.length > 0 && (
        <div
          role="note"
          data-testid="defaults-note"
          className="rounded-panel border border-divider bg-surface p-3 text-secondary"
        >
          <p className="text-text">
            Filled in from what you already entered (every value stays
            editable):
          </p>
          <ul className="mt-1 list-disc pl-5 text-text-secondary">
            {defaultNotes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}
      {draftError && (
        <p role="alert" data-testid="draft-error" className="text-danger">
          {draftError}
        </p>
      )}
      {draftRestored !== null && dirty && (
        <div
          role="note"
          data-testid="draft-restored-banner"
          className="rounded-panel border border-primary/40 bg-primary-subtle/30 p-3 text-secondary"
        >
          <p className="text-text">
            Working draft restored
            {draftRestored ? ` (last saved ${draftRestored.slice(0, 16).replace("T", " ")})` : ""}
            . Continue editing or use Save when you are ready to stop.
          </p>
          <button
            type="button"
            data-testid="draft-discard"
            className="mt-2 underline"
            onClick={() => {
              if (snap.deal?.id)
                deleteCommercialDraft(snap.deal.id).catch(() => {});
              draftCache.delete(draftKey);
              setDraftStamp(null);
              setDraftRestored(null);
              setDirty(false);
              setInputs(inheritMissingRoleDates(initialInputs(snap)));
            }}
          >
            Discard draft and start from the saved version
          </button>
        </div>
      )}
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
                setInputs(
                  inheritMissingRoleDates(structuredClone(proposal.component)),
                );
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
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {field("Contract start", "service_start", "date")}
                  {field("Contract end", "service_end", "date")}
                  {field("Contract currency", "currency")}
                  <label className="space-y-1 text-secondary">
                    Billing schedule
                    <select
                      aria-label="Billing schedule"
                      className="h-10 w-full rounded-md border border-divider bg-surface px-3"
                      value={
                        inputs.billing_cadence === "on_completion"
                          ? "fixed_post_delivery"
                          : (inputs.billing_cadence ?? "")
                      }
                      onChange={(event) => patch("billing_cadence", event.target.value || null)}
                    >
                      <option value="">Select</option>
                      <option value="weekly">Weekly</option>
                      <option value="biweekly">Bi-weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="fixed_post_delivery">Fixed after project delivery</option>
                    </select>
                  </label>
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
                {inputs.profile === "fixed_assignment" ? (
                  <label className="block text-secondary">
                    Contract fee
                    <Input
                      aria-label="Contract fee"
                      inputMode="decimal"
                      value={pricing.total_fee ?? ""}
                      onChange={(event) =>
                        patch("pricing", {
                          ...pricing,
                          total_fee: event.target.value || null,
                        })
                      }
                    />
                  </label>
                ) : inputs.profile === "hybrid" ? (
                  <HybridFields component={inputs} onChange={replaceComponent} />
                ) : (
                  <PricingFields
                    component={inputs}
                    onChange={(value) => patch("pricing", value)}
                  />
                )}
              </>,
            )}

            {sectionShell(
              "team",
              <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
                <div className="min-w-0 space-y-5">
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
                  <AdditionalCostsEditor
                    rows={inputs.costs}
                    serviceStart={inputs.service_start}
                    onChange={(rows) => patch("costs", rows)}
                  />
                </div>
                <aside className="min-w-0 xl:sticky xl:top-4 xl:self-start">
                  <FinanceGmPanel
                    result={
                      result.computed
                        ? {
                            ...result.computed,
                            ...result.computed.policy,
                            gm_version: snap.gmModel?.version,
                          }
                        : null
                    }
                    locations={inputs.staffing
                      .map((row) => row.location)
                      .filter((location): location is string => !!location)}
                    state={
                      calculationState === "saved" && !dirty ? "saved" : "draft"
                    }
                  />
                </aside>
              </div>,
            )}

          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={
                !editable ||
                busy ||
                !policy ||
                !snap.sow ||
                !snap.deal
              }
              onClick={() => void calculate(true)}
            >
              <Save className="h-4 w-4" /> {busy ? "Saving…" : "Save"}
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
            <Button disabled><Save className="h-4 w-4" /> Save</Button>
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
            ? " This is a provisional calculation — Save to publish it to the approval flow."
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
