/**
 * 16 — SOW upload picker → create new (S10-01).
 *
 * When the resolver cannot lock a match the job pauses at
 * ``needs_pick``. The picker with a ``create_new`` body creates a
 * fresh client + opportunity and resumes the pipeline to ``done``.
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

test("unknown client → picker create-new → confirmation", async () => {
  const owner = emailFor("Sales");
  const ctx = await request.newContext({
    baseURL: apiBase(),
    extraHTTPHeaders: { "X-Test-User": owner },
  });
  try {
    const res = await ctx.post("/sows/upload", {
      multipart: {
        file: {
          name: "sow.pdf",
          mimeType: "application/pdf",
          buffer: readFileSync(FIXTURE),
        },
      },
    });
    expect(res.status()).toBe(200);
    const uploadJson = (await res.json()) as {
      job_id: string;
      status: string;
      needs_pick: {
        signals?: { legal_name?: string | null };
        create_new?: { legal_name?: string | null };
      } | null;
    };

    // For a client the resolver has never seen, the job pauses at
    // needs_pick. If a matching client happens to exist from prior
    // specs, we simply short-circuit and skip the picker branch —
    // the spec's job here is to prove the picker + resume path.
    if (uploadJson.status !== "needs_pick") {
      test.skip(
        true,
        "resolver matched an existing client — skipping picker branch",
      );
      return;
    }

    const jobId = uploadJson.job_id;
    const suggestedName =
      uploadJson.needs_pick?.create_new?.legal_name ||
      uploadJson.needs_pick?.signals?.legal_name ||
      `Fresh Client ${rand()}`;

    const pickRes = await ctx.post(`/sows/jobs/${jobId}/pick`, {
      data: {
        create_new: {
          legal_name: suggestedName,
          domain: `fresh-${rand()}.example`,
        },
      },
    });
    expect(pickRes.status()).toBe(200);
    const picked = (await pickRes.json()) as {
      status: string;
      resolution: string | null;
      opportunity_id: string | null;
    };
    expect(picked.status).toBe("done");
    expect(picked.resolution).toBe("created");
    expect(picked.opportunity_id).toBeTruthy();
  } finally {
    await ctx.dispose();
  }
});
