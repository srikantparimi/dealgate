import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:5211" });

function syntheticPdf(text: string) {
  const stream = `BT /F1 12 Tf 50 740 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(body));
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body);
  body += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(n => `${String(n).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body);
}

test("T17 agreement presence and immutable replacement downloads through real storage", async ({ page, request }) => {
  test.setTimeout(240_000);
  const f = JSON.parse(readFileSync("/tmp/s21-t17-61d71c0b.json", "utf8"));
  expect(f.database).toBe("s21_t17_61d71c0b4bf7436d957723c632fe1aba");
  const client = f.fixture.client_id;
  const deal = f.fixture.opportunity_id;
  const headers = { "X-Test-User": f.people.owner.email };
  const evidence: unknown[] = [];
  const checkpoint = () => writeFileSync("../../docs/s21/evidence/baseline/t17-agreement-browser.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    database: f.database, boundary: "Local identity adapter; real API, PostgreSQL and S3; not staging", evidence,
  }, null, 2));
  async function get(path: string) {
    const response = await request.get(`http://127.0.0.1:8211${path}`, { headers });
    expect(response.status(), path).toBe(200);
    return response.json();
  }
  expect((await get(`/agreements?client_id=${client}`)).items).toEqual([]);
  const sowBefore = await get(`/sow/opportunity/${deal}/current`);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const originals: Record<string, { id: string; bytes: Buffer }> = {};
  for (const kind of ["NDA", "MSA"]) {
    const name = `s21-t17-${kind.toLowerCase()}-v1.pdf`;
    const bytes = syntheticPdf(`SYNTHETIC TEST ONLY - ${kind} document version 1 - no legal effect.`);
    await page.goto(`/agreements?client_id=${client}&kind=${kind}&upload=1`);
    await expect(page.getByLabel("Client", { exact: true })).toHaveValue(client);
    await expect(page.getByRole("radio", { name: kind, exact: true })).toBeChecked();
    await page.getByLabel("Agreement file").setInputFiles({ name, mimeType: "application/pdf", buffer: bytes });
    const responsePromise = page.waitForResponse(r => r.url().endsWith("/agreements") && r.request().method() === "POST");
    await page.getByRole("dialog").getByRole("button", { name: "Upload", exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    const row = await response.json();
    originals[kind] = { id: row.id, bytes };
    evidence.push({ action: "upload", kind, row }); checkpoint();
    await expect(page.getByRole("table", { name: "Agreements" })).toContainText(name);
  }
  for (const path of [`/clients/${client}`, `/deals/${deal}`, `/sows/${deal}/documents`, `/agreements?client_id=${client}`]) {
    await page.goto(path);
    const presence = page.getByRole("region", { name: "Client NDA and MSA", exact: true });
    await expect(presence).toContainText("NDA: 1 on file");
    await expect(presence).toContainText("MSA: 1 on file");
    evidence.push({ presence: path }); checkpoint();
  }
  const replacement = syntheticPdf("SYNTHETIC TEST ONLY - NDA document version 2 - no legal effect.");
  await page.getByRole("button", { name: "Replace s21-t17-nda-v1.pdf", exact: true }).click();
  await page.getByLabel("Replacement file").setInputFiles({ name: "s21-t17-nda-v2.pdf", mimeType: "application/pdf", buffer: replacement });
  const replacePromise = page.waitForResponse(r => r.url().endsWith(`/agreements/${originals.NDA.id}/replace`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Save replacement", exact: true }).click();
  const replaced = await replacePromise;
  expect(replaced.status()).toBe(200);
  evidence.push({ action: "replace", row: await replaced.json() }); checkpoint();
  const history = await get(`/agreements/${originals.NDA.id}/versions`);
  expect(history.items.map((row: { version_no: number }) => row.version_no)).toEqual([2, 1]);
  for (const [version, bytes] of [[1, originals.NDA.bytes], [2, replacement]] as const) {
    const download = await get(`/agreements/${originals.NDA.id}/versions/${version}/download`);
    const response = await request.get(download.url);
    expect(response.status()).toBe(200);
    expect(await response.body()).toEqual(bytes);
    expect(history.items.find((row: { version_no: number }) => row.version_no === version).file_hash)
      .toBe(createHash("sha256").update(bytes).digest("hex"));
    evidence.push({ download_version: version, sha256: createHash("sha256").update(bytes).digest("hex") }); checkpoint();
  }
  expect((await get(`/agreements?client_id=${client}`)).items).toHaveLength(2);
  const sowAfter = await get(`/sow/opportunity/${deal}/current`);
  for (const sow of [sowBefore, sowAfter]) {
    const response = await request.get(sow.download_url);
    expect(response.status()).toBe(200);
    expect(createHash("sha256").update(await response.body()).digest("hex")).toBe(sow.file_hash);
    sow.download_url = new URL(sow.download_url).origin + new URL(sow.download_url).pathname;
  }
  expect(sowAfter).toEqual(sowBefore);
  expect(errors).toEqual([]);
  evidence.push({ completed: true, sow_unchanged: true }); checkpoint();
});

test("T17 read-only agreement proof continuation after successful writes", async ({ request }) => {
  const receiptPath = "../../docs/s21/evidence/baseline/t17-agreement-browser.json";
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
  expect(receipt.database).toBe("s21_t17_61d71c0b4bf7436d957723c632fe1aba");
  expect(receipt.evidence.filter((e: any) => e.presence)).toHaveLength(4);
  expect(receipt.evidence.filter((e: any) => e.download_version)).toHaveLength(2);
  const f = JSON.parse(readFileSync("/tmp/s21-t17-61d71c0b.json", "utf8"));
  const response = await request.get(`http://127.0.0.1:8211/sow/opportunity/${f.fixture.opportunity_id}/current`, {
    headers: { "X-Test-User": f.people.owner.email },
  });
  expect(response.status()).toBe(200);
  const sow = await response.json();
  expect(sow.id).toBe("d95a10b3-9811-418a-b6ef-958d148c00b7");
  expect(sow.file_hash).toBe("7104c0fe8432aac30032689e0e8d89d6fe752bff0001b730826f08083561c0fc");
  expect(sow.confirmed_at).toBe("2026-10-03T04:23:16.460166Z");
  const bytes = await request.get(sow.download_url);
  expect(bytes.status()).toBe(200);
  expect(createHash("sha256").update(await bytes.body()).digest("hex")).toBe(sow.file_hash);
  receipt.evidence.push({ read_only_continuation: true, sow_id: sow.id, sow_sha256: sow.file_hash,
    limitation: "Original run59018 passed all document assertions; final equality differed only in expiring URL query. Not an uninterrupted green run." });
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
});
