/**
 * /engagements/new — New engagement (S22 P2-4), as the prototype: the sheet's
 * project block, "+ New client…", and "Create engagement from deal" for a
 * Closed-Won HubSpot deal (pre-filled from the deal, via ?deal=<opportunity id>
 * or the picker). Pick the type first — it decides which money field applies.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getPipelineFacets, getPipelineOpportunity, listPipelineOpportunities, type PipelineOpportunityRow, type PipelineOwnerFacet } from "../../../api/client";
import {
  CURRENCIES,
  ENGAGEMENT_TYPE_LABEL,
  FIXED_TYPES,
  createClient,
  createEngagement,
  errorsFrom,
  importWorkbook,
  listClientOptions,
  missingFrom,
  rememberImportNote,
  type ClientOption,
  type EngagementType,
} from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { cn } from "../../../lib/cn";
import { Panel, Problems, errorText } from "./shared";

const NEW_CLIENT = "__new";

interface Form {
  client_id: string;
  new_client: string;
  name: string;
  type: EngagementType | "";
  owner_user_id: string;
  currency: string;
  start: string;
  end: string;
  total_price: string;
  monthly_fee: string;
  additional_costs_flag: "" | "1" | "0";
  same_dates_for_all: "" | "1" | "0";
  hubspot_deal_id: string;
  opportunity_id: string;
}

const EMPTY: Form = {
  client_id: "",
  new_client: "",
  name: "",
  type: "",
  owner_user_id: "",
  currency: "USD",
  start: "",
  end: "",
  total_price: "",
  monthly_fee: "",
  additional_costs_flag: "",
  same_dates_for_all: "",
  hubspot_deal_id: "",
  opportunity_id: "",
};

const TYPE_FROM_DEAL: Record<string, EngagementType> = {
  fixed_cost: "fixed_cost",
  "fixed cost": "fixed_cost",
  fixed_fee: "fixed_cost",
  assessment: "assessment",
  msp: "msp",
  managed_service: "msp",
  "managed service": "msp",
  time_and_materials: "time_and_materials",
  "t&m": "time_and_materials",
  staff_augmentation: "staff_augmentation",
  "staff augmentation": "staff_augmentation",
  staff_aug: "staff_augmentation",
};

function prefillFromDeal(form: Form, deal: PipelineOpportunityRow): Form {
  const suggested = deal.name ? Object.entries(TYPE_FROM_DEAL).find(([k]) => deal.name!.toLowerCase().includes(k))?.[1] : undefined;
  return {
    ...form,
    client_id: deal.client_id ?? form.client_id,
    name: deal.name ?? form.name,
    owner_user_id: deal.owner_id ?? form.owner_user_id,
    currency: deal.currency ?? form.currency,
    start: deal.close_date ?? form.start,
    hubspot_deal_id: deal.hubspot_deal_id ?? "",
    opportunity_id: deal.opportunity_id,
    type: form.type || suggested || "",
  };
}

export function NewEngagementPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const dealParam = params.get("deal") ?? "";
  const [form, setForm] = useState<Form>(EMPTY);
  const [clients, setClients] = useState<ClientOption[]>([]);
  const [owners, setOwners] = useState<PipelineOwnerFacet[]>([]);
  const [deals, setDeals] = useState<PipelineOpportunityRow[]>([]);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheetErrors, setSheetErrors] = useState<string[] | null>(null);
  const [sheetMessage, setSheetMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function uploadSheet(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setSheetErrors(null);
    setSheetMessage(`Reading ${file.name}…`);
    try {
      const result = await importWorkbook(file);
      rememberImportNote(result.engagement.id, result);
      navigate(`/engagements/${result.engagement.id}/allocations`);
    } catch (cause) {
      const errors = errorsFrom(cause);
      if (errors) setSheetErrors(errors);
      else setSheetMessage(errorText(cause, "Could not read that file."));
      if (errors) setSheetMessage(null);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  useEffect(() => {
    let cancelled = false;
    listClientOptions().then((rows) => !cancelled && setClients(rows)).catch(() => undefined);
    getPipelineFacets().then((f) => !cancelled && setOwners(f.owners)).catch(() => undefined);
    listPipelineOpportunities({ open_closed: "closed_won", page_size: 100 })
      .then((page) => !cancelled && setDeals(page.items))
      .catch(() => undefined);
    if (dealParam) {
      getPipelineOpportunity(dealParam)
        .then((deal) => !cancelled && setForm((prev) => prefillFromDeal(prev, deal)))
        .catch((cause) => !cancelled && setNotice(errorText(cause, "The deal could not be loaded; fill the form by hand.")));
    }
    return () => {
      cancelled = true;
    };
  }, [dealParam]);

  const fixed = form.type !== "" && FIXED_TYPES.has(form.type);
  const msp = form.type === "msp";
  const localMissing = useMemo(() => {
    const miss: string[] = [];
    const client = form.client_id === NEW_CLIENT ? form.new_client.trim() : form.client_id;
    if (!client) miss.push("client");
    if (!form.name.trim()) miss.push("name");
    if (!form.type) miss.push("type");
    if (!form.start || !form.end) miss.push("dates");
    if (fixed && form.total_price.trim() === "") miss.push("total price");
    if (msp && form.monthly_fee.trim() === "") miss.push("monthly fee");
    if (form.additional_costs_flag === "") miss.push("additional costs Y/N");
    if (form.same_dates_for_all === "") miss.push("same dates Y/N");
    return miss;
  }, [form, fixed, msp]);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit() {
    setProblems(null);
    setNotice(null);
    if (localMissing.length) {
      setProblems(localMissing);
      return;
    }
    setBusy(true);
    try {
      let clientId = form.client_id;
      if (clientId === NEW_CLIENT) {
        const created = await createClient(form.new_client.trim());
        clientId = created.id;
      }
      const engagement = await createEngagement({
        client_id: clientId,
        name: form.name.trim(),
        type: form.type as EngagementType,
        start: form.start,
        end: form.end,
        total_price: fixed ? form.total_price : null,
        monthly_fee: msp ? form.monthly_fee : null,
        currency: form.currency,
        additional_costs_flag: form.additional_costs_flag === "1",
        same_dates_for_all: form.same_dates_for_all === "1",
        owner_user_id: form.owner_user_id || null,
        hubspot_deal_id: form.hubspot_deal_id || null,
        opportunity_id: form.opportunity_id || null,
      });
      navigate(`/engagements/${engagement.id}/allocations`);
    } catch (cause) {
      const missing = missingFrom(cause);
      if (missing) setProblems(missing);
      else setNotice(errorText(cause, "The engagement was not created."));
    } finally {
      setBusy(false);
    }
  }

  const field = "min-h-control-compact rounded-control border border-input-border bg-warning-surface px-2 py-1 text-body text-text disabled:bg-surface-sunken disabled:text-text-muted";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="New engagement" subtitle="Same fields as the cost margin sheet's project block. Pick the type first — it decides which money field applies." />
      <Panel
        className="max-w-3xl"
        title="Upload the DealGate cost-margin sheet"
        hint="The sheet has everything: project block, people, costs. Nothing else to type. Columns are read by their headers, so older copies work."
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Cost-margin sheet (.xlsx)"
            className={cn(field, "max-w-md")}
            disabled={uploading}
            onChange={(event) => void uploadSheet(event.target.files?.[0])}
          />
          {sheetMessage ? (
            <span role="status" className="text-secondary text-text-secondary">
              {sheetMessage}
            </span>
          ) : null}
        </div>
        {sheetErrors ? (
          <p role="alert" className="mt-2 text-secondary text-danger" data-testid="sheet-errors">
            {sheetErrors.join(" · ")}
          </p>
        ) : null}
      </Panel>
      <Panel className="max-w-3xl" title="…or fill it in">
        <form
          className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="text-secondary text-text-secondary" htmlFor="ne-deal">
            From a Closed-Won deal
          </label>
          <select
            id="ne-deal"
            className={cn(field, "w-full")}
            value={form.opportunity_id}
            onChange={(event) => {
              const deal = deals.find((d) => d.opportunity_id === event.target.value);
              if (deal) setForm((prev) => prefillFromDeal(prev, deal));
              else setForm((prev) => ({ ...prev, opportunity_id: "", hubspot_deal_id: "" }));
            }}
          >
            <option value="">— optional: pre-fill from a HubSpot deal —</option>
            {deals.map((d) => (
              <option key={d.opportunity_id} value={d.opportunity_id}>
                {d.client_name ?? "Unknown client"} · {d.name ?? `Deal ${d.hubspot_deal_id ?? ""}`}
              </option>
            ))}
          </select>

          <label className="text-secondary text-text-secondary" htmlFor="ne-client">
            Client *
          </label>
          <div className="flex flex-wrap gap-2">
            <select id="ne-client" className={cn(field, "min-w-[14rem]")} value={form.client_id} onChange={(event) => set("client_id", event.target.value)}>
              <option value="">— pick —</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
              <option value={NEW_CLIENT}>+ New client…</option>
            </select>
            {form.client_id === NEW_CLIENT ? (
              <input aria-label="New client name" className={cn(field, "min-w-[14rem]")} placeholder="New client name" value={form.new_client} onChange={(event) => set("new_client", event.target.value)} />
            ) : null}
          </div>

          <label className="text-secondary text-text-secondary" htmlFor="ne-name">
            Engagement name *
          </label>
          <input id="ne-name" className={cn(field, "w-full")} placeholder="e.g. Portal rebuild staffing" value={form.name} onChange={(event) => set("name", event.target.value)} />

          <label className="text-secondary text-text-secondary" htmlFor="ne-type">
            Engagement type *
          </label>
          <select id="ne-type" className={field} value={form.type} onChange={(event) => set("type", event.target.value as EngagementType | "")}>
            <option value="">— pick first —</option>
            {(Object.keys(ENGAGEMENT_TYPE_LABEL) as EngagementType[]).map((t) => (
              <option key={t} value={t}>
                {ENGAGEMENT_TYPE_LABEL[t]}
              </option>
            ))}
          </select>

          <label className="text-secondary text-text-secondary" htmlFor="ne-owner">
            Owner
          </label>
          <select id="ne-owner" className={field} value={form.owner_user_id} onChange={(event) => set("owner_user_id", event.target.value)}>
            <option value="">— account owner —</option>
            {owners.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>

          <label className="text-secondary text-text-secondary" htmlFor="ne-currency">
            Currency
          </label>
          <select id="ne-currency" className={field} value={form.currency} onChange={(event) => set("currency", event.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>

          <label className="text-secondary text-text-secondary" htmlFor="ne-start">
            Start *
          </label>
          <input id="ne-start" type="date" className={field} value={form.start} onChange={(event) => set("start", event.target.value)} />
          <label className="text-secondary text-text-secondary" htmlFor="ne-end">
            End *
          </label>
          <input id="ne-end" type="date" className={field} value={form.end} onChange={(event) => set("end", event.target.value)} />

          <label className="text-secondary text-text-secondary" htmlFor="ne-price">
            Total project price
          </label>
          <input id="ne-price" type="number" min={0} className={field} disabled={!fixed} placeholder="Fixed cost / Assessment only" value={form.total_price} onChange={(event) => set("total_price", event.target.value)} />
          <label className="text-secondary text-text-secondary" htmlFor="ne-fee">
            Monthly fee
          </label>
          <input id="ne-fee" type="number" min={0} className={field} disabled={!msp} placeholder="MSP only" value={form.monthly_fee} onChange={(event) => set("monthly_fee", event.target.value)} />

          <label className="text-secondary text-text-secondary" htmlFor="ne-addl">
            Additional costs? *
          </label>
          <select id="ne-addl" className={field} value={form.additional_costs_flag} onChange={(event) => set("additional_costs_flag", event.target.value as Form["additional_costs_flag"])}>
            <option value="">— pick —</option>
            <option value="1">Yes</option>
            <option value="0">No</option>
          </select>
          <label className="text-secondary text-text-secondary" htmlFor="ne-same">
            Same start/end for everyone? *
          </label>
          <select id="ne-same" className={field} value={form.same_dates_for_all} onChange={(event) => set("same_dates_for_all", event.target.value as Form["same_dates_for_all"])}>
            <option value="">— pick —</option>
            <option value="1">Yes — everyone works the full window</option>
            <option value="0">No — each person has their own dates</option>
          </select>

          <div className="col-span-2 mt-2 flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create engagement"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate("/portfolio")} disabled={busy}>
              Cancel
            </Button>
            <Problems problems={problems} />
            {notice ? (
              <span role="status" className="text-secondary text-text-secondary">
                {notice}
              </span>
            ) : null}
          </div>
        </form>
      </Panel>
    </div>
  );
}
