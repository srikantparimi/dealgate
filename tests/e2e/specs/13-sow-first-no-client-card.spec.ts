/**
 * 13 — SOW-first no-client-card (S9 wave 2).
 *
 * Upload `03_fixed_price_mixed.pdf` for a client with no rate card.
 * The confirmation screen must:
 *   - Show exactly one inline request "This client has no rate card
 *     yet" with a link to `/settings/rates/client-cards/:client_id`.
 *   - Render a loud fallback warning on the package.
 *   - Once the user creates the client card, reloading the
 *     confirmation drops the warning.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import {
  applyTestUser,
  publishClientRateCard,
  seedClientRateCardMissing,
  seedFixtureSow,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("no client rate card → exactly one inline request + fallback warning; clears after publish", async ({
  page,
}) => {
  const seeded = await seedClientRateCardMissing({});
  expect(seeded.cardMissing).toBe(true);

  const sow = await seedFixtureSow(
    seeded.opportunityId,
    "03_fixed_price_mixed.pdf",
    "Sales",
  );
  expect(sow.expectedEngagementType).toBe("fixed_price");

  // 1. The `/clients/:id/rate-card` endpoint reports the fallback
  // state with the loud warning copy the confirmation surface reuses.
  const card = await apiFetch<{
    card: unknown | null;
    has_fallback: boolean;
    warning: string | null;
  }>("Sales", "GET", `/clients/${seeded.clientId}/rate-card`);
  expect(card.json.card).toBeNull();
  expect(card.json.has_fallback).toBe(true);
  expect(card.json.warning ?? "").toMatch(/no client rate card/i);

  // 2. Browser round-trip — the confirmation screen carries exactly
  // one inline request and links to the client-cards settings page.
  await applyTestUser(page, "Sales");
  await page.goto(`/deals/${seeded.opportunityId}`);
  await expect(page.getByRole("heading", { name: /^sow$/i })).toBeVisible();

  const rateCardRequest = page.getByText(
    /this client has no rate card yet/i,
  );
  // "Exactly one inline request" — the design rule 7 chip appears
  // once on the package. If a spec regression fires the request
  // twice, the count assertion below fails loudly.
  await expect(rateCardRequest).toHaveCount(1);
  const link = page.getByRole("link", {
    name: /rate card|client card|create card/i,
  });
  await expect(link.first()).toBeVisible();
  const href = await link.first().getAttribute("href");
  expect(href).toContain(`/settings/rates/client-cards/${seeded.clientId}`);

  // 3. Loud fallback warning is visible on the package summary.
  await expect(
    page.getByText(/company default was used|fallback|company-default/i).first(),
  ).toBeVisible();

  // 4. User publishes the client rate card (in a real flow this is
  // the Finance persona opening the settings page). After publish,
  // reloading the confirmation drops the warning.
  const published = await publishClientRateCard(seeded.clientId);
  expect(published.id).not.toBeNull();

  await page.reload();
  await expect(rateCardRequest).toHaveCount(0);
  await expect(
    page.getByText(/company default was used|fallback|company-default/i),
  ).toHaveCount(0);

  // API mirror — the `/rate-card` endpoint now returns the card and no
  // fallback warning.
  const afterCard = await apiFetch<{
    card: { id: string } | null;
    has_fallback: boolean;
    warning: string | null;
  }>("Sales", "GET", `/clients/${seeded.clientId}/rate-card`);
  expect(afterCard.json.card).not.toBeNull();
  expect(afterCard.json.has_fallback).toBe(false);
  expect(afterCard.json.warning).toBeNull();
});
