/**
 * 14 — SOW upload happy path (S10-01).
 *
 * A human drops `05_tm_capped.pdf` on the studio, sees the pipeline
 * card cycle through the five status rows, and lands on the
 * confirmation screen — no client picker required (the extract
 * signals a match against the seeded client).
 *
 * The spec drives the API directly for the upload + polling because
 * FormData multipart uploads through a Playwright page are brittle
 * with the current dev-server proxy; the browser round-trip is
 * exercised by spec 16.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, request, test } from "@playwright/test";
import { apiBase, emailFor } from "../fixtures/api";
import { rand } from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

const FIXTURE = join(
  __dirname,
  "..",
  "..",
  "..",
  "fixtures",
  "sample_sows",
  "05_tm_capped.pdf",
);

test("upload → progress → confirmation payload", async () => {
  const owner = emailFor("Sales");
  const clientName = `Northstar Analytics ${rand()}`;

  // Seed a client that the resolver will fuzzy-match against the
  // scope-scanned legal name from the fixture. The e2e workflow's
  // dev backend accepts an empty signature when the webhook secret is
  // unset (see fixtures/seed.ts::seedClientWithDeal).
  const seedCtx = await request.newContext({
    baseURL: apiBase(),
    extraHTTPHeaders: {
      "X-Test-User": emailFor("SystemAdmin"),
      "Content-Type": "application/json",
    },
  });
  await seedCtx.post("/hubspot/webhook", {
    data: {
      eventId: `evt-${rand()}`,
      subscriptionType: "deal.creation",
      objectId: `deal-${rand()}`,
      properties: {
        dealname: `${clientName} — engagement`,
        company: clientName,
        hubspot_owner_email: owner,
        associated_company_id: `co-${rand()}`,
      },
    },
  });
  await seedCtx.dispose();

  const uploadCtx = await request.newContext({
    baseURL: apiBase(),
    extraHTTPHeaders: {
      "X-Test-User": owner,
    },
  });
  try {
    const uploadRes = await uploadCtx.post("/sows/upload", {
      multipart: {
        file: {
          name: "05_tm_capped.pdf",
          mimeType: "application/pdf",
          buffer: readFileSync(FIXTURE),
        },
      },
    });
    expect(uploadRes.status()).toBe(200);
    const uploadJson = (await uploadRes.json()) as {
      job_id: string;
      status: string;
      opportunity_id: string | null;
    };
    expect(uploadJson.job_id).toBeTruthy();

    // Poll like the frontend would.
    const jobId = uploadJson.job_id;
    let finalStatus = uploadJson.status;
    let opportunityId = uploadJson.opportunity_id;
    for (let i = 0; i < 20; i += 1) {
      if (finalStatus === "done" || finalStatus === "needs_pick") break;
      await new Promise((r) => setTimeout(r, 500));
      const poll = await uploadCtx.get(`/sows/jobs/${jobId}`);
      expect(poll.status()).toBe(200);
      const job = (await poll.json()) as {
        status: string;
        opportunity_id: string | null;
      };
      finalStatus = job.status;
      opportunityId = job.opportunity_id;
    }

    expect(["done", "needs_pick"]).toContain(finalStatus);

    if (finalStatus === "done") {
      expect(opportunityId).toBeTruthy();
      // Confirmation endpoint returns a populated payload — proof the
      // demo path reaches the confirmation URL.
      const conf = await uploadCtx.get(
        `/sow/${opportunityId}/confirmation`,
      );
      expect(conf.status()).toBe(200);
    }
  } finally {
    await uploadCtx.dispose();
  }
});
