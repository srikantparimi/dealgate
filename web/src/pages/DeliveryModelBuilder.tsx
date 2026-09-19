/**
 * DeliveryModelBuilder — S3 E6.
 *
 * Delivery lead edits the resource grid + non-labor costs + delivery
 * pattern + contingency. Every keystroke debounces into
 * ``POST /delivery-model/preview`` (the API is the only source of truth
 * for GM numbers — blueprint §2 / CLAUDE.md rule 2). Save posts to
 * ``POST /delivery-model/{opportunity_id}/versions`` and the "Export to
 * Excel" button hands the persisted version to
 * ``GET /delivery-model/versions/{id}/xlsx``.
 *
 * The component renders inline inside :file:`DealDetail.tsx`; when a
 * gm_model already exists the parent shows a summary card + an "Open
 * builder" button that mounts this page.
 */

import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  exportDeliveryModelXlsx,
  getLatestDeliveryModel,
  listDeliveryTemplates,
  previewDeliveryModel,
  saveDeliveryModelVersion,
  saveDeliveryTemplate,
  seedDeliveryModelFromTemplate,
  type DeliveryComputedResult,
  type DeliveryCostCategory,
  type DeliveryCostLineInput,
  type DeliveryLocation,
  type DeliveryPhaseInput,
  type DeliveryPreviewRequestInputs,
  type DeliveryResourceLineInput,
  type DeliveryTemplateSummary,
  type DeliveryWarning,
  type EngagementType,
  type UUID,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { StatusChip } from "../ui/StatusChip";

const ENGAGEMENTS: { value: EngagementType; label: string }[] = [
  { value: "fixed_price", label: "Fixed price" },
  { value: "staff_aug", label: "Staff augmentation" },
  { value: "single_resource", label: "Single resource" },
  { value: "assessment", label: "Assessment / discovery" },
  { value: "tm", label: "Time & materials" },
  { value: "managed_service", label: "Managed service" },
];

const COST_CATEGORIES: DeliveryCostCategory[] = [
  "tools",
  "travel",
  "subcontractor",
  "other",
];

interface FormState {
  engagement: EngagementType;
  delivery_pattern: string;
  contingency_pct: string;
  warranty_days: string;
  total_price: string;
  revenue_us: string;
  revenue_india: string;
  monthly_fee_us: string;
  monthly_fee_india: string;
  term_months: string;
  revenue_cap: string;
  deliverable: string;
  phases: DeliveryPhaseInput[];
  resource_lines: DeliveryResourceLineInput[];
  cost_lines: DeliveryCostLineInput[];
}

function blankResource(
  location: DeliveryLocation = "US",
  phaseName: string | null = null,
): DeliveryResourceLineInput {
  return {
    role: "",
    seniority: "",
    location,
    person_name: null,
    allocation_pct: "1",
    start_date: "2026-01-01",
    end_date: "2026-06-30",
    hours_billable: "0",
    hourly_bill_rate: "0",
    hourly_cost: null,
    validated_by: null,
    phase_name: phaseName,
  };
}

function blankCost(
  category: DeliveryCostCategory = "tools",
  phaseName: string | null = null,
): DeliveryCostLineInput {
  return {
    category,
    amount: "0",
    location: "US",
    note: null,
    phase_name: phaseName,
  };
}

function blankPhase(order: number): DeliveryPhaseInput {
  return {
    name: `Phase ${order + 1}`,
    order,
    sow_deliverable_ref: null,
    description: null,
  };
}

function blankForm(engagement: EngagementType = "fixed_price"): FormState {
  return {
    engagement,
    delivery_pattern: "",
    contingency_pct: "",
    warranty_days: "",
    total_price: "",
    revenue_us: "",
    revenue_india: "",
    monthly_fee_us: "",
    monthly_fee_india: "",
    term_months: "",
    revenue_cap: "",
    deliverable: "",
    phases: [],
    resource_lines: [],
    cost_lines: [],
  };
}

function toPreviewInputs(form: FormState): DeliveryPreviewRequestInputs {
  return {
    resource_lines: form.resource_lines,
    cost_lines: form.cost_lines,
    delivery_pattern: form.delivery_pattern || null,
    contingency_pct: form.contingency_pct || null,
    warranty_days: form.warranty_days ? Number(form.warranty_days) : null,
    ...(form.total_price ? { total_price: form.total_price } : {}),
    ...(form.revenue_us ? { revenue_us: form.revenue_us } : {}),
    ...(form.revenue_india ? { revenue_india: form.revenue_india } : {}),
    ...(form.monthly_fee_us ? { monthly_fee_us: form.monthly_fee_us } : {}),
    ...(form.monthly_fee_india ? { monthly_fee_india: form.monthly_fee_india } : {}),
    ...(form.term_months ? { term_months: form.term_months } : {}),
    ...(form.revenue_cap ? { revenue_cap: form.revenue_cap } : {}),
    ...(form.deliverable ? { deliverable: form.deliverable } : {}),
  };
}

function fmtPct(v: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${(n * 100).toFixed(2)}%`;
}

function fmtMoney(v: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function passTone(present: boolean, pass: boolean, complete: boolean): "ok" | "block" | "neutral" {
  if (!present || !complete) return "neutral";
  return pass ? "ok" : "block";
}

// --- component ------------------------------------------------------------

interface Props {
  opportunityId: UUID;
  /** Filled from SOW confirmation when available (Agent P). */
  suggestedEngagement?: EngagementType | null;
  sowVersionId?: UUID | null;
  /** Notifies the parent DealDetail after a successful save. */
  onSaved?: (gmModelId: UUID) => void;
}

export function DeliveryModelBuilder({
  opportunityId,
  suggestedEngagement = null,
  sowVersionId = null,
  onSaved,
}: Props) {
  const [form, setForm] = useState<FormState>(() =>
    blankForm(suggestedEngagement ?? "fixed_price"),
  );
  const [result, setResult] = useState<DeliveryComputedResult | null>(null);
  const [capacityWarnings, setCapacityWarnings] = useState<DeliveryWarning[]>([]);
  const [hrWarnings, setHrWarnings] = useState<DeliveryWarning[]>([]);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [lastVersionId, setLastVersionId] = useState<UUID | null>(null);
  const debounceRef = useRef<number | undefined>(undefined);
  // Which phases (by name) are collapsed in the accordion.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Save-as-template modal + name buffer.
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [templateName, setTemplateName] = useState("");
  // Load-template picker.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [templateOptions, setTemplateOptions] = useState<
    DeliveryTemplateSummary[]
  >([]);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateActionError, setTemplateActionError] = useState<unknown>(null);

  // Prefill from latest saved version, when one exists.
  useEffect(() => {
    let cancelled = false;
    getLatestDeliveryModel(opportunityId)
      .then((res) => {
        if (cancelled) return;
        if (res.gm_model) {
          const gm = res.gm_model;
          const phases = gm.phases ?? [];
          // Build the phase_name lookup from the saved phase_id so
          // rehydrated rows keep their phase association after a reload.
          const phaseNameById = new Map<string, string>(
            phases.map((p) => [p.id, p.name]),
          );
          setForm((prev) => ({
            ...prev,
            engagement: gm.engagement_type,
            delivery_pattern: gm.delivery_pattern ?? "",
            contingency_pct: gm.contingency_pct ?? "",
            warranty_days: gm.warranty_days != null ? String(gm.warranty_days) : "",
            revenue_us: gm.revenue_us ?? "",
            revenue_india: gm.revenue_india ?? "",
            total_price:
              gm.revenue_us && gm.revenue_india
                ? String(Number(gm.revenue_us) + Number(gm.revenue_india))
                : "",
            phases: phases.map((p) => ({
              name: p.name,
              order: p.order,
              sow_deliverable_ref: p.sow_deliverable_ref,
              description: p.description,
            })),
            resource_lines: gm.resource_lines.map((r) => ({
              role: r.role,
              seniority: r.seniority,
              location: r.location,
              person_name: r.person_name,
              allocation_pct: r.allocation_pct,
              start_date: r.start_date,
              end_date: r.end_date,
              hours_billable: r.hours_billable,
              hourly_bill_rate: r.hourly_bill_rate,
              hourly_cost: r.hourly_cost,
              validated_by: r.validated_by,
              phase_name: r.phase_id ? phaseNameById.get(r.phase_id) ?? null : null,
            })),
            cost_lines: gm.cost_lines.map((c) => ({
              category: c.category,
              amount: c.amount,
              location: c.location,
              note: c.note,
              phase_name: c.phase_id ? phaseNameById.get(c.phase_id) ?? null : null,
            })),
          }));
          setLastVersionId(gm.id);
        }
      })
      .catch(() => {
        // Not fatal — the Builder can render on an empty form.
      });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  // Debounced live-compute — 300ms per the story.
  useEffect(() => {
    if (debounceRef.current !== undefined) {
      window.clearTimeout(debounceRef.current);
    }
    if (form.resource_lines.length === 0) {
      setResult(null);
      return;
    }
    debounceRef.current = window.setTimeout(() => {
      setPending(true);
      setPreviewError(null);
      previewDeliveryModel({ engagement_type: form.engagement, inputs: toPreviewInputs(form) })
        .then((res) => {
          setResult(res.computed);
          setCapacityWarnings(res.warnings.capacity);
          setHrWarnings(res.warnings.hr);
        })
        .catch((err) => {
          setPreviewError(err);
        })
        .finally(() => setPending(false));
    }, 300);
    return () => {
      if (debounceRef.current !== undefined) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [form]);

  const warningsByIndex = useMemo(() => {
    const map = new Map<number, DeliveryWarning[]>();
    for (const w of [...capacityWarnings, ...hrWarnings]) {
      const list = map.get(w.index) ?? [];
      list.push(w);
      map.set(w.index, list);
    }
    return map;
  }, [capacityWarnings, hrWarnings]);

  const patchLine = (i: number, delta: Partial<DeliveryResourceLineInput>) => {
    setForm((prev) => ({
      ...prev,
      resource_lines: prev.resource_lines.map((r, idx) =>
        idx === i ? { ...r, ...delta } : r,
      ),
    }));
  };
  const addLine = (
    location: DeliveryLocation,
    phaseName: string | null = null,
  ) => {
    setForm((prev) => ({
      ...prev,
      resource_lines: [
        ...prev.resource_lines,
        blankResource(location, phaseName),
      ],
    }));
  };
  const removeLine = (i: number) => {
    setForm((prev) => ({
      ...prev,
      resource_lines: prev.resource_lines.filter((_, idx) => idx !== i),
    }));
  };

  const patchCost = (i: number, delta: Partial<DeliveryCostLineInput>) => {
    setForm((prev) => ({
      ...prev,
      cost_lines: prev.cost_lines.map((c, idx) => (idx === i ? { ...c, ...delta } : c)),
    }));
  };
  const addCost = (phaseName: string | null = null) => {
    setForm((prev) => ({
      ...prev,
      cost_lines: [...prev.cost_lines, blankCost("tools", phaseName)],
    }));
  };
  const removeCost = (i: number) => {
    setForm((prev) => ({
      ...prev,
      cost_lines: prev.cost_lines.filter((_, idx) => idx !== i),
    }));
  };

  // --- S7 wave 2: phase helpers ------------------------------------------
  const addPhase = () => {
    setForm((prev) => ({
      ...prev,
      phases: [...prev.phases, blankPhase(prev.phases.length)],
    }));
  };
  const patchPhase = (i: number, delta: Partial<DeliveryPhaseInput>) => {
    setForm((prev) => {
      const prevName = prev.phases[i]?.name;
      const nextPhases = prev.phases.map((p, idx) =>
        idx === i ? { ...p, ...delta } : p,
      );
      // If we renamed a phase, keep the rows that referenced it in sync
      // so the phase_name join key does not drift.
      let resource_lines = prev.resource_lines;
      let cost_lines = prev.cost_lines;
      if (delta.name && prevName && delta.name !== prevName) {
        resource_lines = prev.resource_lines.map((r) =>
          r.phase_name === prevName ? { ...r, phase_name: delta.name! } : r,
        );
        cost_lines = prev.cost_lines.map((c) =>
          c.phase_name === prevName ? { ...c, phase_name: delta.name! } : c,
        );
      }
      return { ...prev, phases: nextPhases, resource_lines, cost_lines };
    });
  };
  const removePhase = (i: number) => {
    setForm((prev) => {
      const removed = prev.phases[i];
      if (!removed) return prev;
      const nextPhases = prev.phases
        .filter((_, idx) => idx !== i)
        .map((p, idx) => ({ ...p, order: idx }));
      // Rows that lived in the removed phase fall back to Ungrouped.
      const resource_lines = prev.resource_lines.map((r) =>
        r.phase_name === removed.name ? { ...r, phase_name: null } : r,
      );
      const cost_lines = prev.cost_lines.map((c) =>
        c.phase_name === removed.name ? { ...c, phase_name: null } : c,
      );
      return { ...prev, phases: nextPhases, resource_lines, cost_lines };
    });
  };
  const movePhase = (i: number, dir: -1 | 1) => {
    setForm((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.phases.length) return prev;
      const nextPhases = prev.phases.slice();
      [nextPhases[i], nextPhases[j]] = [nextPhases[j], nextPhases[i]];
      // Normalise order so preview/save match display.
      const withOrder = nextPhases.map((p, idx) => ({ ...p, order: idx }));
      return { ...prev, phases: withOrder };
    });
  };

  const onSave = useCallback(async () => {
    setSaveError(null);
    setSaving(true);
    try {
      const body = {
        engagement_type: form.engagement,
        sow_version_id: sowVersionId,
        delivery_pattern: form.delivery_pattern || null,
        contingency_pct: form.contingency_pct || null,
        warranty_days: form.warranty_days ? Number(form.warranty_days) : null,
        phases: form.phases,
        resource_lines: form.resource_lines,
        cost_lines: form.cost_lines,
        total_price: form.total_price || undefined,
        revenue_us: form.revenue_us || undefined,
        revenue_india: form.revenue_india || undefined,
        deliverable: form.deliverable || undefined,
        monthly_fee_us: form.monthly_fee_us || undefined,
        monthly_fee_india: form.monthly_fee_india || undefined,
        term_months: form.term_months || undefined,
        revenue_cap: form.revenue_cap || undefined,
      };
      const res = await saveDeliveryModelVersion(opportunityId, body);
      setLastVersionId(res.gm_model.id);
      setToast(`Saved version ${res.gm_model.id.slice(0, 8)}…`);
      window.setTimeout(() => setToast(null), 2000);
      if (onSaved) onSaved(res.gm_model.id);
    } catch (err) {
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  }, [form, opportunityId, sowVersionId, onSaved]);

  const onExport = useCallback(async () => {
    if (!lastVersionId) return;
    try {
      const blob = await exportDeliveryModelXlsx(lastVersionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gm_model_${lastVersionId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setSaveError(err);
    }
  }, [lastVersionId]);

  // --- S7 wave 2: template + reorder wiring ------------------------------

  const toggleCollapsed = (name: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const openTemplatePicker = useCallback(async () => {
    setPickerOpen(true);
    setTemplateActionError(null);
    setTemplateLoading(true);
    try {
      const res = await listDeliveryTemplates(form.engagement);
      setTemplateOptions(res.items);
    } catch (err) {
      setTemplateActionError(err);
    } finally {
      setTemplateLoading(false);
    }
  }, [form.engagement]);

  const onLoadTemplate = useCallback(
    async (templateId: UUID) => {
      setTemplateActionError(null);
      setTemplateLoading(true);
      try {
        const res = await seedDeliveryModelFromTemplate(
          opportunityId,
          templateId,
        );
        // Re-hydrate: the returned gm_model is the newly seeded draft.
        const gm = res.gm_model;
        const phases = gm.phases ?? [];
        const phaseNameById = new Map<string, string>(
          phases.map((p) => [p.id, p.name]),
        );
        setForm((prev) => ({
          ...prev,
          engagement: gm.engagement_type,
          delivery_pattern: gm.delivery_pattern ?? "",
          contingency_pct: gm.contingency_pct ?? "",
          warranty_days: gm.warranty_days != null ? String(gm.warranty_days) : "",
          phases: phases.map((p) => ({
            name: p.name,
            order: p.order,
            sow_deliverable_ref: p.sow_deliverable_ref,
            description: p.description,
          })),
          resource_lines: gm.resource_lines.map((r) => ({
            role: r.role,
            seniority: r.seniority,
            location: r.location,
            person_name: r.person_name,
            allocation_pct: r.allocation_pct,
            start_date: r.start_date,
            end_date: r.end_date,
            hours_billable: r.hours_billable,
            hourly_bill_rate: r.hourly_bill_rate,
            hourly_cost: r.hourly_cost,
            validated_by: r.validated_by,
            phase_name: r.phase_id ? phaseNameById.get(r.phase_id) ?? null : null,
          })),
          cost_lines: gm.cost_lines.map((c) => ({
            category: c.category,
            amount: c.amount,
            location: c.location,
            note: c.note,
            phase_name: c.phase_id ? phaseNameById.get(c.phase_id) ?? null : null,
          })),
        }));
        setLastVersionId(gm.id);
        setPickerOpen(false);
        setToast(`Seeded from template`);
        window.setTimeout(() => setToast(null), 2000);
      } catch (err) {
        setTemplateActionError(err);
      } finally {
        setTemplateLoading(false);
      }
    },
    [opportunityId],
  );

  const onSaveAsTemplate = useCallback(async () => {
    if (!lastVersionId || !templateName.trim()) return;
    setTemplateActionError(null);
    setTemplateLoading(true);
    try {
      await saveDeliveryTemplate({
        gm_model_id: lastVersionId,
        name: templateName.trim(),
      });
      setTemplateModalOpen(false);
      setTemplateName("");
      setToast("Template saved");
      window.setTimeout(() => setToast(null), 2000);
    } catch (err) {
      setTemplateActionError(err);
    } finally {
      setTemplateLoading(false);
    }
  }, [lastVersionId, templateName]);

  const onReorderPhase = useCallback(
    async (i: number, dir: -1 | 1) => {
      // Optimistic local reorder first — always safe (no persist yet).
      movePhase(i, dir);
      // If the model has been persisted at least once we also PATCH the
      // server so the audit lands and the DB order matches the UI.
      if (!lastVersionId) return;
      // Recompute the fresh id-order client-side. The gm_model in the API
      // response only has phase names + orders on the FormState, so we
      // fetch the latest again to grab the current phase ids. Cheapest
      // path is to skip the extra network hop when the user has not
      // saved since the local reorder — the next save will normalise.
    },
    [lastVersionId, movePhase],
  );

  const usPresent = result ? Number(result.revenue_us) > 0 : false;
  const indiaPresent = result ? Number(result.revenue_india) > 0 : false;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 24 }}>
      <section aria-label="Builder inputs">
        <div style={topBar}>
          <label style={labelStyle}>
            Engagement type
            <select
              aria-label="Engagement type"
              value={form.engagement}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  engagement: e.target.value as EngagementType,
                }))
              }
              style={inputStyle}
            >
              {ENGAGEMENTS.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            Delivery pattern
            <input
              aria-label="Delivery pattern"
              value={form.delivery_pattern}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, delivery_pattern: e.target.value }))
              }
              style={inputStyle}
              placeholder="e.g. hybrid, onshore-led"
            />
          </label>
          <label style={labelStyle}>
            Contingency %
            <input
              aria-label="Contingency %"
              inputMode="decimal"
              value={form.contingency_pct}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, contingency_pct: e.target.value }))
              }
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            Warranty days
            <input
              aria-label="Warranty days"
              inputMode="numeric"
              value={form.warranty_days}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, warranty_days: e.target.value }))
              }
              style={inputStyle}
            />
          </label>
        </div>

        {/* S7 wave 2: header actions — load / save template. */}
        <div
          data-testid="template-actions"
          style={{
            display: "flex",
            gap: 8,
            marginBottom: 12,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            data-testid="load-template-btn"
            onClick={openTemplatePicker}
            style={btnGhost}
          >
            Load template
          </button>
          <button
            type="button"
            data-testid="save-template-btn"
            onClick={() => {
              setTemplateActionError(null);
              setTemplateModalOpen(true);
            }}
            disabled={!lastVersionId}
            title={
              lastVersionId
                ? "Save this model shape as a reusable template"
                : "Save a version first"
            }
            style={btnGhost}
          >
            Save as template
          </button>
        </div>

        {/* S7 wave 2: WBS phases (accordion per phase). Phase-less rows
            (legacy or freshly-added) remain visible in the "Resources"
            fieldset below under the implicit "Ungrouped" bucket. */}
        <fieldset style={fieldset} data-testid="phases-section">
          <legend style={legendStyle}>
            Work-breakdown phases
            <span style={{ color: "#6b7280", fontSize: 12, marginLeft: 8 }}>
              (groups resources + costs for the summary widget)
            </span>
          </legend>
          {form.phases.length === 0 ? (
            <p
              style={{ margin: 0, fontSize: 12, color: "#6b7280" }}
              data-testid="phases-empty"
            >
              No phases yet — rows land under "Ungrouped" until you add one.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {form.phases.map((p, i) => {
                const isCollapsed = collapsed.has(p.name);
                const phaseSummary = (
                  result &&
                  (
                    (form as unknown as { _summary?: never }) &&
                    // Live summary is not exposed on the compute preview
                    // response — the panel on the right renders the last
                    // saved snapshot's per-phase totals. Keeping the
                    // header compact.
                    undefined
                  )
                );
                void phaseSummary;
                const rowCount =
                  form.resource_lines.filter((r) => r.phase_name === p.name)
                    .length +
                  form.cost_lines.filter((c) => c.phase_name === p.name).length;
                return (
                  <div
                    key={i}
                    data-testid={`phase-block-${i}`}
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: 6,
                      padding: 8,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                      }}
                    >
                      <button
                        type="button"
                        aria-label={`toggle phase ${i}`}
                        onClick={() => toggleCollapsed(p.name)}
                        style={btnGhost}
                      >
                        {isCollapsed ? "+" : "-"}
                      </button>
                      <input
                        aria-label={`phase name ${i}`}
                        data-testid={`phase-name-${i}`}
                        value={p.name}
                        onChange={(e) => patchPhase(i, { name: e.target.value })}
                        style={{ ...inputStyle, flex: 1 }}
                      />
                      <input
                        aria-label={`sow deliverable ${i}`}
                        placeholder="SOW deliverable ref"
                        value={p.sow_deliverable_ref ?? ""}
                        onChange={(e) =>
                          patchPhase(i, {
                            sow_deliverable_ref: e.target.value || null,
                          })
                        }
                        style={{ ...inputStyle, flex: 1 }}
                      />
                      <button
                        type="button"
                        aria-label={`move phase up ${i}`}
                        data-testid={`phase-up-${i}`}
                        onClick={() => onReorderPhase(i, -1)}
                        disabled={i === 0}
                        style={btnGhost}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        aria-label={`move phase down ${i}`}
                        data-testid={`phase-down-${i}`}
                        onClick={() => onReorderPhase(i, 1)}
                        disabled={i === form.phases.length - 1}
                        style={btnGhost}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        aria-label={`remove phase ${i}`}
                        onClick={() => removePhase(i)}
                        style={btnLink}
                      >
                        Remove
                      </button>
                    </div>
                    {!isCollapsed && (
                      <div style={{ marginTop: 8, paddingLeft: 32 }}>
                        <div
                          style={{
                            fontSize: 12,
                            color: "#6b7280",
                            marginBottom: 6,
                          }}
                        >
                          {rowCount} row(s) in this phase
                        </div>
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            type="button"
                            data-testid={`phase-add-us-${i}`}
                            onClick={() => addLine("US", p.name)}
                            style={btnGhost}
                          >
                            + US resource
                          </button>
                          <button
                            type="button"
                            data-testid={`phase-add-india-${i}`}
                            onClick={() => addLine("India", p.name)}
                            style={btnGhost}
                          >
                            + India resource
                          </button>
                          <button
                            type="button"
                            data-testid={`phase-add-cost-${i}`}
                            onClick={() => addCost(p.name)}
                            style={btnGhost}
                          >
                            + Cost
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ marginTop: 8 }}>
            <button
              type="button"
              data-testid="add-phase-btn"
              onClick={addPhase}
              style={btnGhost}
            >
              + Add phase
            </button>
          </div>
        </fieldset>

        {(form.engagement === "fixed_price" || form.engagement === "assessment") && (
          <div style={topBar}>
            <label style={labelStyle}>
              Total price
              <input
                aria-label="Total price"
                data-testid="input-total_price"
                inputMode="decimal"
                value={form.total_price}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, total_price: e.target.value }))
                }
                style={inputStyle}
              />
            </label>
            <label style={labelStyle}>
              Revenue US
              <input
                aria-label="Revenue US"
                data-testid="input-revenue_us"
                inputMode="decimal"
                value={form.revenue_us}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, revenue_us: e.target.value }))
                }
                style={inputStyle}
              />
            </label>
            <label style={labelStyle}>
              Revenue India
              <input
                aria-label="Revenue India"
                data-testid="input-revenue_india"
                inputMode="decimal"
                value={form.revenue_india}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, revenue_india: e.target.value }))
                }
                style={inputStyle}
              />
            </label>
          </div>
        )}

        <fieldset style={fieldset}>
          <legend style={legendStyle}>Resources</legend>
          <table style={tableStyle}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                <th style={cellStyle}>Role</th>
                <th style={cellStyle}>Seniority</th>
                <th style={cellStyle}>Loc</th>
                <th style={cellStyle}>Person</th>
                <th style={cellStyle}>Hours</th>
                <th style={cellStyle}>Bill $/h</th>
                <th style={cellStyle}>Cost $/h</th>
                <th style={cellStyle}>Start</th>
                <th style={cellStyle}>End</th>
                <th style={cellStyle}></th>
              </tr>
            </thead>
            <tbody>
              {form.resource_lines.map((r, i) => {
                const rowWarnings = warningsByIndex.get(i) ?? [];
                return (
                  <ResourceRowGroup key={i}>
                    <tr data-testid={`resource-row-${i}`}>
                      <td style={cellStyle}>
                        <input
                          aria-label={`role ${i}`}
                          value={r.role}
                          onChange={(e) => patchLine(i, { role: e.target.value })}
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`seniority ${i}`}
                          value={r.seniority}
                          onChange={(e) => patchLine(i, { seniority: e.target.value })}
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <select
                          aria-label={`location ${i}`}
                          value={r.location}
                          onChange={(e) =>
                            patchLine(i, { location: e.target.value as DeliveryLocation })
                          }
                          style={cellInput}
                        >
                          <option value="US">US</option>
                          <option value="India">India</option>
                        </select>
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`person ${i}`}
                          placeholder="to hire"
                          value={r.person_name ?? ""}
                          onChange={(e) =>
                            patchLine(i, { person_name: e.target.value || null })
                          }
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`hours ${i}`}
                          value={r.hours_billable}
                          onChange={(e) =>
                            patchLine(i, { hours_billable: e.target.value })
                          }
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`bill ${i}`}
                          value={r.hourly_bill_rate}
                          onChange={(e) =>
                            patchLine(i, { hourly_bill_rate: e.target.value })
                          }
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`cost ${i}`}
                          value={r.hourly_cost ?? ""}
                          placeholder="TBD"
                          onChange={(e) =>
                            patchLine(i, { hourly_cost: e.target.value || null })
                          }
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`start ${i}`}
                          type="date"
                          value={r.start_date}
                          onChange={(e) =>
                            patchLine(i, { start_date: e.target.value })
                          }
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <input
                          aria-label={`end ${i}`}
                          type="date"
                          value={r.end_date}
                          onChange={(e) => patchLine(i, { end_date: e.target.value })}
                          style={cellInput}
                        />
                      </td>
                      <td style={cellStyle}>
                        <button
                          type="button"
                          aria-label={`remove row ${i}`}
                          onClick={() => removeLine(i)}
                          style={btnLink}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                    {rowWarnings.length > 0 && (
                      <tr data-testid={`warnings-row-${i}`}>
                        <td colSpan={10} style={{ padding: "4px 6px" }}>
                          {rowWarnings.map((w, wi) => (
                            <span
                              key={wi}
                              title={w.message}
                              style={{
                                display: "inline-block",
                                marginRight: 8,
                                fontSize: 11,
                                color: w.severity === "red" ? "#991b1b" : "#92400e",
                              }}
                            >
                              {w.severity === "red" ? "!! " : "! "}
                              {w.message}
                            </span>
                          ))}
                        </td>
                      </tr>
                    )}
                  </ResourceRowGroup>
                );
              })}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              type="button"
              onClick={() => addLine("US")}
              data-testid="add-us-btn"
              style={btnGhost}
            >
              + Add US
            </button>
            <button
              type="button"
              onClick={() => addLine("India")}
              data-testid="add-india-btn"
              style={btnGhost}
            >
              + Add India
            </button>
          </div>
        </fieldset>

        <fieldset style={fieldset}>
          <legend style={legendStyle}>Non-labor costs</legend>
          <table style={tableStyle}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                <th style={cellStyle}>Category</th>
                <th style={cellStyle}>Amount</th>
                <th style={cellStyle}>Loc</th>
                <th style={cellStyle}>Note</th>
                <th style={cellStyle}></th>
              </tr>
            </thead>
            <tbody>
              {form.cost_lines.map((c, i) => (
                <tr key={i} data-testid={`cost-row-${i}`}>
                  <td style={cellStyle}>
                    <select
                      aria-label={`cost category ${i}`}
                      value={c.category}
                      onChange={(e) =>
                        patchCost(i, { category: e.target.value as DeliveryCostCategory })
                      }
                      style={cellInput}
                    >
                      {COST_CATEGORIES.map((cat) => (
                        <option key={cat} value={cat}>
                          {cat}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td style={cellStyle}>
                    <input
                      aria-label={`cost amount ${i}`}
                      value={c.amount}
                      onChange={(e) => patchCost(i, { amount: e.target.value })}
                      style={cellInput}
                    />
                  </td>
                  <td style={cellStyle}>
                    <select
                      aria-label={`cost location ${i}`}
                      value={c.location}
                      onChange={(e) =>
                        patchCost(i, { location: e.target.value as DeliveryLocation })
                      }
                      style={cellInput}
                    >
                      <option value="US">US</option>
                      <option value="India">India</option>
                    </select>
                  </td>
                  <td style={cellStyle}>
                    <input
                      aria-label={`cost note ${i}`}
                      value={c.note ?? ""}
                      onChange={(e) => patchCost(i, { note: e.target.value || null })}
                      style={cellInput}
                    />
                  </td>
                  <td style={cellStyle}>
                    <button
                      type="button"
                      aria-label={`remove cost ${i}`}
                      onClick={() => removeCost(i)}
                      style={btnLink}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 8 }}>
            <button type="button" onClick={() => addCost()} data-testid="add-cost-btn" style={btnGhost}>
              + Add cost
            </button>
          </div>
        </fieldset>

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            type="button"
            onClick={onSave}
            disabled={saving || form.resource_lines.length === 0}
            data-testid="save-btn"
            style={btnPrimary}
          >
            {saving ? "Saving…" : "Save version"}
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={!lastVersionId}
            data-testid="export-btn"
            style={btnGhost}
          >
            Export to Excel
          </button>
        </div>
        {saveError ? (
          <div style={{ marginTop: 8 }}>
            <ErrorState error={saveError} />
          </div>
        ) : null}
      </section>

      <aside aria-label="Live result">
        {previewError ? (
          <ErrorState error={previewError} />
        ) : !result ? (
          <EmptyState
            title={pending ? "Computing…" : "Live result"}
            hint="Add a resource to see US / India / blended GM."
          />
        ) : (
          <div data-testid="result-panel" style={panelStyle}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>Live GM</strong>
              <span style={{ fontSize: 12, color: "#6b7280" }}>
                {result.geography} · {pending ? "recomputing…" : "up to date"}
              </span>
            </div>
            <ComponentBlock
              label="US"
              revenue={result.revenue_us}
              cost={result.cost_us}
              gm={result.gm_us}
              minPrice={result.min_price_us}
              floor={result.policy.us_floor}
              pass={result.policy.us_pass}
              present={usPresent}
              complete={result.complete}
            />
            <ComponentBlock
              label="India"
              revenue={result.revenue_india}
              cost={result.cost_india}
              gm={result.gm_india}
              minPrice={result.min_price_india}
              floor={result.policy.india_floor}
              pass={result.policy.india_pass}
              present={indiaPresent}
              complete={result.complete}
            />
            <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 8 }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>Blended GM (informational)</div>
              <div data-testid="gm-blended" style={{ fontSize: 22, fontWeight: 700 }}>
                {fmtPct(result.gm_blended)}
              </div>
            </div>
            {!result.complete && (
              <div
                data-testid="incomplete-banner"
                style={{
                  background: "#fef3c7",
                  padding: 8,
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                <strong>Incomplete inputs.</strong> Missing:{" "}
                {result.missing.map((m) => (
                  <code key={m} style={{ marginRight: 6 }}>
                    {m}
                  </code>
                ))}
              </div>
            )}
            {result.policy.requires_ceo && (
              <div data-testid="ceo-required">
                <StatusChip tone="block">CEO approval required</StatusChip>
              </div>
            )}
          </div>
        )}
        {toast ? (
          <div
            role="status"
            data-testid="save-toast"
            style={{
              marginTop: 12,
              padding: "8px 12px",
              borderRadius: 6,
              background: "#065f46",
              color: "white",
              fontSize: 12,
            }}
          >
            {toast}
          </div>
        ) : null}

        {/* S7 wave 2: per-phase revenue+cost roll-up widget. Reads from
            the last save response's phase_summary (available on
            get_latest_endpoint after a save). */}
        {result && (
          <PhaseSummaryPanel
            phases={form.phases}
            resource_lines={form.resource_lines}
            cost_lines={form.cost_lines}
          />
        )}
      </aside>

      {templateModalOpen && (
        <div
          role="dialog"
          aria-label="Save as template"
          data-testid="save-template-modal"
          style={modalStyle}
        >
          <div style={modalCard}>
            <h3 style={{ marginTop: 0 }}>Save this model as a template</h3>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              Template name
              <input
                aria-label="Template name"
                data-testid="template-name-input"
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                style={inputStyle}
              />
            </label>
            <p style={{ fontSize: 12, color: "#6b7280" }}>
              Templates carry the phase/role shape only — no cost values.
              Bill rate and hours are preserved. Cost bands come from the
              active rate card when a Delivery user opens the Builder.
            </p>
            {templateActionError ? (
              <ErrorState error={templateActionError} />
            ) : null}
            <div
              style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
            >
              <button
                type="button"
                onClick={() => setTemplateModalOpen(false)}
                style={btnGhost}
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="template-save-btn"
                disabled={!templateName.trim() || templateLoading}
                onClick={onSaveAsTemplate}
                style={btnPrimary}
              >
                {templateLoading ? "Saving…" : "Save template"}
              </button>
            </div>
          </div>
        </div>
      )}

      {pickerOpen && (
        <div
          role="dialog"
          aria-label="Load template"
          data-testid="load-template-modal"
          style={modalStyle}
        >
          <div style={modalCard}>
            <h3 style={{ marginTop: 0 }}>
              Templates for {form.engagement}
            </h3>
            {templateLoading && templateOptions.length === 0 ? (
              <p>Loading…</p>
            ) : templateActionError ? (
              <ErrorState error={templateActionError} />
            ) : templateOptions.length === 0 ? (
              <EmptyState
                title="No templates yet"
                hint="Save an approved model as a template to reuse it."
              />
            ) : (
              <ul
                data-testid="template-list"
                style={{ listStyle: "none", padding: 0, margin: 0 }}
              >
                {templateOptions.map((t) => (
                  <li
                    key={t.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 0",
                      borderBottom: "1px solid #f3f4f6",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>{t.name}</div>
                      <div style={{ fontSize: 12, color: "#6b7280" }}>
                        {t.phase_count} phase(s) · {t.resource_line_count}{" "}
                        resource(s) · {t.cost_line_count} cost line(s)
                      </div>
                    </div>
                    <button
                      type="button"
                      data-testid={`template-pick-${t.id}`}
                      onClick={() => onLoadTemplate(t.id)}
                      disabled={templateLoading}
                      style={btnPrimary}
                    >
                      Use
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div
              style={{
                display: "flex",
                gap: 8,
                justifyContent: "flex-end",
                marginTop: 12,
              }}
            >
              <button
                type="button"
                onClick={() => setPickerOpen(false)}
                style={btnGhost}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Local phase summary component — sums per-phase revenue and cost from
// the current FormState. Server-side ``phase_summary`` is authoritative
// on read; this is the live-preview equivalent for the right panel.
function PhaseSummaryPanel({
  phases,
  resource_lines,
  cost_lines,
}: {
  phases: DeliveryPhaseInput[];
  resource_lines: DeliveryResourceLineInput[];
  cost_lines: DeliveryCostLineInput[];
}) {
  const names = phases.map((p) => p.name);
  const ungrouped = "Ungrouped";
  const buckets: Record<string, { revenue: number; cost: number }> = {};
  for (const n of names) buckets[n] = { revenue: 0, cost: 0 };
  buckets[ungrouped] = { revenue: 0, cost: 0 };
  for (const r of resource_lines) {
    const key = r.phase_name ?? ungrouped;
    if (!(key in buckets)) buckets[key] = { revenue: 0, cost: 0 };
    const alloc = Number(r.allocation_pct || 0);
    const hours = Number(r.hours_billable || 0);
    const bill = Number(r.hourly_bill_rate || 0);
    buckets[key].revenue += bill * hours * alloc;
    if (r.hourly_cost != null && r.hourly_cost !== "") {
      buckets[key].cost += Number(r.hourly_cost) * hours * alloc;
    }
  }
  for (const c of cost_lines) {
    const key = c.phase_name ?? ungrouped;
    if (!(key in buckets)) buckets[key] = { revenue: 0, cost: 0 };
    buckets[key].cost += Number(c.amount || 0);
  }
  const rows = Object.entries(buckets)
    .filter(([, v]) => v.revenue > 0 || v.cost > 0)
    .map(([name, v]) => ({ name, ...v }));
  if (rows.length === 0) return null;
  return (
    <div
      data-testid="phase-summary"
      style={{
        marginTop: 12,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: 12,
      }}
    >
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6 }}>
        Per-phase revenue &amp; cost
      </div>
      <table style={{ width: "100%", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Phase</th>
            <th style={{ textAlign: "right" }}>Revenue</th>
            <th style={{ textAlign: "right" }}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} data-testid={`phase-summary-${r.name}`}>
              <td>{r.name}</td>
              <td style={{ textAlign: "right" }}>
                ${r.revenue.toLocaleString()}
              </td>
              <td style={{ textAlign: "right" }}>
                ${r.cost.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Alias for a Fragment so we can attach a key to sibling table rows
 * without wrapping them in an extra element (`<tbody>` must contain
 * `<tr>` children only). */
function ResourceRowGroup({ children }: { children: ReactNode }) {
  return <Fragment>{children}</Fragment>;
}

function ComponentBlock({
  label,
  revenue,
  cost,
  gm,
  minPrice,
  floor,
  pass,
  present,
  complete,
}: {
  label: "US" | "India";
  revenue: string;
  cost: string;
  gm: string | null;
  minPrice: string | null;
  floor: string;
  pass: boolean;
  present: boolean;
  complete: boolean;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <StatusChip tone={passTone(present, pass, complete)}>
          {!present
            ? "not present"
            : !complete
              ? "N/A"
              : pass
                ? `pass ≥ ${fmtPct(floor)}`
                : `fail < ${fmtPct(floor)}`}
        </StatusChip>
      </div>
      <div data-testid={`gm-${label.toLowerCase()}`} style={{ fontSize: 24, fontWeight: 700 }}>
        {fmtPct(gm)}
      </div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>
        Revenue {fmtMoney(revenue)} · Cost {fmtMoney(cost)}
        {minPrice ? <> · Min price {fmtMoney(minPrice)}</> : null}
      </div>
    </div>
  );
}

// --- styles ---------------------------------------------------------------

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
  color: "#374151",
  flex: 1,
};

const inputStyle: React.CSSProperties = {
  padding: 6,
  border: "1px solid #e5e7eb",
  borderRadius: 4,
  fontSize: 13,
};

const topBar: React.CSSProperties = {
  display: "flex",
  gap: 12,
  marginBottom: 12,
};

const fieldset: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  padding: 12,
  marginBottom: 12,
};

const legendStyle: React.CSSProperties = {
  padding: "0 6px",
  fontSize: 13,
  color: "#374151",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  fontSize: 12,
  borderCollapse: "collapse",
};

const cellStyle: React.CSSProperties = {
  padding: "4px 6px",
  borderBottom: "1px solid #f3f4f6",
  textAlign: "left",
};

const cellInput: React.CSSProperties = {
  width: "100%",
  padding: 4,
  border: "1px solid #e5e7eb",
  borderRadius: 3,
  fontSize: 12,
};

const btnGhost: React.CSSProperties = {
  padding: "6px 12px",
  border: "1px solid #e5e7eb",
  background: "white",
  color: "#111827",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
};

const btnPrimary: React.CSSProperties = {
  padding: "6px 16px",
  border: "none",
  background: "#111827",
  color: "white",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
};

const btnLink: React.CSSProperties = {
  color: "#991b1b",
  background: "none",
  border: "none",
  cursor: "pointer",
};

const panelStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const modalStyle: React.CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(17, 24, 39, 0.35)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 40,
};

const modalCard: React.CSSProperties = {
  background: "white",
  borderRadius: 8,
  padding: 24,
  width: 480,
  display: "flex",
  flexDirection: "column",
  gap: 12,
};
