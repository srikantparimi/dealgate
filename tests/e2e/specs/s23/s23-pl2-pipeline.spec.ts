/**
 * S23-PL2 · the redesigned Pipeline on staging, as the e2e bot. Every check reads the screen the user sees
 * (rule 18): card numbers, list counts, chips, the freshness line, the URL a link would carry.
 *
 * The bot sees only its own fixtures, so the spec issues run-tagged fixture deals with real stages, amounts,
 * regions and owners (T12, POST /api/dev/test-fixtures with pipeline_deal). It first checks the page with every
 * work column empty (tonight's situation), then adds a next action, an NDA file, a draft SOW, a watch, a group and
 * saved views through the real endpoints and the page itself (the populated situation).
 *
 *   T2  each of the six cards opens a list whose count equals the card
 *   T6  an <img onerror> label renders as text and runs nothing
 *   T8  stage navigator (All statuses, then the remembered status), status, BU, date, more filters, search,
 *       Reset all, tabs, layout, sort, page size — each changes the list or the URL
 *   T10 1440 and 375 px, light and dark: no horizontal scroll; screenshots outside the repo
 *   F3  the freshness line in its real state, plus stale and failed by response interception (screenshots)
 *
 * Teardown is unconditional: the spec's views, groups and watches are removed and the fixture clients are
 * hard-deleted, so scripts/check-test-data-clean.sh finds nothing afterwards.
 *
 *   STAGING_E2E_USERNAME=e2e-staging@smartek21.com E2E_BASE_URL=https://app.dealgateapp.com \
 *     PL2_SHOTS=/tmp/s23-pl2-shots npx playwright test specs/s23/s23-pl2-pipeline.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { authStaging, mintStagingTokens } from "../../fixtures/staging-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const SHOTS = process.env.PL2_SHOTS ?? path.join(os.tmpdir(), "s23-pl2-shots");
const RUN_TAG = `S23 e2e ${Date.now()}`;
const INJECTION = `<img src=x onerror=window.__pl2=1> =HYPERLINK("http://x","y")`;

type Fixture = { client_id: string; opportunity_id: string; label: string };
const fixtures: Record<string, Fixture> = {};
const viewIds: string[] = [];
const groupIds: string[] = [];
let api: APIRequestContext;

test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

async function json<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  if (!res.ok()) throw new Error(`${res.status()} ${res.url()}: ${(await res.text()).slice(0, 300)}`);
  return (await res.json()) as T;
}

async function issue(key: string, label: string, pipelineDeal: Record<string, unknown>): Promise<void> {
  const body = await json<Fixture>(
    await api.post("dev/test-fixtures", { data: { label: `${RUN_TAG} ${label}`, reviewer_ids: [], hours: 4, pipeline_deal: pipelineDeal } }),
  );
  fixtures[key] = { client_id: body.client_id, opportunity_id: body.opportunity_id, label };
}

async function openPipeline(page: Page, query = "status=open"): Promise<void> {
  const answered = page.waitForResponse((r) => r.url().includes("/api/pipeline/workspace") && r.status() === 200);
  await page.goto(`${BASE}/pipeline?${query}`);
  await answered;
  await expect(page.getByRole("region", { name: "Pipeline summary" })).toBeVisible();
}

/** The number on a card, as the user reads it. */
async function cardValue(page: Page, label: RegExp): Promise<string> {
  const text = await page.getByRole("region", { name: "Pipeline summary" }).getByRole("button", { name: label }).innerText();
  const value = text.split("\n").map((l) => l.trim()).find((l) => /^\$?[\d.,]+[mk]?$/.test(l));
  if (!value) throw new Error(`no value on card ${label}: ${text}`);
  return value;
}

/** The list's own count line: "N deals · …" or "N clients · …". */
async function listCount(page: Page, noun: "deals" | "clients"): Promise<number> {
  const re = noun === "deals" ? /^(\d+) deals? · / : /^(\d+) clients? · /;
  const line = page.getByText(re).first();
  await expect(line).toBeVisible();
  return Number(re.exec(await line.innerText())![1]);
}

async function shot(page: Page, name: string, fullPage = false): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage });
}

test.beforeAll(async () => {
  const { idToken } = mintStagingTokens();
  api = await pwRequest.newContext({
    baseURL: `${BASE}/api/`,
    extraHTTPHeaders: { Authorization: `Bearer ${idToken}` },
    timeout: 90_000,
  });
  // Tonight's situation: real stages, amounts, regions and owners; every work column empty.
  await issue("open_st21", "Cloud modernization", { stage: 2, amount: "120000.00", region: "US", owner: "active", close_in_days: 3, activity_days_ago: 3 });
  await issue("open_rr", "Managed services", { stage: 4, amount: "250000.00", region: "South Africa", owner: "active", close_in_days: 40 });
  await issue("hold", "Paused rollout", { stage: 9, amount: "30000.00", region: "US - IT Avalon (Staffing)", owner: "active", close_in_days: 60, activity_days_ago: 20 });
  await issue("won", "Signed support", { stage: 7, amount: "80000.00", region: "US - IT Avalon", owner: "former", close_in_days: -10 });
  await issue("no_owner", INJECTION, { stage: 1, region: "US", owner: "none", close_in_days: -5 });
});

test.afterAll(async () => {
  try {
    const views = await json<{ id: string; name: string }[]>(await api.get("pipeline/views")).catch(() => []);
    for (const v of views.filter((x) => x.name.includes(RUN_TAG) || viewIds.includes(x.id))) {
      await api.delete(`pipeline/views/${v.id}`).catch(() => undefined);
    }
    const groups = await json<{ id: string; name: string }[]>(await api.get("pipeline/groups")).catch(() => []);
    for (const g of groups.filter((x) => x.name.includes(RUN_TAG) || groupIds.includes(x.id))) {
      await api.delete(`tracking-groups/${g.id}`).catch(() => undefined);
    }
    for (const f of Object.values(fixtures)) {
      await api.delete(`pipeline/watching/${f.opportunity_id}`).catch(() => undefined);
    }
    for (const f of Object.values(fixtures)) {
      const del = await api.delete(`clients/${f.client_id}`, { params: { reason: "S23 PL2 spec teardown" } });
      const body = (await del.json().catch(() => ({}))) as { job_id?: string };
      for (let i = 0; body.job_id && i < 60; i += 1) {
        const state = (await (await api.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
        if (state.status === "done" || state.status === "failed") break;
        await new Promise((r) => setTimeout(r, 2_000));
      }
    }
  } finally {
    await api.dispose();
  }
});

test("tonight's situation: empty work columns read exactly as the prototype, and HubSpot text stays text", async ({ page }) => {
  await authStaging(page, BASE);
  await page.addInitScript(() => { (window as unknown as { __pl2?: number }).__pl2 = undefined; });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPipeline(page);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Pipeline");
  await expect(page.getByText(/Deals synced .* PT|Deal data is \d+ days? old|The last sync failed|No successful deal sync/).first()).toBeVisible();
  for (const label of ["Open deals", "Open value · USD", "Closing this month", "Overdue next actions", "Pending approvals", "Agreement gaps"]) {
    // The card is one button; its name starts with the label (the "↗" beside it is hidden from assistive tech).
    const name = new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
    await expect(page.getByRole("region", { name: "Pipeline summary" }).getByRole("button", { name })).toBeVisible();
  }
  await expect(page.getByText("No deal has a next action yet")).toBeVisible();
  // S24-AG1 F6: the gap card's note is the NDA & MSA page's definition (the "no agreement files uploaded yet" note is retired).
  await expect(page.getByRole("region", { name: "Pipeline summary" }).getByText("Net new, past stage 1, NDA or MSA missing")).toBeVisible();
  const records = page.getByRole("region", { name: "Pipeline records" });
  await expect(records.getByText("Set next action").first()).toBeVisible();
  await expect(records.getByText("No SOW").first()).toBeVisible();
  // S24-AG1 F6: each tag follows its kind's name and reads the shared state ("Missing": net new, past stage 1, nothing held).
  await expect(records.locator("span").filter({ hasText: /^NDA\s*Missing$/ }).first()).toBeVisible();
  await expect(records.locator("span").filter({ hasText: /^MSA\s*Missing$/ }).first()).toBeVisible();
  await expect(records.getByText("On hold", { exact: true }).first()).toBeVisible();
  // T6: the label is shown as text; nothing ran and no image element was made from it.
  await expect(records.getByText(INJECTION, { exact: false }).first()).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __pl2?: number }).__pl2)).toBeUndefined();
  expect(await page.locator('img[src="x"]').count()).toBe(0);
  await shot(page, "d1440-light-tonight", true);
});

test("T2 on the page: each of the six cards opens a list whose count equals the card", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  const cards: [RegExp, "deals" | "clients" | "value"][] = [
    [/^Open deals/, "deals"],
    [/^Open value · USD/, "value"],
    [/^Closing this month/, "deals"],
    [/^Overdue next actions/, "deals"],
    [/^Pending approvals/, "deals"],
    [/^Agreement gaps/, "clients"],
  ];
  for (const [label, kind] of cards) {
    await openPipeline(page);
    const value = await cardValue(page, label);
    const before = page.url();
    await page.getByRole("region", { name: "Pipeline summary" }).getByRole("button", { name: label }).click();
    // A drill that is already in force changes nothing (no new request); otherwise wait for the new answer.
    await page.waitForLoadState("networkidle");
    if (page.url() !== before) await expect(page.getByRole("region", { name: "Pipeline records" })).toHaveAttribute("aria-busy", "false");
    if (kind === "value") {
      await expect(page.getByText(new RegExp(`^\\d+ deals? · ${value.replace(/[$.]/g, "\\$&")} · USD`)).first()).toBeVisible();
    } else {
      expect(await listCount(page, kind), `${label} card ${value}`).toBe(Number(value));
    }
  }
});

test("the populated situation: next action, NDA file, draft SOW, watch, group and saved views", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  const me = await json<{ id: string }>(await api.get("me"));
  await json(await api.post("next-actions", {
    data: { opportunity_id: fixtures.open_st21.opportunity_id, title: `${RUN_TAG} confirm commercial terms`,
            assignee_user_id: me.id, due_date: new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10) },
  }));
  const pdf = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
  await json(await api.post("agreements", {
    multipart: { client_id: fixtures.open_rr.client_id, kind: "NDA", file: { name: "nda.pdf", mimeType: "application/pdf", buffer: pdf } },
  }));
  await issue("draft_sow", "Data platform build", { stage: 3, amount: "50000.00", region: "US", owner: "active", close_in_days: 90, draft_sow: true });

  await openPipeline(page);
  await expect(page.getByText(/of \d+ deals? with a next action/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Pipeline summary" }).getByText("Net new, past stage 1, NDA or MSA missing")).toBeVisible();
  const records = page.getByRole("region", { name: "Pipeline records" });
  await expect(records.getByText(`${RUN_TAG} confirm commercial terms`)).toBeVisible();
  await expect(records.getByText(/· overdue/).first()).toBeVisible();
  await expect(records.locator("span").filter({ hasText: /^NDA\s*✓ Client copy$/ }).first()).toBeVisible(); // S24-AG1 F6
  await expect(records.getByText("Draft").first()).toBeVisible();

  // Watch a deal from its star; the Watching focus view counts it.
  await records.getByRole("button", { name: new RegExp(`^Watch .*Cloud modernization`) }).first().click();
  await expect(page.getByRole("button", { name: /^Watching\s*1$/ }).first()).toBeVisible({ timeout: 20_000 });

  // Save a view, a second one, and a duplicate (case-insensitive).
  for (const name of [`${RUN_TAG} view`, `${RUN_TAG} view 2`]) {
    await page.getByRole("button", { name: /Save view/ }).first().click();
    await page.getByRole("textbox", { name: /View name/ }).fill(name);
    await page.getByRole("button", { name: /^Save view$/ }).click();
    await expect(page.getByRole("button", { name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }).first()).toBeVisible();
  }
  await page.getByRole("button", { name: /Save view/ }).first().click();
  await page.getByRole("textbox", { name: /View name/ }).fill(`${RUN_TAG} VIEW`);
  await page.getByRole("button", { name: /^Save view$/ }).click();
  await expect(page.getByText("You already have a view with this name.")).toBeVisible();
  await page.keyboard.press("Escape");

  // Group two selected deals.
  await records.getByRole("checkbox", { name: /Select .*Cloud modernization/ }).first().check();
  await records.getByRole("checkbox", { name: /Select .*Managed services/ }).first().check();
  await page.getByRole("button", { name: /Add to group/ }).click();
  await page.getByRole("textbox", { name: /Group name/ }).fill(`${RUN_TAG} group`);
  await page.getByRole("button", { name: /^Create group$/ }).click();
  await expect(page.getByRole("button", { name: new RegExp(`${RUN_TAG} group`) }).first()).toBeVisible();
  await shot(page, "d1440-light-populated", true);
});

test("previews, next-action editor, export, Create in HubSpot, settings screens; no alerts, notes or sector", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPipeline(page);
  const records = page.getByRole("region", { name: "Pipeline records" });

  // F11: the deal preview's editor writes through the existing next-action endpoint.
  const saved = page.waitForResponse((r) => /\/api\/next-actions(\/|$|\?)/.test(r.url()) && ["POST", "PATCH"].includes(r.request().method()));
  await records.getByRole("button", { name: /Data platform build$/ }).first().click();
  const preview = page.getByRole("dialog");
  await expect(preview.getByText(/Opportunity · quick preview/i)).toBeVisible();
  await expect(preview.getByText("Deal value · USD")).toBeVisible();
  await expect(preview.getByText("HubSpot region")).toBeVisible();
  // S24-AG1 F6: the preview says what the NDA and MSA tags mean.
  await expect(preview.getByText("NDA and MSA show the client's state: Client copy, Standard copy, Marked covered, Missing or Due at stage 2. A warning only; nothing is blocked. The SOW state is separate from the HubSpot sales stage.")).toBeVisible();
  await preview.getByRole("textbox", { name: "Next action" }).fill(`${RUN_TAG} validate scope assumptions`);
  await preview.getByRole("button", { name: "Save next action" }).click();
  expect((await saved).status()).toBeLessThan(300);
  await expect(preview.getByText("Next action saved.")).toBeVisible();
  // F20: no alerts, no notes, no client sector in the preview.
  await expect(preview.getByText(/alert|notes?\b|sector/i)).toHaveCount(0);
  await shot(page, "d1440-deal-preview");
  await page.keyboard.press("Escape");

  // F11: the client preview lists the client's deals.
  await records.getByRole("button", { name: /Managed services/ }).nth(1).click();
  await expect(page.getByRole("dialog").getByText(/All linked opportunities · \d+/)).toBeVisible();
  await shot(page, "d1440-client-preview");
  await page.keyboard.press("Escape");

  // F14: the export downloads every filtered row as CSV.
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Export view/ }).click()]);
  expect(download.suggestedFilename()).toBe("DealGate_Pipeline_deals.csv");
  const csv = fs.readFileSync(await download.path(), "utf8");
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  expect(csv.split(/\r\n/).filter(Boolean).length).toBeGreaterThan(1);

  // F19: Create in HubSpot opens the portal from configuration, not a hard-coded id.
  const config = await json<{ hubspot_portal_id: string | null }>(await api.get("config"));
  const create = page.getByRole("link", { name: /Create in HubSpot/ });
  if (config.hubspot_portal_id) {
    await expect(create).toHaveAttribute("href", new RegExp(`/contacts/${config.hubspot_portal_id}/deal/new$`));
  } else {
    await expect(create).toHaveCount(0);
  }
  // F20: no alert controls on the page.
  await expect(page.getByRole("button", { name: /alert/i })).toHaveCount(0);

  // F18: Settings → Business units and the HubSpot owner link on People & access.
  await page.goto(`${BASE}/settings/business-units`);
  await expect(page.getByRole("heading", { name: "Business units" })).toBeVisible();
  await expect(page.getByText(/US covers two different business units/)).toBeVisible();
  await shot(page, "d1440-settings-business-units", true);
  await page.goto(`${BASE}/settings/people`);
  await expect(page.getByText(/HubSpot owner/).first()).toBeVisible();
  await shot(page, "d1440-settings-people", true);
});

test("T6 on staging: a formula-like next action is plain text on the page and neutralised in the export", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  const me = await json<{ id: string }>(await api.get("me"));
  const formula = `=HYPERLINK("http://x","${RUN_TAG}")`;
  await json(await api.post("next-actions", {
    data: { opportunity_id: fixtures.hold.opportunity_id, title: formula, assignee_user_id: me.id, due_date: null },
  }));
  await openPipeline(page);
  await expect(page.getByRole("region", { name: "Pipeline records" }).getByText(formula).first()).toBeVisible();
  const res = await api.get("pipeline/export", { params: { status: "open" } });
  expect(res.status()).toBe(200);
  const csv = await res.text();
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  const line = csv.split(/\r\n/).find((l) => l.includes(RUN_TAG) && l.includes("HYPERLINK"));
  expect(line, "the export row carrying the formula").toBeTruthy();
  expect(line!).toContain(`"'=HYPERLINK(`);
});

test("F3 on staging: Run sync now says 'Sync started' and the panel reports the finished run", async ({ page }) => {
  test.setTimeout(600_000);
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPipeline(page);
  await page.getByRole("button", { name: /Sync details|Inspect sync/ }).click();
  const panel = page.getByRole("dialog", { name: /Sync health/ });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: /Run sync now/ }).click();
  await expect(panel.getByText("Sync started")).toBeVisible();
  await shot(page, "d1440-sync-run-started");
  // CloudFront cuts the POST at 30 s while the sync runs on; only the polled sync-health decides.
  await expect(panel.getByText(/Sync finished · (Succeeded|Partly failed|Failed)/)).toBeVisible({ timeout: 540_000 });
  await expect(panel.getByText(/The sync did not start/)).toHaveCount(0);
  await shot(page, "d1440-sync-run-finished");
});

test("T8: every control changes the list or the URL; the stage navigator restores the status", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPipeline(page);
  const all = await listCount(page, "deals");

  const proposal = page.getByRole("region", { name: "HubSpot sales stages" }).getByRole("button", { name: /^4 · Proposal/ });
  await proposal.click();
  await expect(page).toHaveURL(/status=all/);
  await expect(page).toHaveURL(/stage=4/);
  await expect(page.getByRole("button", { name: /^Remove 4 · Proposal/ })).toBeVisible();
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(1);
  await proposal.click();
  await expect(page).toHaveURL(/status=open/);
  await expect(page.getByRole("button", { name: /^Remove Status: Open \(includes on hold\)/ })).toBeVisible();

  await page.getByRole("combobox", { name: "Deal status" }).selectOption("won");
  await expect(page).toHaveURL(/status=won/);
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(1);
  await page.getByRole("combobox", { name: "Deal status" }).selectOption("open");

  await page.getByRole("button", { name: /^Business unit/ }).click();
  await page.getByRole("checkbox", { name: /Retro Rabbit/ }).check();
  await page.getByRole("button", { name: "Apply filter" }).click();
  await expect(page.getByRole("button", { name: /^Remove BU: Retro Rabbit \(South Africa\)/ })).toBeVisible();
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(1);

  await page.getByRole("button", { name: /Reset all/ }).click();
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(all);

  await page.getByRole("button", { name: /^More filters/ }).click();
  await page.getByRole("combobox", { name: "Attention" }).selectOption("past_close");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("button", { name: /^Remove Attention: close date passed/ })).toBeVisible();
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(1);
  await page.getByRole("button", { name: /Reset all/ }).click();

  await page.getByRole("searchbox").fill("Paused rollout");
  await expect(page).toHaveURL(/q=Paused/);
  await expect.poll(() => listCount(page, "deals"), { timeout: 20_000 }).toBe(1);
  await page.getByRole("button", { name: /Reset all/ }).click();

  await page.getByRole("button", { name: /^Clients/ }).click();
  await expect(page).toHaveURL(/tab=clients/);
  await listCount(page, "clients");
  await page.getByRole("button", { name: /^Opportunities/ }).click();
  await page.getByRole("button", { name: /Board/ }).click();
  await expect(page).toHaveURL(/layout=board/);
  await page.getByRole("button", { name: /List/ }).click();
  await page.getByRole("combobox", { name: "Sort records" }).selectOption("name");
  await expect(page).toHaveURL(/sort=name/);
  await page.getByRole("combobox", { name: /Rows/ }).selectOption("50");
  await expect(page).toHaveURL(/page_size=50/);
  await page.goBack();
  await expect(page).not.toHaveURL(/page_size=50/);
});

test("F3: the freshness line in all three states (real, then stale and failed by interception)", async ({ page }) => {
  await authStaging(page, BASE);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPipeline(page);
  await shot(page, "d1440-sync-real");
  const now = Date.now();
  const states: Record<string, Record<string, unknown>> = {
    fresh: { state: "fresh", last_success_at: new Date(now - 7 * 3_600_000).toISOString(), last_attempt_at: new Date(now - 7 * 3_600_000).toISOString(), last_status: "ok", errors: [], error_count: 0 },
    stale: { state: "stale", last_success_at: new Date(now - 50 * 3_600_000).toISOString(), last_attempt_at: new Date(now - 50 * 3_600_000).toISOString(), last_status: "ok", errors: [], error_count: 0 },
    failed: { state: "failed", last_success_at: new Date(now - 31 * 3_600_000).toISOString(), last_attempt_at: new Date(now - 7 * 3_600_000).toISOString(), last_status: "partial", error_count: 1, errors: [{ hubspot_id: "1038193692", reason: "deal: stage 1038193692 not mapped" }] },
  };
  const expected: Record<string, RegExp> = {
    fresh: /Deals synced .* PT · \d+ h ago · nightly sync/,
    stale: /Deal data is \d+ days? old\. Last successful sync .* PT\. Check sync health before relying on these figures\./,
    failed: /The last sync failed \(.* PT\)\. Showing deals from the last good sync, .* PT\./,
  };
  for (const [name, freshness] of Object.entries(states)) {
    await page.route("**/api/pipeline/workspace**", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.freshness = { ...body.freshness, ...freshness };
      await route.fulfill({ response: res, json: body });
    });
    await openPipeline(page);
    await expect(page.getByText(expected[name]).first()).toBeVisible();
    await shot(page, `d1440-sync-${name}`);
    await page.getByRole("button", { name: name === "fresh" ? /Sync details/ : /Inspect sync/ }).click();
    await expect(page.getByRole("dialog", { name: /Sync health/ })).toBeVisible();
    if (name === "failed") {
      const panel = page.getByRole("dialog", { name: /Sync health/ });
      await expect(panel.getByText(/HubSpot returned a stage the mapping does not know \(1 deal\)\. The other deals were saved\./)).toBeVisible();
      await expect(panel.getByText(/1038193692/)).toHaveCount(0);
    }
    await shot(page, `d1440-sync-panel-${name}`);
    await page.keyboard.press("Escape");
    await page.unroute("**/api/pipeline/workspace**");
  }
});

test("T10: 1440 and 375 px, light and dark — no horizontal scroll", async ({ browser }) => {
  for (const [name, viewport, colorScheme] of [
    ["d1440-light", { width: 1440, height: 900 }, "light"],
    ["d1440-dark", { width: 1440, height: 900 }, "dark"],
    ["m375-light", { width: 375, height: 812 }, "light"],
    ["m375-dark", { width: 375, height: 812 }, "dark"],
  ] as const) {
    const context = await browser.newContext({ viewport, colorScheme });
    const page = await context.newPage();
    await authStaging(page, BASE);
    await openPipeline(page);
    const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(scroll, `${name} scrollWidth`).toBeLessThanOrEqual(client);
    if (name.startsWith("m375")) {
      await page.getByRole("button", { name: /Views & groups/ }).click();
      await expect(page.getByRole("dialog", { name: /Your views & groups/ })).toBeVisible();
      await shot(page, `${name}-views-panel`);
      await page.keyboard.press("Escape");
    }
    await shot(page, `${name}-pipeline`, true);
    await context.close();
  }
});
