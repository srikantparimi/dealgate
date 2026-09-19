/**
 * Seed helpers for E2E specs.
 *
 * Every helper hits the API as SystemAdmin (so no role gate blocks the
 * fixture) and returns the created row. Specs then log the browser in
 * as the appropriate persona via the `X-Test-User` header injected by
 * `applyTestUser`.
 */
import type { Page } from "@playwright/test";
import { apiFetch, emailFor, type Role } from "./api";

/** Random suffix so parallel runs (or reruns) don't collide on unique keys. */
export function rand(prefix = ""): string {
  const s = Math.random().toString(36).slice(2, 10);
  return prefix ? `${prefix}-${s}` : s;
}

/**
 * Inject `VITE_TEST_USER` into `localStorage` before any page script runs.
 * The web client (`web/src/api/client.ts`) reads `import.meta.env.VITE_TEST_USER`
 * — for E2E we rely on the dev server having been started with the value,
 * but this route-level hook also injects the header on every request so
 * the identity can be swapped per test without restarting Vite.
 */
export async function applyTestUser(page: Page, role: Role): Promise<void> {
  const email = emailFor(role);
  await page.route("**/*", async (route) => {
    const req = route.request();
    const url = req.url();
    // Only inject on API calls. The regex covers both same-origin
    // `/api/*` proxies and direct `http://localhost:8000/*` calls.
    if (/localhost:8000|\/api\//.test(url)) {
      const headers = { ...req.headers(), "x-test-user": email };
      await route.continue({ headers });
    } else {
      await route.continue();
    }
  });
}

/** ---------- Clients ---------------------------------------------------- */

export interface SeededClient {
  id: string;
  name: string;
  legal_entity_id: string;
}

/**
 * Create a client + one legal entity. Uses the SystemAdmin API path.
 * The dev backend does not expose a public POST /clients, so we insert
 * via the HubSpot webhook path (`/hubspot/webhook`) that the pytest
 * suites already use as the canonical "arrival" event.
 */
export async function seedClientWithDeal(opts: {
  clientName?: string;
  hubspotCompanyId?: string;
  hubspotDealId?: string;
  ownerEmail?: string;
}): Promise<{ client: SeededClient; opportunityId: string; hubspotDealId: string }> {
  const clientName = opts.clientName ?? `Acme ${rand()}`;
  const hubspotCompanyId = opts.hubspotCompanyId ?? `co-${rand()}`;
  const hubspotDealId = opts.hubspotDealId ?? `deal-${rand()}`;
  const ownerEmail = opts.ownerEmail ?? emailFor("Sales");

  // The webhook is the canonical intake path; it creates the client,
  // legal entity, and opportunity idempotently. The dev backend accepts
  // an empty signature when `HUBSPOT_WEBHOOK_SECRET` is unset.
  await apiFetch("SystemAdmin", "POST", "/hubspot/webhook", {
    eventId: `evt-${rand()}`,
    subscriptionType: "deal.creation",
    objectId: hubspotDealId,
    properties: {
      dealname: `${clientName} — engagement`,
      company: clientName,
      hubspot_owner_email: ownerEmail,
      hs_object_id: hubspotDealId,
      associated_company_id: hubspotCompanyId,
    },
  });

  const deals = await apiFetch<{ items: Array<{ id: string; client_id: string }> }>(
    "SystemAdmin",
    "GET",
    "/deals",
    undefined,
    { query: { size: 100 } },
  );
  const deal = deals.json.items.find((d) =>
    Boolean(d.id) && Boolean(d.client_id),
  );
  if (!deal) throw new Error("seedClientWithDeal: no deal after webhook");

  const client = await apiFetch<{
    id: string;
    name: string;
    legal_entities: Array<{ id: string }>;
  }>("SystemAdmin", "GET", `/clients/${deal.client_id}`);
  const legal = client.json.legal_entities[0];
  if (!legal) throw new Error("seedClientWithDeal: no legal entity");

  return {
    client: {
      id: client.json.id,
      name: client.json.name,
      legal_entity_id: legal.id,
    },
    opportunityId: deal.id,
    hubspotDealId,
  };
}

/** ---------- Agreements (NDA/MSA coverage) ------------------------------ */

export async function seedAgreement(
  legalEntityId: string,
  kind: "NDA" | "MSA",
  state:
    | "missing"
    | "requested"
    | "drafting"
    | "under_review"
    | "sent"
    | "partially_signed"
    | "executed" = "executed",
): Promise<{ id: string }> {
  const res = await apiFetch<{ id: string }>(
    "Legal",
    "POST",
    "/agreements",
    {
      legal_entity_id: legalEntityId,
      type: kind,
      state,
      owner_email: emailFor("Legal"),
    },
  );
  return { id: res.json.id };
}

/** ---------- SOW versions ---------------------------------------------- */

export interface SeededSowVersion {
  id: string;
  sow_id: string;
  extract_status: string;
}

/**
 * Create a SOW version with a pre-populated stub extract (uses the API
 * `SOW_EXTRACT_STUB=1` path when the workflow env sets it). Returns the
 * unconfirmed version id.
 */
export async function seedSowVersion(
  opportunityId: string,
  ownerRole: Role = "Sales",
): Promise<SeededSowVersion> {
  // Ask for a presigned URL and let the API create the row in a stubbed
  // S3 flow. When `S3_STUB=1` is set the API accepts a synthetic file
  // key without a real upload.
  const upload = await apiFetch<{ s3_key: string }>(
    ownerRole,
    "POST",
    `/sow/${opportunityId}/upload-url`,
    { filename: "sow.pdf", content_type: "application/pdf" },
  );
  const version = await apiFetch<SeededSowVersion>(
    ownerRole,
    "POST",
    `/sow/${opportunityId}/versions`,
    {
      file_s3_key: upload.json.s3_key,
      file_hash: `hash-${rand()}`,
      file_size: 1234,
    },
  );
  return version.json;
}

/** Confirm every extracted field on a SOW version (skips the manual UI
 * loop when a spec only wants the delivery-model side of things). */
export async function confirmAllSowFields(
  sowVersionId: string,
  ownerRole: Role = "Sales",
): Promise<void> {
  const v = await apiFetch<{ extracted_fields: Record<string, { value: unknown }> }>(
    ownerRole,
    "GET",
    `/sow/versions/${sowVersionId}`,
  );
  for (const [name, field] of Object.entries(v.json.extracted_fields ?? {})) {
    await apiFetch(ownerRole, "PATCH", `/sow/versions/${sowVersionId}/fields/${name}`, {
      value: field.value,
    });
  }
  await apiFetch(ownerRole, "POST", `/sow/versions/${sowVersionId}/submit`);
}

/** ---------- Delivery / GM model --------------------------------------- */

export async function seedGmModel(opts: {
  opportunityId: string;
  sowVersionId?: string;
  engagementType?: string;
  /** When true, drives GM below the US floor (27.78%) for scenario 04. */
  belowFloor?: boolean;
}): Promise<{ id: string }> {
  const engagementType = opts.engagementType ?? "staff_aug";
  const belowFloor = opts.belowFloor ?? false;
  const start = "2025-01-01";
  const end = "2025-06-30";
  const resourceLines = [
    {
      role: "Engineer",
      seniority: "Senior",
      location: "US",
      person_name: "Alex",
      allocation_pct: "100",
      start_date: start,
      end_date: end,
      hours_billable: "800",
      hourly_bill_rate: belowFloor ? "180" : "250",
      hourly_cost: "130",
      validated_by: null,
    },
  ];
  const save = await apiFetch<{ gm_model: { id: string } }>(
    "Delivery",
    "POST",
    `/delivery-model/${opts.opportunityId}/versions`,
    {
      engagement_type: engagementType,
      sow_version_id: opts.sowVersionId ?? null,
      resource_lines: resourceLines,
      cost_lines: [],
    },
  );
  return { id: save.json.gm_model.id };
}

/** ---------- Approval packages ----------------------------------------- */

export async function submitApprovalPackage(
  opportunityId: string,
  submitterRole: Role = "Delivery",
): Promise<{ id: string; status: string }> {
  const res = await apiFetch<{ id: string; status: string }>(
    submitterRole,
    "POST",
    `/approvals/packages/${opportunityId}`,
  );
  return res.json;
}

export async function decidePackage(
  packageId: string,
  fn: "delivery" | "hr" | "finance" | "legal",
  role: Role,
  decision: "approve" | "reject" | "request_changes" = "approve",
  reason: string | null = null,
): Promise<void> {
  await apiFetch(role, "POST", `/approvals/packages/${packageId}/decisions/${fn}`, {
    decision,
    reason,
  });
}
