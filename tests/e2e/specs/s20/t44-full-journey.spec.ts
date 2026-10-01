/**
 * T44 · full end-to-end journey (S20 · W5).
 *
 * Per review + directive §8:
 * > Full e2e journey: intake → rework → approvals → conditional CEO →
 * > executed evidence → release → delivery acknowledge →
 * > project/actuals → calendar-month renewal. Capture build + resulting states.
 *
 * This is the click-through's execution. It uses `multi-role-auth.ts`
 * `actAs()` to swap role tokens between steps (submitter → delivery →
 * hr → finance → legal → ceo). The `system` slot is reserved for the
 * SystemAdmin bot that seeds data at start and cleans up at end.
 *
 * Fixtures are tagged with the `S20 e2e ` prefix so the scheduled
 * cleanup can reap them 24 h later (worker/e2e_cleanup.py::_PREFIX_RE
 * plus the S20 addition W1 will land — see requests.md).
 *
 * **Skeleton — all steps `test.skip` until the underlying capabilities land.**
 * Un-skip in reverse order (start with intake+upload once W3 lands, then
 * approvals once W3+W7 land, then release+project once W7 lands, etc).
 */
import { test, expect } from "@playwright/test";
import {
  actAs,
  authAsRole,
  bearerFor,
  type RoleSlot,
} from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const MARKER = `S20 e2e ${new Date()
  .toISOString()
  .replaceAll(/[-:T.Z]/g, "")}`;

test.describe.serial("T44 · full journey (S20)", () => {
  let dealId: string | null = null;
  let packageId: string | null = null;
  let projectId: string | null = null;

  test.beforeAll(async () => {
    // The staging HubSpot token is read-only tonight (isolation.md F1),
    // so a real deal is created by hand in HubSpot; the observer path
    // waits for the sync mirror to land it. The marker is the deal name.
    console.log(`[T44] using deal name marker: ${MARKER}`);
  });

  test.skip("step 1 · submitter finds the deal on Pipeline and opens it", async ({ page }) => {
    await authAsRole(page, "submitter");
    await page.goto(`${BASE}/pipeline?search=${encodeURIComponent(MARKER)}`);
    await expect(page.getByText(MARKER)).toBeVisible({ timeout: 60_000 });
    await page.getByText(MARKER).click();
    // capture dealId from URL
    dealId = /\/(?:deals|opportunities)\/([^/?]+)/.exec(page.url())?.[1] ?? null;
    expect(dealId).toBeTruthy();
  });

  test.skip("step 2 · submitter uploads a SOW with deal + client prefilled (T11)", async ({ page }) => {
    // Deep-link to /sows/new?dealId=... — W3 must accept the query param.
    await page.goto(`${BASE}/sows/new?dealId=${dealId}`);
    // The client + deal name are prefilled and read-only.
    // Upload a synthetic SOW file (fixtures/sow_extraction_stubs.ts).
    // Assert exactly one package created.
  });

  test.skip("step 3 · confirm scope, staffing, GM (T12, T17)", async ({ page }) => {
    // Confirm each extracted field; assert missing → `Not assessed`;
    // enter staffing so GM computes; check thresholds.
  });

  test.skip("step 4a · delivery reviews and returns for changes (T19)", async ({ page }) => {
    await actAs(page, "delivery");
    await page.reload();
    // Navigate to /sows/{packageId}/approvals; submit request-changes.
    // Assert audit event, notification to submitter.
  });

  test.skip("step 4b · submitter reworks and resubmits (T19)", async ({ page }) => {
    await actAs(page, "submitter");
    await page.reload();
    // Address the change; resubmit; assert version bump.
  });

  test.skip("step 4c · delivery / hr / finance / legal approve on the new version", async ({ page }) => {
    for (const role of ["delivery", "hr", "finance", "legal"] as RoleSlot[]) {
      await actAs(page, role);
      await page.reload();
      // Approve; assert 200 + audit event.
    }
  });

  test.skip("step 5 · CEO exception when below floor (T20)", async ({ page }) => {
    await actAs(page, "ceo");
    await page.reload();
    // If the assessment is below-floor: approve exception with conditions.
    // If compliant: assert /sows/{id}/exception reads "Not required".
  });

  test.skip("step 6 · signature: send, sign, verify executed (T22)", async ({ page }) => {
    // sig service currently gated by W7. Send with test envelope; simulate
    // sign; upload executed doc; verify terms match approved.
  });

  test.skip("step 7 · delivery acceptance + project creation (T23)", async ({ page }) => {
    await actAs(page, "delivery");
    await page.reload();
    // Accept delivery; assert project created exactly once; capture projectId.
    projectId = /* extract */ null;
  });

  test.skip("step 8 · Command center + Reports reconcile to the same package (T39, T42)", async ({ page }) => {
    await actAs(page, "system");
    await page.reload();
    // Command center counts include the package; approval-turnaround
    // aggregate includes its cycle time; export shows the row.
  });

  test.skip("step 9 · renewal shown as two calendar months (T25)", async ({ page }) => {
    // Navigate to /renewals; find the package; assert the renewal
    // trigger date is (term_end - 2 calendar months, month-end clamped,
    // in America/Los_Angeles) — NOT term_end - 60 days.
  });

  test.afterAll(async () => {
    if (!dealId) return;
    // Best-effort cleanup — reap the SOW package + attached rows via
    // the S20-flag on worker/e2e_cleanup.py::_PREFIX_RE (once W1 adds
    // "S20 e2e " to the regex — pending in requests.md).
    try {
      const headers = { ...bearerFor("system"), "Content-Type": "application/json" };
      if (packageId) {
        await fetch(`${BASE}/api/sows/${packageId}?reason=e2e%20cleanup`, {
          method: "DELETE",
          headers,
        });
      }
    } catch {
      /* best-effort */
    }
  });
});
