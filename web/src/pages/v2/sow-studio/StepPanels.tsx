/**
 * Five step panels for the New SOW studio.
 *
 * Every input is controlled by the parent's `useReducer` state so a
 * mid-step network failure never loses what the user typed (spec §4).
 * File uploads only *stage* — the actual PUT to S3 happens on advance
 * so a picked-but-not-advanced file also survives back-nav.
 */
import { useEffect, useMemo, useState } from "react";
import { Upload, RefreshCcw } from "lucide-react";
import {
  computeGm,
  getGmSchema,
  listClients,
  listUsers,
  type ClientListRow,
  type EngagementType,
  type SandboxSchema,
  type UserRow,
} from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";
import { cn } from "../../../lib/cn";
import { TEMPLATES } from "./templates";
import type { StudioState } from "./steps";

export interface StepPanelProps {
  state: StudioState;
  patch: (fn: (s: StudioState) => StudioState) => void;
}

/* --------------------------------- Step 1 --------------------------------- */

export function SourceStep({ state, patch }: StepPanelProps) {
  const [clientQuery, setClientQuery] = useState(state.source.clientName);
  const [clients, setClients] = useState<ClientListRow[]>([]);
  useEffect(() => {
    let cancelled = false;
    listClients({ search: clientQuery, size: 10 })
      .then((r) => {
        if (!cancelled) setClients(r.items);
      })
      .catch(() => {
        if (!cancelled) setClients([]);
      });
    return () => {
      cancelled = true;
    };
  }, [clientQuery]);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="client-search">Client</Label>
          <Input
            id="client-search"
            value={clientQuery}
            onChange={(e) => {
              setClientQuery(e.target.value);
              patch((s) => ({
                ...s,
                source: { ...s.source, clientName: e.target.value },
              }));
            }}
            placeholder="Start typing…"
            aria-describedby="client-help"
          />
          <p id="client-help" className="mt-1 text-secondary text-text-secondary">
            Pick an existing client so agreements can be matched.
          </p>
          {clients.length ? (
            <ul className="mt-2 max-h-40 overflow-y-auto rounded-panel border border-divider bg-surface">
              {clients.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() =>
                      patch((s) => ({
                        ...s,
                        source: {
                          ...s.source,
                          clientId: c.id,
                          clientName: c.name,
                        },
                      }))
                    }
                    className={cn(
                      "block w-full px-3 py-2 text-left text-body hover:bg-primary-subtle",
                      state.source.clientId === c.id && "bg-primary-subtle",
                    )}
                  >
                    {c.name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div>
          <Label htmlFor="sow-title">SOW title</Label>
          <Input
            id="sow-title"
            value={state.source.sowTitle}
            onChange={(e) =>
              patch((s) => ({
                ...s,
                source: { ...s.source, sowTitle: e.target.value },
              }))
            }
            placeholder="e.g. Northstar Analytics — Phase 1"
          />
        </div>
      </div>

      <fieldset className="rounded-panel border border-divider p-4">
        <legend className="px-2 text-secondary font-medium text-text-secondary">
          Source
        </legend>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <StagedFileInput state={state} patch={patch} />
          <label
            className={cn(
              "flex cursor-pointer flex-col gap-1 rounded-panel border border-input-border bg-surface p-3",
              state.source.kind === "structured" && "border-primary",
            )}
          >
            <div className="flex items-center gap-2">
              <input
                type="radio"
                name="source-kind"
                checked={state.source.kind === "structured"}
                onChange={() =>
                  patch((s) => ({
                    ...s,
                    source: {
                      ...s.source,
                      kind: "structured",
                      stagedFileName: null,
                      stagedFileSize: null,
                    },
                  }))
                }
              />
              <span className="font-medium">Start from structured draft</span>
            </div>
            <span className="text-secondary text-text-secondary">
              Skip upload; fill scope, terms and GM directly.
            </span>
          </label>
        </div>
        <p className="mt-3 text-secondary text-text-secondary">
          Uploading a file only <em>stages</em> it. Extraction runs at submit
          via the SOW extract worker; no field is claimed as verified.
        </p>
      </fieldset>

      <fieldset className="rounded-panel border border-divider p-4">
        <legend className="px-2 text-secondary font-medium text-text-secondary">
          Engagement template
        </legend>
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          {TEMPLATES.map((t) => {
            const selected = state.source.engagementType === t.id;
            return (
              <label
                key={t.id}
                data-testid={`template-${t.id}`}
                className={cn(
                  "flex cursor-pointer flex-col gap-1 rounded-panel border border-input-border bg-surface p-3",
                  selected && "border-primary bg-primary-subtle",
                )}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="engagement-type"
                    checked={selected}
                    onChange={() =>
                      patch((s) => ({
                        ...s,
                        source: { ...s.source, engagementType: t.id },
                        gm: { ...s.gm, inputs: {}, lastComputedAt: null },
                      }))
                    }
                  />
                  <span className="font-medium">{t.name}</span>
                </div>
                <span className="text-secondary text-text-secondary">
                  {t.hint}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
    </div>
  );
}

function StagedFileInput({ state, patch }: StepPanelProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer flex-col gap-1 rounded-panel border border-input-border bg-surface p-3",
        state.source.kind === "file" && "border-primary",
      )}
    >
      <div className="flex items-center gap-2">
        <input
          type="radio"
          name="source-kind"
          checked={state.source.kind === "file"}
          onChange={() =>
            patch((s) => ({
              ...s,
              source: { ...s.source, kind: "file" },
            }))
          }
        />
        <Upload className="h-4 w-4 text-text-secondary" aria-hidden />
        <span className="font-medium">Upload SOW file</span>
      </div>
      <input
        type="file"
        accept="application/pdf,.pdf,.docx"
        aria-label="Stage SOW file"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          patch((s) => ({
            ...s,
            source: {
              ...s.source,
              kind: "file",
              stagedFileName: f.name,
              stagedFileSize: f.size,
            },
          }));
        }}
        className="text-secondary text-text-secondary"
      />
      {state.source.stagedFileName ? (
        <span className="text-secondary text-text-secondary">
          Staged: {state.source.stagedFileName}
          {state.source.stagedFileSize
            ? ` · ${Math.round(state.source.stagedFileSize / 1024)} kB`
            : ""}
        </span>
      ) : null}
    </label>
  );
}

/* --------------------------------- Step 2 --------------------------------- */

export function ScopeStep({ state, patch }: StepPanelProps) {
  const s = state.scope;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ScopeField
        id="scope-summary"
        label="Verified scope summary"
        value={s.scopeSummary}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, scopeSummary: v } }))}
        textarea
        help="What are we contracting to deliver, in plain language."
      />
      <ScopeField
        id="deliverables"
        label="Deliverables"
        value={s.deliverables}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, deliverables: v } }))}
        textarea
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <ScopeField
          id="price"
          label="Proposed price"
          value={s.price}
          onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, price: v } }))}
          inputMode="decimal"
        />
        <ScopeField
          id="currency"
          label="Currency"
          value={s.currency}
          onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, currency: v } }))}
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <ScopeField
          id="term-start"
          label="Term start"
          value={s.termStart}
          onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, termStart: v } }))}
          type="date"
        />
        <ScopeField
          id="term-end"
          label="Term end"
          value={s.termEnd}
          onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, termEnd: v } }))}
          type="date"
        />
      </div>
      <ScopeField
        id="acceptance"
        label="Acceptance criteria"
        value={s.acceptance}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, acceptance: v } }))}
        textarea
      />
      <ScopeField
        id="exclusions"
        label="Exclusions"
        value={s.exclusions}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, exclusions: v } }))}
        textarea
      />
      <ScopeField
        id="payment"
        label="Payment terms"
        value={s.payment}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, payment: v } }))}
      />
      <ScopeField
        id="notice"
        label="Notice period"
        value={s.notice}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, notice: v } }))}
      />
      <ScopeField
        id="signatories"
        label="Signatories"
        value={s.signatories}
        onChange={(v) => patch((p) => ({ ...p, scope: { ...p.scope, signatories: v } }))}
        textarea
      />
    </div>
  );
}

interface ScopeFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  textarea?: boolean;
  help?: string;
  inputMode?: "decimal" | "text";
  type?: string;
}

function ScopeField({
  id,
  label,
  value,
  onChange,
  textarea,
  help,
  inputMode,
  type,
}: ScopeFieldProps) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      {textarea ? (
        <textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className={cn(
            "mt-1 flex w-full rounded-control border border-input-border bg-surface px-3 py-2",
            "text-body text-text placeholder:text-text-secondary focus-visible:outline-focus",
          )}
        />
      ) : (
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1"
          inputMode={inputMode}
          type={type}
        />
      )}
      {help ? (
        <p className="mt-1 text-secondary text-text-secondary">{help}</p>
      ) : null}
    </div>
  );
}

/* --------------------------------- Step 3 --------------------------------- */

export function GmStep({ state, patch }: StepPanelProps) {
  const [schema, setSchema] = useState<SandboxSchema | null>(null);
  const [busy, setBusy] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);
  const et = state.source.engagementType;

  useEffect(() => {
    if (!et) {
      setSchema(null);
      return;
    }
    let cancelled = false;
    getGmSchema(et)
      .then((s) => {
        if (!cancelled) setSchema(s);
      })
      .catch(() => {
        if (!cancelled) setSchema(null);
      });
    return () => {
      cancelled = true;
    };
  }, [et]);

  async function runCompute() {
    if (!et) return;
    setBusy(true);
    setComputeError(null);
    try {
      const res = await computeGm({
        engagement_type: et,
        inputs: {
          ...state.gm.inputs,
          revenue_us: state.gm.revenueUs || undefined,
          revenue_india: state.gm.revenueIndia || undefined,
        },
      });
      patch((s) => ({
        ...s,
        gm: { ...s.gm, lastComputedAt: res.computed_at },
      }));
    } catch (e) {
      setComputeError(e instanceof Error ? e.message : "Compute failed");
    } finally {
      setBusy(false);
    }
  }

  if (!et) {
    return (
      <p className="rounded-panel border border-warning/40 bg-warning-surface p-3 text-warning">
        Pick an engagement template in step 1 before building the GM.
      </p>
    );
  }

  return (
    <div className="space-y-4" data-testid={`gm-schema-${et}`}>
      <p className="text-secondary text-text-secondary">
        Schema loaded from <code>getGmSchema(&quot;{et}&quot;)</code>. Every
        field is server-defined; changing the engagement template refreshes
        this list.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label htmlFor="rev-us">Revenue — US</Label>
          <Input
            id="rev-us"
            inputMode="decimal"
            value={state.gm.revenueUs}
            onChange={(e) =>
              patch((s) => ({ ...s, gm: { ...s.gm, revenueUs: e.target.value } }))
            }
          />
        </div>
        <div>
          <Label htmlFor="rev-india">Revenue — India</Label>
          <Input
            id="rev-india"
            inputMode="decimal"
            value={state.gm.revenueIndia}
            onChange={(e) =>
              patch((s) => ({
                ...s,
                gm: { ...s.gm, revenueIndia: e.target.value },
              }))
            }
          />
        </div>
      </div>

      {schema ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {schema.fields.map((f) => (
            <div key={f.name}>
              <Label htmlFor={`gm-${f.name}`}>
                {f.label}
                {f.required ? " *" : ""}
              </Label>
              <Input
                id={`gm-${f.name}`}
                value={state.gm.inputs[f.name] ?? ""}
                onChange={(e) =>
                  patch((s) => ({
                    ...s,
                    gm: {
                      ...s.gm,
                      inputs: { ...s.gm.inputs, [f.name]: e.target.value },
                    },
                  }))
                }
              />
              {f.help ? (
                <p className="mt-1 text-secondary text-text-secondary">
                  {f.help}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-secondary text-text-secondary">
          Schema unavailable — Margin lab computes GM once you advance.
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button type="button" variant="secondary" onClick={runCompute} disabled={busy}>
          <RefreshCcw className="h-4 w-4" aria-hidden />
          {busy ? "Computing…" : "Compute GM"}
        </Button>
        {state.gm.lastComputedAt ? (
          <span className="text-secondary text-text-secondary">
            Last compute: {new Date(state.gm.lastComputedAt).toLocaleString()}
          </span>
        ) : null}
      </div>
      {computeError ? (
        <p role="alert" className="text-danger">
          {computeError}
        </p>
      ) : null}
    </div>
  );
}

/* --------------------------------- Step 4 --------------------------------- */

export function RoutingStep({ state, patch }: StepPanelProps) {
  const [users, setUsers] = useState<UserRow[]>([]);
  useEffect(() => {
    let cancelled = false;
    listUsers({ size: 100 })
      .then((r) => {
        if (!cancelled) setUsers(r.items);
      })
      .catch(() => {
        if (!cancelled) setUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const byGroup = useMemo(() => {
    const g: Record<string, UserRow[]> = {};
    for (const u of users) {
      for (const grp of u.groups) {
        g[grp] = g[grp] ?? [];
        g[grp].push(u);
      }
    }
    return g;
  }, [users]);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <ReviewerSelect
          id="delivery-owner"
          label="Delivery reviewer"
          value={state.routing.deliveryOwnerId}
          users={byGroup.Delivery ?? users}
          onChange={(id) =>
            patch((s) => ({
              ...s,
              routing: { ...s.routing, deliveryOwnerId: id },
            }))
          }
        />
        <ReviewerSelect
          id="hr-owner"
          label="HR reviewer"
          value={state.routing.hrOwnerId}
          users={byGroup.HR ?? users}
          onChange={(id) =>
            patch((s) => ({ ...s, routing: { ...s.routing, hrOwnerId: id } }))
          }
        />
        <ReviewerSelect
          id="finance-owner"
          label="Finance reviewer"
          value={state.routing.financeOwnerId}
          users={byGroup.Finance ?? users}
          onChange={(id) =>
            patch((s) => ({
              ...s,
              routing: { ...s.routing, financeOwnerId: id },
            }))
          }
        />
        <ReviewerSelect
          id="legal-owner"
          label="Legal reviewer"
          value={state.routing.legalOwnerId}
          users={byGroup.Legal ?? users}
          onChange={(id) =>
            patch((s) => ({ ...s, routing: { ...s.routing, legalOwnerId: id } }))
          }
        />
      </div>

      <label className="flex items-center gap-2 text-body">
        <input
          type="checkbox"
          checked={state.routing.ceoRequired}
          onChange={(e) =>
            patch((s) => ({
              ...s,
              routing: { ...s.routing, ceoRequired: e.target.checked },
            }))
          }
          data-testid="ceo-required"
        />
        <span>Below-floor package — route to CEO exception</span>
      </label>
      {state.routing.ceoRequired ? (
        <ReviewerSelect
          id="ceo-owner"
          label="CEO approver"
          value={state.routing.ceoOwnerId}
          users={byGroup.CEO ?? users}
          onChange={(id) =>
            patch((s) => ({ ...s, routing: { ...s.routing, ceoOwnerId: id } }))
          }
        />
      ) : null}

      <div>
        <Label htmlFor="due-date">Review due date</Label>
        <Input
          id="due-date"
          type="date"
          value={state.routing.dueDate}
          onChange={(e) =>
            patch((s) => ({
              ...s,
              routing: { ...s.routing, dueDate: e.target.value },
            }))
          }
          className="mt-1 max-w-xs"
        />
      </div>
    </div>
  );
}

interface ReviewerSelectProps {
  id: string;
  label: string;
  value: string | null;
  users: UserRow[];
  onChange: (id: string | null) => void;
}

function ReviewerSelect({ id, label, value, users, onChange }: ReviewerSelectProps) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className={cn(
          "mt-1 flex h-10 w-full rounded-control border border-input-border",
          "bg-surface px-3 text-body text-text focus-visible:outline-focus",
        )}
      >
        <option value="">Unassigned</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.name} · {u.email}
          </option>
        ))}
      </select>
    </div>
  );
}

/* --------------------------------- Step 5 --------------------------------- */

export function SubmitStep({
  state,
  patch: _patch,
  onSubmit,
  submitting,
  submitError,
}: StepPanelProps & {
  onSubmit: () => void | Promise<void>;
  submitting: boolean;
  submitError: string | null;
}) {
  const template = TEMPLATES.find((t) => t.id === state.source.engagementType);
  return (
    <div className="space-y-4">
      <section className="rounded-panel border border-divider bg-surface p-4">
        <h3 className="text-section text-text">Frozen versions</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2 text-body">
          <div>
            <dt className="text-secondary text-text-secondary">SOW version</dt>
            <dd className="tnum">
              {state.source.sowVersionId ?? "Draft (assigned at submit)"}
            </dd>
          </div>
          <div>
            <dt className="text-secondary text-text-secondary">GM computed</dt>
            <dd className="tnum">
              {state.gm.lastComputedAt
                ? new Date(state.gm.lastComputedAt).toLocaleString()
                : "not computed"}
            </dd>
          </div>
        </dl>
      </section>

      <section className="rounded-panel border border-divider bg-surface p-4">
        <h3 className="text-section text-text">Commercial summary</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2 text-body">
          <SummaryRow label="Client" value={state.source.clientName || "—"} />
          <SummaryRow label="SOW" value={state.source.sowTitle || "—"} />
          <SummaryRow label="Template" value={template?.name ?? "—"} />
          <SummaryRow
            label="Price"
            value={
              state.scope.price
                ? `${state.scope.price} ${state.scope.currency}`
                : "—"
            }
          />
          <SummaryRow label="Term" value={`${state.scope.termStart || "?"} → ${state.scope.termEnd || "?"}`} />
          <SummaryRow label="Payment" value={state.scope.payment || "—"} />
        </dl>
      </section>

      <section className="rounded-panel border border-divider bg-surface p-4">
        <h3 className="text-section text-text">Review plan</h3>
        <ul className="mt-2 space-y-1 text-body">
          <li>Delivery — {state.routing.deliveryOwnerId ?? "unassigned"}</li>
          <li>HR — {state.routing.hrOwnerId ?? "unassigned"}</li>
          <li>Finance — {state.routing.financeOwnerId ?? "unassigned"}</li>
          <li>Legal — {state.routing.legalOwnerId ?? "unassigned"}</li>
          {state.routing.ceoRequired ? (
            <li>CEO — {state.routing.ceoOwnerId ?? "unassigned"}</li>
          ) : null}
        </ul>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="primary"
          onClick={() => void onSubmit()}
          disabled={submitting}
          data-testid="studio-submit"
        >
          {submitting ? "Submitting…" : "Submit package"}
        </Button>
        <p className="text-secondary text-text-secondary">
          Submission creates a Delivery review task. It does not approve the
          contract.
        </p>
      </div>
      {submitError ? (
        <p role="alert" className="text-danger">
          {submitError}
        </p>
      ) : null}
      {state.submittedAt ? (
        <p className="text-success" role="status">
          Submitted at {new Date(state.submittedAt).toLocaleString()}.
        </p>
      ) : null}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-secondary text-text-secondary">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/* Compile-time nudge: EngagementType is used for narrowing above. */
export type _EngagementType = EngagementType;
