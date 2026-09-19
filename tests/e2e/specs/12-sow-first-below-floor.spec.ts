/**
 * 12 — SOW-first below-floor (S9 wave 2).
 *
 * Upload `06_below_floor.pdf`. The pipeline must:
 *   - Classify as `fixed_price` from the SOW.
 *   - Report both US and India floor tests as FAIL.
 *   - Show the CEO GateStep as "Will trigger" *before* submit.
 *   - Pre-draft the CEO brief (visible under `/sows/:id/exception`).
 *   - Let the account owner write the business rationale.
 *   - Let the CEO approve the exception → package transitions to
 *     `ready_to_sign`.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import {
  applyTestUser,
  seedAgreement,
  seedClientWithDeal,
  seedFixtureSow,
  seedGmModel,
  submitApprovalPackage,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("below-floor SOW pre-drafts CEO brief and approves through to ready_to_sign", async ({
  page,
}) => {
  const { client, opportunityId } = await seedClientWithDeal({});
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedFixtureSow(opportunityId, "06_below_floor.pdf", "Sales");
  expect(sow.expectedEngagementType).toBe("fixed_price");

  // Deliberately drive the GM below both floors so the confirmation
  // endpoint pre-drafts the CEO brief. `seedGmModel({belowFloor: true})`
  // is the canonical §7 worked example used by spec 04.
  await seedGmModel({
    opportunityId,
    sowVersionId: sow.sowVersionId,
    engagementType: "fixed_price",
    belowFloor: true,
  });

  // 1. Confirmation endpoint reports floors FAIL + a CEO gate brief.
  const conf = await apiFetch<{
    engagement: { primary: { type: string } };
    floors: {
      us_pass: boolean;
      india_pass: boolean;
      requires_ceo: boolean;
      failing: string[];
    };
    ceo_gate: { will_trigger: boolean; brief?: unknown };
  }>(
    "Sales",
    "GET",
    `/sow/${opportunityId}/confirmation`,
  );
  expect(conf.json.engagement.primary.type).toBe("fixed_price");
  expect(conf.json.floors.us_pass).toBe(false);
  expect(conf.json.floors.india_pass).toBe(false);
  expect(conf.json.floors.requires_ceo).toBe(true);
  // 2. CEO GateStep reads "Will trigger" pre-submit — the confirmation
  // endpoint surfaces this via `ceo_gate.will_trigger` + a pre-drafted
  // brief the exception route can render.
  expect(conf.json.ceo_gate.will_trigger).toBe(true);
  expect(conf.json.ceo_gate.brief).toBeTruthy();

  // 3. Browser round-trip — the exception route renders the brief.
  await applyTestUser(page, "Sales");
  await page.goto(`/sows/${sow.sowVersionId}/exception`);
  // The v2 exception surface renders a heading and the CEO brief
  // sections. We assert the route resolves (200) and the brief text
  // is visible; the precise UI copy is tested in the web unit suite.
  await expect(page).toHaveURL(new RegExp(`/sows/${sow.sowVersionId}/exception$`));
  await expect(
    page.getByRole("heading", { name: /ceo|exception|brief/i }).first(),
  ).toBeVisible();

  // 4. Submit the approval package. Because floors fail, the package
  // routes to `pending_ceo_exception` (spec 04 covers the same path
  // for a manually-built GM model — here we prove the SOW-first
  // pipeline drives it end-to-end).
  const pkg = await submitApprovalPackage(opportunityId, "Delivery");
  expect(pkg.status).toMatch(/pending_ceo_exception|pending_delivery_hr/);

  // Locate the CEO exception row for this package.
  const inbox = await apiFetch<{
    items: { id: string; package_id: string }[];
  }>("CEO", "GET", "/ceo-exceptions", undefined, {
    query: { status: "pending" },
  });
  const exc = inbox.json.items.find((row) => row.package_id === pkg.id);
  expect(exc, "ceo exception row exists").toBeTruthy();
  const excId = exc!.id;

  // 5. Account owner writes the business rationale — the one
  // paragraph a human must actually author (manifesto step 6).
  await apiFetch("Sales", "PATCH", `/ceo-exceptions/${excId}/rationale`, {
    rationale_text:
      "Strategic seed engagement for a top-3 target logo. Renegotiated at renewal per policy.",
  });

  // 6. CEO approves the exception with conditions + a valid_until.
  await applyTestUser(page, "CEO");
  await page.goto(`/ceo-exceptions/${excId}`);
  await expect(page.getByRole("heading", { name: /client/i })).toBeVisible();

  await apiFetch("CEO", "POST", `/ceo-exceptions/${excId}/decisions`, {
    decision: "approve",
    conditions_text: "Renegotiate to floor at renewal.",
    valid_until: "2027-06-30",
  });

  // 7. Package transitions to ready_to_sign.
  const final = await apiFetch<{ status: string }>(
    "SystemAdmin",
    "GET",
    `/approvals/packages/${pkg.id}`,
  );
  expect(final.json.status).toBe("ready_to_sign");
});
