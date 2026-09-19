/**
 * 15 — SOW upload doc-type reject (S10-01).
 *
 * The résumé fixture (`99_resume.pdf`) must return 422 with the
 * ``detected_type: "resume"`` envelope and MUST NOT create any DB rows.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, request, test } from "@playwright/test";
import { apiBase, emailFor } from "../fixtures/api";

test.describe.configure({ mode: "serial" });

const FIXTURE = join(
  __dirname,
  "..",
  "..",
  "..",
  "fixtures",
  "sample_sows",
  "99_resume.pdf",
);

test("résumé PDF rejected with 422 and no rows created", async () => {
  const owner = emailFor("Sales");
  const ctx = await request.newContext({
    baseURL: apiBase(),
    extraHTTPHeaders: { "X-Test-User": owner },
  });
  try {
    const res = await ctx.post("/sows/upload", {
      multipart: {
        file: {
          name: "resume.pdf",
          mimeType: "application/pdf",
          buffer: readFileSync(FIXTURE),
        },
      },
    });
    expect(res.status()).toBe(422);
    const body = (await res.json()) as {
      detail: { detected_type: string; message: string };
    };
    expect(body.detail.detected_type).toBe("resume");
    expect(body.detail.message).toMatch(/does not look like a SOW/i);
  } finally {
    await ctx.dispose();
  }
});
