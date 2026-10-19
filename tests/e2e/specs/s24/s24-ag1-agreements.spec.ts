/**
 * S24-AG1 · the NDA & MSA page (Agreements) in a real browser: T9 (Playwright, rule 18) and T14 (accessibility).
 * Every check reads what the user sees: headers, buttons, dialogs, toasts, card numbers and list counts.
 *
 * LOCAL mode (E2E_MODE=local; playwright.s24-local.config.ts sets it). A loopback stack on a seeded database
 * (scripts/s24_ag1_local_seed.py, 29 synthetic clients): SystemAdmin API on 8241, Legal on 8242, Sales on 8243
 * (DEALGATE_TEST_GROUPS is process-wide), S3_STUB=1, DEALGATE_ENV=local, X-Test-User identities; Vite on 5241
 * proxies /api to 8241. The Legal and Sales pages send their API calls to their own API through page routes.
 * The tests run in file order on ONE fresh database: tonight's page, uploads and each rejection, the standard
 * copies, the attach wizard (dry run, ticks, typed confirm, polling, reopen, done), the client panel, Documents,
 * Activity and export, HubSpot hints, Legal, Sales, 375/1440 px in light and dark, T14, undo, then the Pipeline.
 *
 *   stack: scratchpad td/stack.sh reset-db && td/stack.sh start   (the lane's report has the exact commands)
 *   cd tests/e2e && S24_SHOTS=<dir> npx playwright test -c playwright.s24-local.config.ts
 *
 * STAGING mode (E2E_MODE=staging, or E2E_BASE_URL on the staging host). The e2e bot, which sees only its own
 * fixtures, on run-tagged fixture clients (RUN_TAG "S24 e2e <time>"): the six cards equal their lists, the
 * cutover line, Pipeline tags and gap-card wording, the gap card equals the Needs-attention card, a client copy
 * (synthetic bytes) with its download, mark and remove mark, detach, hostile-name escaping, 375/1440 px light and
 * dark. It NEVER uploads a standard copy, runs or undoes a batch, saves or applies a mapping, or touches a real
 * client. afterAll deletes the fixtures and polls their deletion jobs.
 *
 *   E2E_MODE=staging STAGING_E2E_USERNAME=e2e-staging@smartek21.com E2E_BASE_URL=https://app.dealgateapp.com \
 *     S24_SHOTS=/tmp/s24-ag1-shots npx playwright test -c playwright.s24-local.config.ts
 *
 * The staging tests were rehearsed on loopback only (S24_REHEARSE_API: a local API that issues fixtures the way the
 * staging bot does, X-Test-User instead of Cognito); the rehearsal never reaches staging.
 *
 * Screenshots go to S24_SHOTS (default: <os tmpdir>/s24-ag1-shots), never into the repo.
 */
import {
  expect,
  request as pwRequest,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { authStaging, mintStagingTokens } from "../../fixtures/staging-auth";

// --- mode -------------------------------------------------------------------------------------------------

const STAGING_HOST = /app\.dealgateapp\.com|d1mu2un4hj9akj\.cloudfront\.net|dealgate\.smartek21\.com/;
const MODE: "local" | "staging" | "off" =
  process.env.E2E_MODE === "staging"
    ? "staging"
    : process.env.E2E_MODE === "local"
      ? "local"
      : STAGING_HOST.test(process.env.E2E_BASE_URL ?? "")
        ? "staging"
        : "off";

const SHOTS = process.env.S24_SHOTS ?? path.join(os.tmpdir(), "s24-ag1-shots");
const LOCAL_WEB = process.env.S24_LOCAL_WEB ?? "http://127.0.0.1:5241";
type Role = "admin" | "legal" | "sales";
const LOCAL_API: Record<Role, string> = {
  admin: process.env.S24_API_ADMIN ?? "http://127.0.0.1:8241",
  legal: process.env.S24_API_LEGAL ?? "http://127.0.0.1:8242",
  sales: process.env.S24_API_SALES ?? "http://127.0.0.1:8243",
};
// The admin identity is the Vite server's VITE_TEST_USER; the other two only travel through the page routes.
const LOCAL_USER: Record<Role, string> = {
  admin: "admin.local@example.test",
  legal: "legal.local@example.test",
  sales: "sales.local@example.test",
};
const STAGING_BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
/**
 * A loopback rehearsal of the staging tests (never staging): S24_REHEARSE_API names a local API started with
 * DEALGATE_TEST_GROUPS=SystemAdmin,officeapp-e2e, ALLOW_DEV_SEED_ENDPOINT=1 and a DEALGATE_TENANT_ID, which issues
 * fixtures exactly as the staging bot does; identity is X-Test-User instead of Cognito, and the stub storage's
 * download link is checked by its key instead of fetched.
 */
const REHEARSAL = process.env.S24_REHEARSE_API
  ? { api: process.env.S24_REHEARSE_API, web: LOCAL_WEB, user: process.env.S24_REHEARSE_USER ?? "bot.local@example.test" }
  : null;
if (REHEARSAL && !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(REHEARSAL.api)) {
  throw new Error("S24_REHEARSE_API must be a loopback URL");
}
const STAGING_WEB = REHEARSAL ? REHEARSAL.web : STAGING_BASE;

// --- the words the user reads (the approved prototype's copy, as the page renders it) ----------------------

const MSG = {
  type: "Only PDF and Word (.docx) files can be uploaded.",
  tooLarge: "This file is larger than 25 MB.",
  empty: "This file is empty.",
  notPdf: "This file is named .pdf but its contents are not a PDF.",
  notDocx: "This file is named .docx but its contents are not a Word document.",
};
const NOT_SET_TONIGHT =
  "Not set up yet. No NDA or MSA has been uploaded. Existing and net-new are provisional until you attach the standard copies, which also sets the cutover date.";
const NOT_SET_WITH_STANDARD =
  "Not set up yet. Existing and net-new are provisional until you attach the standard copies, which also sets the cutover date.";
const CUTOVER_SENTENCE =
  "Clients that existed at the cutover are covered. Clients created or closing a first deal after it need their own copy.";
const GAP_NOTE = "Net new, past stage 1, NDA or MSA missing";
const PREVIEW_SENTENCE =
  "NDA and MSA show the client's state: Client copy, Standard copy, Marked covered, Missing or Due at stage 2. A warning only; nothing is blocked. The SOW state is separate from the HubSpot sales stage.";
const WRITER_LOCK = "Only Legal and SystemAdmin can change agreements. You can view and download.";
const BULK_LOCK = "Only SystemAdmin can attach standard copies in bulk.";
const CARD_LABELS = [
  "Clients",
  "Existing clients",
  "Net-new clients",
  "Needs attention",
  "Standard copies attached",
  "Client copies on file",
] as const;
type CardLabel = (typeof CARD_LABELS)[number];

// --- the seed (scripts/s24_ag1_local_seed.py) ----------------------------------------------------------------

const HOSTILE = '<img src=x onerror="window.__agXss=1">Hostile & Co';
/** The directive's Needs attention on the seed: net new, an open deal at stage 2-6 or on Hold, NDA or MSA missing. */
const SEED_ATTENTION = [
  HOSTILE,
  "Alder Holdings",
  "Ember Retail",
  "Falcon Capital",
  "Granite Media",
  "Lantern Energy",
  "Meridian Retail, LLC",
  "Pinnacle Motors",
  "Redwood Pharma",
  "Summit Gaming",
  "Unknown company (deal 4417)",
  "Vantage Realty",
].sort();
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const ATTACH_PROGRESS_TEXT = "Attaching in groups of 25. You can leave this open; it keeps running.";

// --- small helpers -----------------------------------------------------------------------------------------

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A minimal, valid, synthetic PDF (no legal content). */
function synthPdf(label: string): Buffer {
  const text = `SYNTHETIC TEST ONLY - ${label} - no legal effect`;
  const stream = `BT /F1 12 Tf 50 740 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, i) => {
    offsets.push(Buffer.byteLength(body));
    body += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body);
  body += `xref\n0 6\n0000000000 65535 f \n${offsets.map((n) => `${String(n).padStart(10, "0")} 00000 n \n`).join("")}`;
  body += `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body);
}

function pdfFile(name: string, label = name) {
  return { name, mimeType: "application/pdf", buffer: synthPdf(label) };
}

/** Synthetic bytes with the Word (zip) signature PK 03 04: what the file rules check, not a real document. */
function docxFile(name: string) {
  return {
    name,
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.concat([Buffer.from([0x50, 0x4b, 0x03, 0x04]), Buffer.from("synthetic test bytes, not a real Word document\n")]),
  };
}

/** Today's calendar date in America/Los_Angeles as the page writes it ("Oct 15, 2026"). */
function pacificToday(): { text: string; iso: string; tomorrowIso: string } {
  const now = new Date();
  const text = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Los_Angeles" });
  const iso = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const tomorrow = new Date(`${iso}T12:00:00Z`);
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  return { text, iso, tomorrowIso: tomorrow.toISOString().slice(0, 10) };
}

async function shot(page: Page, name: string, fullPage = false): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage });
}

/** window.open is recorded instead of opening a tab, so a download link never leaves the test (stub URLs). */
const RECORD_OPEN = () => {
  const w = window as unknown as { __opened: string[]; open: (url?: string | URL) => null };
  w.__opened = [];
  w.open = (url?: string | URL) => {
    w.__opened.push(String(url ?? ""));
    return null;
  };
};

async function openedUrls(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __opened?: string[] }).__opened ?? []);
}

async function expectNoXss(page: Page): Promise<void> {
  expect(await page.evaluate(() => (window as unknown as { __agXss?: unknown }).__agXss)).toBeUndefined();
  expect(await page.locator('img[src="x"]').count()).toBe(0);
}

/** No raw id as text anywhere on the page or in an open dialog. `allow` removes known names first (staging fixtures carry their run id). */
async function expectNoRawUuid(page: Page, allow: string[] = []): Promise<void> {
  let text = await page.evaluate(() => document.body.innerText);
  for (const a of allow) text = text.split(a).join(" ");
  const hit = UUID_RE.exec(text);
  expect(hit, `raw id rendered as text: …${hit ? text.slice(Math.max(0, hit.index - 60), hit.index + 40) : ""}…`).toBeNull();
}

async function expectNoOverflow(page: Page, what: string): Promise<void> {
  const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(scroll, `${what}: page scrollWidth ${scroll} > clientWidth ${client}`).toBeLessThanOrEqual(client);
  const dialogs = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).map((d) => [d.scrollWidth, d.clientWidth]),
  );
  for (const [s, c] of dialogs) expect(s, `${what}: dialog scrollWidth ${s} > clientWidth ${c}`).toBeLessThanOrEqual(c);
}

/** The toasts on screen (the viewport sits inside #root, which is aria-hidden while a drawer is open). */
const toastItems = (page: Page) => page.locator('[aria-label^="Notifications"] li');

/**
 * Close the open drawer with Escape once no toast is on screen. A toast raised from inside a drawer is the newest
 * dismissable layer, so Escape would dismiss it first (reported as an AG1 bug; see the T14 test that pins it).
 */
async function escapeDrawer(page: Page): Promise<void> {
  await expect(toastItems(page)).toHaveCount(0, { timeout: 15_000 });
  // A locked control keeps focus after a click and its reason tooltip stays open; Escape dismisses that tooltip
  // first, as WCAG 1.4.13 asks of content shown on focus, and the next Escape closes the drawer.
  if (await page.locator('[role="tooltip"]').count()) {
    await page.keyboard.press("Escape");
    await expect(page.locator('[role="tooltip"]')).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(1);
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

// --- page pieces ---------------------------------------------------------------------------------------------

const summary = (page: Page) => page.getByRole("region", { name: "Agreement summary" });
const records = (page: Page) => page.getByRole("region", { name: "Agreement records" });
const cardButton = (page: Page, label: CardLabel) =>
  summary(page).getByRole("button").filter({ has: page.getByText(label, { exact: true }) });

async function cardValue(page: Page, label: CardLabel): Promise<number> {
  const raw = (await cardButton(page, label).locator("strong").innerText()).trim();
  if (!/^\d+$/.test(raw)) throw new Error(`card ${label} shows ${raw}`);
  return Number(raw);
}

async function cardNote(page: Page, label: CardLabel): Promise<string> {
  const lines = (await cardButton(page, label).innerText()).split("\n").map((l) => l.trim()).filter(Boolean);
  return lines[lines.length - 1] ?? "";
}

/** The open list's own count line: "N clients · …", "N documents · …", "N events · …". */
async function basisCount(page: Page): Promise<number> {
  const line = records(page).getByText(/^\d+ (clients?|documents?|events?) · /);
  await expect(line).toBeVisible();
  return Number(/^(\d+)/.exec(await line.innerText())![1]);
}

const tabButton = (page: Page, tab: "Clients" | "Documents" | "Activity") =>
  page.getByRole("group", { name: "Records" }).getByRole("button", { name: new RegExp(`^${tab}\\b`) });

async function tabCount(page: Page, tab: "Clients" | "Documents" | "Activity"): Promise<number> {
  const m = /(\d+)\s*$/.exec((await tabButton(page, tab).innerText()).trim());
  if (!m) throw new Error(`tab ${tab} shows no count`);
  return Number(m[1]);
}

async function settled(page: Page): Promise<void> {
  await expect(records(page)).toHaveAttribute("aria-busy", "false");
}

const clientRows = (page: Page) => page.getByRole("table", { name: "Clients" }).locator("tbody tr");
const clientRow = (page: Page, name: string) =>
  clientRows(page).filter({ has: page.getByRole("button", { name, exact: true }) });
const clientNameButton = (page: Page, name: string) =>
  page.getByRole("table", { name: "Clients" }).getByRole("button", { name, exact: true });

async function rowNames(page: Page): Promise<string[]> {
  return (await clientRows(page).locator("[data-row-focus]").allInnerTexts()).map((s) => s.trim());
}

async function openAgreements(page: Page, base: string, query = ""): Promise<void> {
  const answered = page.waitForResponse((r) => r.url().includes("/agreements/workspace") && r.status() === 200);
  await page.goto(`${base}/agreements${query ? `?${query}` : ""}`);
  await answered;
  // A link that names a client opens its panel at once (the page behind is then hidden from assistive tech).
  if (/(^|&)client_id=/.test(query)) {
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.locator("h1")).toContainText("NDA & MSA");
    return;
  }
  await expect(page.getByRole("heading", { level: 1 })).toContainText("NDA & MSA");
  await expect(summary(page).getByRole("button")).toHaveCount(6);
  await settled(page);
}

/** A card click resets the filters and applies its drill: the list then has exactly the card's number (F1/B3). */
async function everyCardEqualsItsList(page: Page): Promise<Record<CardLabel, number>> {
  const seen = {} as Record<CardLabel, number>;
  await tabButton(page, "Clients").click();
  for (const label of CARD_LABELS) {
    const value = await cardValue(page, label);
    await cardButton(page, label).click();
    await expect.poll(async () => (await settledCount(page)) === value, { message: `${label} card ${value}` }).toBe(true);
    expect(await tabCount(page, "Clients"), `${label}: the Clients tab count`).toBe(value);
    const pageSize = Number(await records(page).getByRole("combobox", { name: "Rows" }).inputValue());
    if (value === 0) await expect(records(page).getByText("No clients match this view.")).toBeVisible();
    else await expect(clientRows(page)).toHaveCount(Math.min(value, pageSize));
    seen[label] = value;
  }
  return seen;
}

async function settledCount(page: Page): Promise<number> {
  if ((await records(page).getAttribute("aria-busy")) !== "false") return -1;
  return basisCount(page);
}

/** fetch() from inside the page (through the same routes the page uses) — the server's own answer. */
async function pageFetch(
  page: Page,
  init: { method: string; path: string; json?: unknown; pdf?: { field: string; name: string } },
  testUser?: string,
): Promise<{ status: number; body: string }> {
  return page.evaluate(
    async ({ init, testUser }) => {
      const headers: Record<string, string> = {};
      if (testUser) headers["X-Test-User"] = testUser;
      let body: BodyInit | undefined;
      if (init.json !== undefined) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(init.json);
      } else if (init.pdf) {
        const form = new FormData();
        form.append(init.pdf.field, new Blob(["%PDF-1.4\n% synthetic test bytes\n%%EOF\n"], { type: "application/pdf" }), init.pdf.name);
        body = form;
      }
      const res = await fetch(init.path, { method: init.method, headers, body });
      return { status: res.status, body: await res.text() };
    },
    { init, testUser },
  );
}

// --- T14 probes (run inside the page) -----------------------------------------------------------------------

interface FocusStop {
  name: string;
  tag: string;
  visible: boolean;
  ring: boolean;
  top: number;
  left: number;
  right: number;
  bottom: number;
  inDialog: boolean;
  /** The drawer's own close button (×): conventionally top right and last in the Tab order. */
  dialogClose: boolean;
}

/** What has focus now: its accessible name, whether it is visible, whether a focus ring is drawn, and where it is. */
async function focusStop(page: Page): Promise<FocusStop | null> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return null;
    const text = (n: Element | null) => (n?.textContent ?? "").replace(/\s+/g, " ").trim();
    const nameOf = (e: HTMLElement): string => {
      const by = e.getAttribute("aria-labelledby");
      if (by) {
        const t = by.split(/\s+/).map((id) => text(document.getElementById(id))).join(" ").trim();
        if (t) return t;
      }
      const aria = e.getAttribute("aria-label");
      if (aria?.trim()) return aria.trim();
      const labels = (e as HTMLInputElement).labels;
      if (labels?.length) {
        const t = Array.from(labels).map((l) => text(l)).join(" ").trim();
        if (t) return t;
      }
      if (["BUTTON", "A", "SUMMARY"].includes(e.tagName) || ["button", "link", "tab", "checkbox"].includes(e.getAttribute("role") ?? "")) {
        const t = e.innerText.replace(/\s+/g, " ").trim();
        if (t) return t;
      }
      return e.getAttribute("title") ?? "";
    };
    const box = el instanceof HTMLInputElement && el.type === "file" ? (el.closest("label") ?? el) : el;
    const r = box.getBoundingClientRect();
    const cs = getComputedStyle(box);
    // A date field's calendar button lives in the browser's own shadow DOM: the host does not match :focus-visible
    // then, and the browser draws its own ring on the button (checked on screenshots in both themes).
    const browserPart =
      el instanceof HTMLInputElement && ["date", "time", "datetime-local", "month", "week"].includes(el.type) && !el.matches(":focus-visible");
    const ring =
      browserPart || (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 1) || (cs.boxShadow !== "none" && cs.boxShadow !== "");
    const visible = r.width > 2 && r.height > 2 && cs.visibility !== "hidden" && cs.display !== "none";
    // Positions in content coordinates: add every scrolled ancestor's offset (the drawer and its lists scroll).
    let dy = window.scrollY;
    let dx = window.scrollX;
    for (let n = box.parentElement; n; n = n.parentElement) {
      dy += n.scrollTop;
      dx += n.scrollLeft;
    }
    return {
      name: nameOf(el),
      tag: el.tagName.toLowerCase() + (el.getAttribute("role") ? `[role=${el.getAttribute("role")}]` : ""),
      visible,
      ring,
      top: r.top + dy,
      left: r.left + dx,
      right: r.right + dx,
      bottom: r.bottom + dy,
      inDialog: Boolean(el.closest('[role="dialog"]')),
      dialogClose: el.getAttribute("aria-label") === "Close" && el.parentElement?.getAttribute("role") === "dialog",
    };
  });
}

/** Every visible form control under `rootSelector` and its accessible name (aria-labelledby, aria-label, <label>). */
async function unlabelledControls(page: Page, rootSelector: string): Promise<string[]> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (!root) return [`no element matches ${sel}`];
    const text = (n: Element | null) => (n?.textContent ?? "").replace(/\s+/g, " ").trim();
    const out: string[] = [];
    const controls = root.querySelectorAll<HTMLElement>(
      'input:not([type="hidden"]), select, textarea, [role="combobox"], [role="checkbox"], [role="switch"], [role="radio"]',
    );
    for (const e of Array.from(controls)) {
      const isFile = e instanceof HTMLInputElement && e.type === "file";
      const r = (isFile ? (e.closest("label") ?? e) : e).getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      let name = "";
      const by = e.getAttribute("aria-labelledby");
      if (by) name = by.split(/\s+/).map((id) => text(document.getElementById(id))).join(" ").trim();
      if (!name) name = (e.getAttribute("aria-label") ?? "").trim();
      const labels = (e as HTMLInputElement).labels;
      if (!name && labels?.length) name = Array.from(labels).map((l) => text(l)).join(" ").trim();
      if (!name) out.push(`${e.tagName.toLowerCase()}#${e.id || "?"}${e.getAttribute("role") ? `[role=${e.getAttribute("role")}]` : ""}`);
    }
    return out;
  }, rootSelector);
}

interface ContrastResult {
  checked: number;
  failures: string[];
  samples: string[];
}

/**
 * WCAG contrast of every visible text under `rootSelector`, from getComputedStyle: the text colour against the
 * element's effective background (its own and its ancestors' backgrounds composited). Text in an inactive
 * control (disabled, aria-disabled, locked) and hidden or decorative (aria-hidden) text are exempt, as WCAG 1.4.3
 * allows. Large text (24 px, or 18.66 px bold) needs 3:1, everything else 4.5:1.
 */
async function contrastOf(page: Page, rootSelector: string): Promise<ContrastResult> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (!root) return { checked: 0, failures: [`no element matches ${sel}`], samples: [] };
    type RGBA = [number, number, number, number];
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    const parse = (css: string): RGBA => {
      const m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(css.trim());
      if (m) {
        const a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
        return [Number(m[1]), Number(m[2]), Number(m[3]), a];
      }
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = css;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0]!, d[1]!, d[2]!, d[3]! / 255];
    };
    const over = (top: RGBA, under: RGBA): RGBA => {
      const a = top[3];
      return [top[0] * a + under[0] * (1 - a), top[1] * a + under[1] * (1 - a), top[2] * a + under[2] * (1 - a), 1];
    };
    const lum = (c: RGBA) => {
      const ch = (v: number) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2]);
    };
    const background = (el: Element): RGBA => {
      const layers: RGBA[] = [];
      for (let n: Element | null = el; n; n = n.parentElement) {
        const bg = parse(getComputedStyle(n).backgroundColor);
        if (bg[3] > 0) {
          layers.push(bg);
          if (bg[3] >= 1) break;
        }
      }
      let c: RGBA = [255, 255, 255, 1];
      if (!layers.length || layers[layers.length - 1]![3] < 1) c = parse(getComputedStyle(document.body).backgroundColor);
      for (let i = layers.length - 1; i >= 0; i -= 1) c = over(layers[i]!, c);
      return c;
    };
    const opacity = (el: Element) => {
      let o = 1;
      for (let n: Element | null = el; n; n = n.parentElement) o *= parseFloat(getComputedStyle(n).opacity || "1");
      return o;
    };
    const exempt = (el: Element) =>
      Boolean(el.closest('[aria-hidden="true"], [aria-disabled="true"], [data-locked], :disabled, .sr-only, option, script, style'));
    const failures: string[] = [];
    const samples = new Map<string, string>();
    let checked = 0;
    const visit = (el: Element, sample: string) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || cs.visibility === "hidden" || cs.display === "none") return;
      if (exempt(el)) return;
      const bg = background(el);
      let fg = parse(cs.color);
      fg = [fg[0], fg[1], fg[2], fg[3] * opacity(el)];
      const fgc = over(fg, bg);
      const l1 = lum(fgc);
      const l2 = lum(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const size = parseFloat(cs.fontSize);
      const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
      const need = large ? 3 : 4.5;
      checked += 1;
      const key = `${cs.color} on rgb(${bg.slice(0, 3).map(Math.round).join(",")}) ${large ? "large" : "normal"}`;
      if (!samples.has(key)) samples.set(key, `${ratio.toFixed(2)} ${key} «${sample.slice(0, 40)}»`);
      if (ratio + 1e-6 < need) failures.push(`${ratio.toFixed(2)} < ${need}: «${sample.slice(0, 60)}» ${key}`);
    };
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const seen = new Set<Element>();
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
      const value = (t.nodeValue ?? "").trim();
      const parent = t.parentElement;
      if (!value || !parent || seen.has(parent)) continue;
      seen.add(parent);
      visit(parent, value);
    }
    for (const control of Array.from(root.querySelectorAll<HTMLInputElement | HTMLSelectElement>("select, input"))) {
      const shown = control instanceof HTMLSelectElement ? (control.selectedOptions[0]?.text ?? "") : control.value;
      if (shown.trim() && !(control instanceof HTMLInputElement && ["file", "checkbox", "radio", "hidden"].includes(control.type))) {
        visit(control, shown);
      }
    }
    return { checked, failures: Array.from(new Set(failures)), samples: Array.from(samples.values()) };
  }, rootSelector);
}

// =============================================================================================================
// LOCAL: one seeded database, every role, every dialog
// =============================================================================================================

test.describe("S24-AG1 local stack (E2E_MODE=local)", () => {
  test.skip(MODE !== "local", "local mode needs E2E_MODE=local and the loopback stack (playwright.s24-local.config.ts)");

  let admin: APIRequestContext;
  /** Client name → id, read from the API (never shown; used only for direct server checks). */
  const ids: Record<string, string> = {};

  test.beforeAll(async () => {
    admin = await pwRequest.newContext({
      baseURL: `${LOCAL_API.admin}/`,
      extraHTTPHeaders: { "X-Test-User": LOCAL_USER.admin },
    });
    const ws = await admin.get("agreements/workspace", { params: { page_size: "100" } });
    expect(ws.status(), "the SystemAdmin API on 8241 answers").toBe(200);
    for (const row of ((await ws.json()) as { items: { client_id: string; name: string }[] }).items) ids[row.name] = row.client_id;
    for (const role of ["legal", "sales"] as const) {
      const ping = await admin.get(`${LOCAL_API[role]}/healthz`);
      expect(ping.status(), `the ${role} API answers`).toBe(200);
    }
  });

  test.afterAll(async () => {
    await admin?.dispose();
  });

  async function openAs(
    browser: Browser,
    role: Role,
    opts: { width?: number; height?: number; colorScheme?: "light" | "dark" } = {},
  ): Promise<{ context: BrowserContext; page: Page; errors: string[] }> {
    const context = await browser.newContext({
      viewport: { width: opts.width ?? 1440, height: opts.height ?? 900 },
      colorScheme: opts.colorScheme ?? "light",
      acceptDownloads: true,
    });
    await context.addInitScript(RECORD_OPEN);
    if (role !== "admin") {
      // DEALGATE_TEST_GROUPS is per process: this role's API answers this page.
      await context.route(`${LOCAL_WEB}/api/**`, async (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const target = `${LOCAL_API[role]}${url.pathname.replace(/^\/api/, "")}${url.search}`;
        const response = await route.fetch({ url: target, headers: { ...req.headers(), "x-test-user": LOCAL_USER[role] } });
        await route.fulfill({ response });
      });
    }
    // A stub download link (https://<bucket>.local/…) is never fetched.
    await context.route(/^https:\/\/[^/]+\.local\//, (route) => route.fulfill({ status: 200, body: "stub download" }));
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    return { context, page, errors };
  }

  // -----------------------------------------------------------------------------------------------------------
  test("T9 tonight: the page before any upload reads as the prototype, every card opens a list of its own size, and a hostile name is text", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      // A fresh database: nothing uploaded, no cutover, no activity (the run must start from scripts/s24_ag1_local_seed.py).
      await expect(page.getByText(NOT_SET_TONIGHT, { exact: true }), "fresh seeded database (reset it before a full run)").toBeVisible();

      const header = page.locator("header").filter({ has: page.getByRole("heading", { level: 1 }) });
      await expect(header.getByText("Commercial governance")).toBeVisible();
      await expect(header.getByText("Standard copies cover existing clients and any pipeline clients you choose. Any client can have its own updated copy.")).toBeVisible();
      for (const action of [/^Export view$/, /^HubSpot hints$/, /^Attach standard copies…$/, /^Upload document$/]) {
        await expect(header.getByRole("button", { name: action })).toBeVisible();
      }

      // Six cards, in the contract's order, with the server's notes.
      const labels = await summary(page).getByRole("button").evaluateAll((els) => els.map((b) => b.firstElementChild?.textContent?.trim()));
      expect(labels).toEqual([...CARD_LABELS]);
      expect(await cardNote(page, "Needs attention")).toBe(GAP_NOTE);
      expect(await cardValue(page, "Clients")).toBe(29);
      expect(await cardValue(page, "Standard copies attached")).toBe(0);
      expect(await cardValue(page, "Client copies on file")).toBe(0);

      // The two standard panels say nothing is uploaded yet.
      const standards = page.getByRole("region", { name: "Standard documents" });
      for (const kind of ["NDA", "MSA"]) {
        const panel = standards.getByRole("article", { name: `Standard ${kind}`, exact: true });
        await expect(panel).toContainText("Not uploaded yet. Upload it once, then attach it to every existing client in one step.");
        await expect(panel.getByRole("button", { name: `Upload standard ${kind}`, exact: true })).toBeVisible();
      }

      const seen = await everyCardEqualsItsList(page);
      expect(seen["Clients"]).toBe(seen["Existing clients"] + seen["Net-new clients"]);

      // Needs attention is the directive's set: net new, past stage 1 (Hold counts), NDA or MSA missing.
      await cardButton(page, "Needs attention").click();
      await expect(page.getByRole("button", { name: "Remove Needs attention" })).toBeVisible();
      await expect(page.getByRole("combobox", { name: "Agreement status" })).toHaveValue("attention");
      await expect.poll(async () => (await rowNames(page)).sort()).toEqual(SEED_ATTENTION);
      for (const name of SEED_ATTENTION) {
        await expect(clientRow(page, name).getByRole("button", { name: `Upload client copy for ${name}` })).toBeVisible();
      }
      await expect(clientRow(page, "Lantern Energy")).toContainText("On hold");

      // The whole population: 29 clients on two pages of 25.
      await cardButton(page, "Clients").click();
      await settled(page);
      await expect(records(page).getByText("1–25 of 29")).toBeVisible();
      await expect(records(page).getByText("1 / 2")).toBeVisible();
      await records(page).getByRole("button", { name: "Next page" }).click();
      await expect(records(page).getByText("26–29 of 29")).toBeVisible();
      await expect(clientRows(page)).toHaveCount(4);
      await records(page).getByRole("button", { name: "Previous page" }).click();
      await expect(records(page).getByText("1–25 of 29")).toBeVisible();

      // Flags and states read as the prototype's tags; a business unit is never shown without its region.
      await expect(clientRow(page, "Meridian Retail, LLC")).toContainText("Possible duplicate");
      await expect(clientRow(page, "Unknown company (deal 4417)")).toContainText("Unknown company");
      await expect(clientRow(page, "Orchard Health")).toContainText("Test data");
      await expect(clientRow(page, "Atlas Foods")).toContainText("Existing · none attached");
      await expect(clientRow(page, "Granite Media")).toContainText("Retro Rabbit · South Africa");
      await expect(clientRow(page, "Falcon Capital")).toContainText("IT Avalon · US");
      await page.getByRole("combobox", { name: "Deal stage" }).selectOption("stage_1_only");
      await expect(clientRow(page, "Harbor Labs")).toContainText("Due at stage 2");
      await page.getByRole("button", { name: "Reset filters" }).last().click();

      // F12/T9: the hostile name is plain text in the list; nothing ran and no image was made from it.
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Hostile");
      await expect(clientNameButton(page, HOSTILE)).toBeVisible();
      await expect(clientNameButton(page, HOSTILE)).toHaveText(HOSTILE);
      await expectNoXss(page);
      await page.getByRole("button", { name: "Reset filters" }).last().click();

      // Documents and Activity start empty with the prototype's words.
      await tabButton(page, "Documents").click();
      await expect(records(page).getByText("No documents yet.")).toBeVisible();
      await expect(records(page).getByText("Upload the standard NDA and MSA, or a client copy.")).toBeVisible();
      expect(await tabCount(page, "Documents")).toBe(0);
      await tabButton(page, "Activity").click();
      await expect(records(page).getByText("No agreement activity yet.")).toBeVisible();
      await expect(records(page).getByText("Every upload, attach, mark, undo and download is recorded here and in the audit log.")).toBeVisible();
      await tabButton(page, "Clients").click();

      await expectNoRawUuid(page);
      await expectNoXss(page);
      await shot(page, "local-d1440-light-tonight", true);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 upload: each rejection shows the prototype's message and sends nothing; the server says the same; a real synthetic PDF uploads with its note", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const sent: string[] = [];
      page.on("request", (r) => {
        if (r.url().includes("/client-copy")) sent.push(`${r.method()} ${r.url()}`);
      });
      const opener = page.getByRole("button", { name: "Upload client copy for Pinnacle Motors" });
      await opener.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: "Upload a document" })).toBeVisible();
      await expect(dialog.getByText("Upload", { exact: true }).first()).toBeVisible();
      await expect(dialog.getByLabel("Client", { exact: true })).toHaveValue("Pinnacle Motors");
      await expect(dialog.getByLabel("Document type")).toHaveValue("NDA");
      await expect(dialog.getByLabel("What is this?")).toHaveValue("client");
      await expect(dialog.getByLabel("What is this?")).toBeDisabled();
      await expect(dialog.getByText("PDF or Word (.docx), up to 25 MB")).toBeVisible();

      const input = dialog.locator('input[type="file"]');
      const uploadButton = dialog.getByRole("button", { name: "Upload", exact: true });
      await expect(uploadButton).toBeDisabled();
      const big = Buffer.alloc(26 * 1024 * 1024, 0x20);
      big.write("%PDF-1.4\n", 0);
      const rejections: { file: { name: string; mimeType: string; buffer: Buffer }; message: string; status: number }[] = [
        { file: { name: "notes.pdf", mimeType: "application/pdf", buffer: Buffer.from("Plain text that only pretends to be a PDF.\n") }, message: MSG.notPdf, status: 415 },
        { file: { name: "contract.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("Not a zip container at all.\n") }, message: MSG.notDocx, status: 415 },
        { file: { name: "terms.txt", mimeType: "text/plain", buffer: Buffer.from("plain text terms\n") }, message: MSG.type, status: 415 },
        { file: { name: "empty.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(0) }, message: MSG.empty, status: 422 },
        { file: { name: "big.pdf", mimeType: "application/pdf", buffer: big }, message: MSG.tooLarge, status: 413 },
      ];
      for (const bad of rejections) {
        await input.setInputFiles(bad.file, { timeout: 60_000 }); // the 26 MiB buffer is slow under load
        await expect(dialog.getByRole("alert"), bad.file.name).toHaveText(bad.message);
        await expect(uploadButton).toBeDisabled();
        await expect(dialog.getByText("Will be stored as")).toHaveCount(0);
      }
      await shot(page, "local-d1440-upload-rejected");
      expect(sent, "a rejected file is never sent").toEqual([]);

      // The server refuses the same files with the same words (its answer wins over the browser's check).
      const pinnacle = ids["Pinnacle Motors"]!;
      for (const bad of rejections) {
        const res = await admin.post(`clients/${pinnacle}/agreements/NDA/client-copy`, { multipart: { file: bad.file } });
        expect(res.status(), `server answer for ${bad.file.name}`).toBe(bad.status);
        expect(JSON.stringify(await res.json())).toContain(bad.message);
      }
      const untouched = (await (await admin.get(`clients/${pinnacle}/agreements`)).json()) as { nda: { state: string } };
      expect(untouched.nda.state, "nothing was stored by a refused upload").toBe("missing");

      // A real synthetic PDF: the stored name has exactly one extension; the original name is kept for display.
      const note = "Updated payment terms (synthetic test copy)";
      await input.setInputFiles(pdfFile("pinnacle-nda.pdf.pdf", "Pinnacle NDA"));
      await expect(dialog.getByRole("alert")).toHaveCount(0);
      await expect(dialog.getByText(/^pinnacle-nda\.pdf\.pdf · under 1 KB$/)).toBeVisible();
      await expect(dialog.getByText("Will be stored as")).toBeVisible();
      await expect(dialog.locator("code")).toHaveText("pinnacle-nda.pdf");
      await dialog.getByLabel("Note about this version (optional)").fill(note);

      // Hold the request so the progress state is on screen, and the drawer cannot be closed under it (F2).
      let release: () => void = () => undefined;
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route("**/api/clients/*/agreements/*/client-copy", async (route) => {
        await held;
        await route.continue();
      });
      const saved = page.waitForResponse((r) => r.url().endsWith("/client-copy") && r.request().method() === "POST");
      await uploadButton.click();
      await expect(dialog.getByRole("progressbar", { name: "Upload progress" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(dialog, "the upload in flight keeps its drawer open").toBeVisible();
      release();
      const answer = await saved;
      expect(answer.status()).toBe(201);
      const card = (await answer.json()) as { file_name: string; state: string; note?: string };
      expect(card.state).toBe("client");
      expect(card.file_name).toBe("pinnacle-nda.pdf.pdf");
      await page.unroute("**/api/clients/*/agreements/*/client-copy");
      await expect(page.getByText("Client NDA saved for Pinnacle Motors.").first()).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(opener, "focus returns to the control that opened the dialog").toBeFocused();

      const row = clientRow(page, "Pinnacle Motors");
      await expect(row.locator("td").nth(3)).toContainText("✓ Client copy");
      await expect(row.locator("td").nth(4)).toContainText("Missing");
      expect(await cardValue(page, "Client copies on file")).toBe(1);
      expect(await cardNote(page, "Client copies on file")).toBe("clients · NDA 1 · MSA 0");
      expect(await cardValue(page, "Needs attention"), "the MSA is still missing").toBe(12);

      // The client panel shows the file, its source, who uploaded it and the note; the download is a short link.
      await clientNameButton(page, "Pinnacle Motors").click();
      const panel = page.getByRole("dialog");
      await expect(panel.getByRole("heading", { name: "Pinnacle Motors" })).toBeVisible();
      const nda = panel.getByRole("article", { name: "NDA" });
      await expect(nda).toContainText("✓ Client copy");
      await expect(nda).toContainText("pinnacle-nda.pdf.pdf · under 1 KB");
      await expect(nda).toContainText("Client copy for this client");
      await expect(nda).toContainText(/Uploaded byadmin\.local · [A-Z][a-z]{2} \d{1,2}, \d{4}/);
      await expect(nda).toContainText(note);
      await expect(panel.getByText("This client is net new and past stage 1 with MSA missing. This is a warning only. Nothing is blocked.")).toBeVisible();
      await nda.getByRole("button", { name: /Download/ }).click();
      await expect(page.getByText("A download link for Pinnacle Motors's NDA was created. It expires in 5 minutes and the download is recorded.").first()).toBeVisible();
      const urls = await openedUrls(page);
      expect(urls.at(-1), "the stored key has exactly one extension").toMatch(/\/get\/agreements\/[^?]*-pinnacle-nda\.pdf\?stub=1$/);
      expect(urls.at(-1)).not.toMatch(/\.pdf\.pdf/);
      await expectNoRawUuid(page);
      await escapeDrawer(page);
      await expect(clientNameButton(page, "Pinnacle Motors")).toBeFocused();
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 standard upload: the standard NDA from its panel and the standard MSA from Upload document; a new version is announced", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const standards = page.getByRole("region", { name: "Standard documents" });

      await standards.getByRole("button", { name: "Upload standard NDA", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: "Upload standard NDA" })).toBeVisible();
      await expect(dialog.getByText("Standard copy", { exact: true })).toBeVisible();
      await expect(dialog.getByLabel("What is this?")).toHaveValue("standard");
      await expect(dialog.getByText("This becomes the standard NDA. You attach it to existing clients in one step afterwards.")).toBeVisible();
      await expect(dialog.getByLabel("Client", { exact: true })).toHaveCount(0);
      await dialog.locator('input[type="file"]').setInputFiles(pdfFile("standard-nda.pdf", "Standard NDA"));
      await expect(dialog.locator("code")).toHaveText("standard-nda.pdf");
      const nda = page.waitForResponse((r) => r.url().endsWith("/agreements/standard/NDA") && r.request().method() === "POST");
      await dialog.getByRole("button", { name: "Upload", exact: true }).click();
      expect((await nda).status()).toBe(201);
      await expect(page.getByText("Standard NDA v1 uploaded.").first()).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);

      const ndaPanel = standards.getByRole("article", { name: /^Standard NDA\s*v1$/ });
      await expect(ndaPanel).toContainText("standard-nda.pdf · under 1 KB");
      await expect(ndaPanel).toContainText(new RegExp(`Uploaded by admin\\.local · ${esc(pacificToday().text)} · attached to 0 clients`));
      await expect(ndaPanel).toContainText("A new version does not change copies already attached.");

      // The MSA through the header's Upload document: choosing "Standard copy" and MSA renames the dialog.
      await page.getByRole("button", { name: /Upload document/ }).click();
      await dialog.getByLabel("What is this?").selectOption("standard");
      await dialog.getByLabel("Document type").selectOption("MSA");
      await expect(dialog.getByRole("heading", { name: "Upload standard MSA" })).toBeVisible();
      await expect(dialog.getByText("This becomes the standard MSA. You attach it to existing clients in one step afterwards.")).toBeVisible();
      await dialog.locator('input[type="file"]').setInputFiles(pdfFile("standard-msa.pdf", "Standard MSA"));
      const msa = page.waitForResponse((r) => r.url().endsWith("/agreements/standard/MSA") && r.request().method() === "POST");
      await dialog.getByRole("button", { name: "Upload", exact: true }).click();
      expect((await msa).status()).toBe(201);
      await expect(page.getByText("Standard MSA v1 uploaded.").first()).toBeVisible();
      await expect(standards.getByRole("article", { name: /^Standard MSA\s*v1$/ })).toContainText("standard-msa.pdf · under 1 KB");

      // With a standard copy uploaded, the not-set line no longer says nothing was uploaded (docs/bugs #15).
      await expect(page.getByText(NOT_SET_WITH_STANDARD, { exact: true })).toBeVisible();

      // Download (every role; audited) and the next-version notice.
      await ndaPanel.getByRole("button", { name: "Download the standard NDA" }).click();
      await expect(page.getByText("A download link for the standard NDA was created. It expires in 5 minutes and the download is recorded.").first()).toBeVisible();
      expect((await openedUrls(page)).at(-1)).toMatch(/\/get\/agreements\/standard\/NDA\/[^?]*standard-nda\.pdf\?stub=1$/);
      const next = ndaPanel.getByRole("button", { name: "Upload new version of the standard NDA" });
      await next.click();
      await expect(dialog.getByText("This adds version 2 of the standard NDA. Copies already attached to clients stay as they are.")).toBeVisible();
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(next).toBeFocused();
      await expectNoRawUuid(page);
      await shot(page, "local-d1440-light-standards");
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 attach wizard: the server's dry run, ticks, the typed ATTACH n, polling, reopen shows the running batch, done", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      const preview = (await (
        await admin.post("agreements/batches", { data: { kinds: ["NDA", "MSA"], include_net_new_past_stage_1: true } })
      ).json()) as { will_receive: number; net_new_included: number; already_hold: number; net_new_untouched: number; targets: { name: string; included: boolean; reason: string; relationship: string }[] };
      expect(preview.will_receive).toBe(21);
      await openAgreements(page, LOCAL_WEB);
      const opener = page.getByRole("button", { name: "Attach standard copies…" });
      await opener.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: "Attach standard copies" })).toBeVisible();
      await expect(dialog.getByText("One-time backfill")).toBeVisible();
      await expect(dialog.getByRole("list", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText("1 · Standard copies");
      await expect(dialog.getByRole("checkbox", { name: "Attach the standard NDA" })).toBeChecked();
      await expect(dialog.getByRole("checkbox", { name: "Attach the standard MSA" })).toBeChecked();
      await expect(dialog.getByText(/^standard-nda\.pdf · uploaded .+ by admin\.local$/)).toBeVisible();
      await dialog.getByRole("button", { name: /Review who gets them/ }).click();

      // Step 2: the dry run. The counts are the server's.
      await expect(dialog.getByText("This is a dry run. No client changes yet.")).toBeVisible();
      const count = (label: string) => dialog.locator("dt", { hasText: label }).locator("xpath=following-sibling::dd[1]");
      await expect(count("Clients that will receive copies")).toHaveText(String(preview.will_receive));
      await expect(count("of which net-new clients in the pipeline past stage 1")).toHaveText(String(preview.net_new_included));
      await expect(count("Clients already holding the chosen documents")).toHaveText(String(preview.already_hold));
      await expect(count("Net-new clients not included (stage 1 or no active deal)")).toHaveText(String(preview.net_new_untouched));
      const list = dialog.getByRole("list", { name: "Clients" });
      await expect(list.getByRole("listitem")).toHaveCount(preview.targets.length);
      await expect(list.getByRole("checkbox", { checked: true })).toHaveCount(preview.will_receive);
      for (const t of preview.targets) {
        const box = list.getByRole("checkbox", { name: t.name, exact: true });
        if (t.included) await expect(box).toBeChecked();
        else await expect(box).not.toBeChecked();
      }
      const item = (name: string) => list.getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) });
      await expect(item("Orchard Health")).toContainText("Test data");
      await expect(item("Birch Analytics")).toContainText("Deals only in stage 1");
      await expect(item("Redwood Pharma")).toContainText("Net new · in pipeline");
      await expect(item(HOSTILE)).toContainText("Net new · in pipeline");
      await expectNoXss(page);
      await shot(page, "local-d1440-wizard-step2");

      // Untick one net-new client: the counts follow.
      await list.getByRole("checkbox", { name: "Alder Holdings", exact: true }).click();
      await expect(count("Clients that will receive copies")).toHaveText(String(preview.will_receive - 1));
      await expect(count("of which net-new clients in the pipeline past stage 1")).toHaveText(String(preview.net_new_included - 1));
      await expect(count("Net-new clients not included (stage 1 or no active deal)")).toHaveText(String(preview.net_new_untouched + 1));
      await dialog.getByRole("button", { name: /^Continue/ }).click();

      // Step 3: the typed confirm must be exactly ATTACH n (n from the server's second dry run).
      const n = preview.will_receive - 1;
      const net = preview.net_new_included - 1;
      await expect(dialog.getByRole("list", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText("3 · Confirm and run");
      await expect(dialog.getByText(`You are about to attach NDA and MSA to ${n} clients (${n - net} existing, ${net} net new in the pipeline).`, { exact: false })).toBeVisible();
      const typed = dialog.getByLabel(`Type ATTACH ${n} to confirm`);
      const attach = dialog.getByRole("button", { name: "Attach now" });
      await expect(attach).toBeDisabled();
      await typed.fill(`ATTACH ${n - 1}`);
      await expect(attach).toBeDisabled();
      await typed.fill(`attach ${n}`);
      await expect(attach).toBeDisabled();
      await typed.fill(`ATTACH ${n}`);
      await expect(attach).toBeEnabled();

      // The job runs on the server; the page reads it by polling. Hold the progress answers at "running" so the
      // running state, a close and a reopen can be seen, then let the real answer through.
      let hold = true;
      let polls = 0;
      let realRuns = 0;
      const BATCHES = /\/api\/agreements\/batches(\/[^/?]+)?(\?.*)?$/;
      await page.route(BATCHES, async (route) => {
        const req = route.request();
        if (req.method() === "POST") {
          const body = req.postDataJSON() as { dry_run?: boolean } | null;
          if (body?.dry_run === false) realRuns += 1;
          return route.continue();
        }
        if (req.method() !== "GET" || !hold) return route.continue();
        const res = await route.fetch();
        const json = (await res.json()) as Record<string, unknown> & { items?: Record<string, unknown>[] };
        const running = (b: Record<string, unknown>) => ({ ...b, status: "running", done_count: Math.min(5, Number(b.target_count)), finished_at: null });
        if (Array.isArray(json.items)) {
          if (json.items[0]) json.items[0] = running(json.items[0]);
          return route.fulfill({ response: res, json });
        }
        polls += 1;
        return route.fulfill({ response: res, json: running(json) });
      });
      const started = page.waitForResponse((r) => r.url().endsWith("/agreements/batches") && r.request().method() === "POST" && r.status() === 202);
      await attach.click();
      const batch = (await (await started).json()) as { id: string; status: string; target_count: number };
      expect(batch.id).toMatch(/^AG-\d{4}$/);
      expect(batch.target_count).toBe(n);
      await expect(dialog.getByText(ATTACH_PROGRESS_TEXT)).toBeVisible();
      await expect(dialog.getByRole("progressbar", { name: "Attach progress" })).toBeVisible();
      await expect.poll(() => polls, { message: "the page polls the batch" }).toBeGreaterThanOrEqual(1);
      await expect(dialog.getByRole("progressbar", { name: "Attach progress" })).toHaveAttribute("aria-valuetext", `25% · 5 of ${n} clients`);
      await shot(page, "local-d1440-wizard-running");

      // Close while it runs, then reopen: the dialog follows the running batch and starts nothing new.
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(opener).toBeFocused();
      await opener.click();
      await expect(page.getByRole("dialog").getByText(ATTACH_PROGRESS_TEXT)).toBeVisible();
      await expect(page.getByRole("dialog").getByRole("list", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText("3 · Confirm and run");
      expect(realRuns, "closing and reopening never starts a second batch").toBe(1);

      hold = false;
      const done = page.getByRole("dialog").getByText(`Batch ${batch.id} attached NDA and MSA to ${n} clients.`, { exact: false });
      await expect(done).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("dialog")).toContainText("Done.");
      await expect(page.getByRole("dialog")).toContainText("Every attachment is credited to admin.local and recorded in the audit log.");
      const today = pacificToday().text;
      await expect(page.getByRole("dialog")).toContainText(
        `Existing and net new are now fixed as of ${today}. You can undo this batch from the page header. Undo removes only what this batch attached.`,
      );
      await shot(page, "local-d1440-wizard-done");
      await page.getByRole("dialog").getByRole("button", { name: "Close" }).last().click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.unroute(BATCHES);

      const batches = (await (await admin.get("agreements/batches")).json()) as { items: { id: string; status: string }[] };
      expect(batches.items.map((b) => b.id), "exactly one batch exists").toEqual([batch.id]);
      expect(batches.items[0]!.status).toBe("done");

      // The page: the cutover is set, the latest batch is named, and the cards moved.
      await expect(page.getByText(`Cutover ${today}.`)).toBeVisible();
      await expect(page.getByText(`${CUTOVER_SENTENCE} Latest batch ${batch.id} attached ${n} clients.`, { exact: false })).toBeVisible();
      await expect(page.getByRole("button", { name: `Undo batch ${batch.id}` })).toBeVisible();
      await expect.poll(() => cardValue(page, "Standard copies attached")).toBe(n);
      expect(await cardNote(page, "Standard copies attached")).toBe(`clients · NDA ${n - 1} · MSA ${n}`);
      expect(await cardValue(page, "Needs attention")).toBe(1);
      expect(await cardValue(page, "Existing clients"), "the cutover stamped the same relationships").toBe(11);
      await everyCardEqualsItsList(page);
      await cardButton(page, "Needs attention").click();
      await expect.poll(() => rowNames(page)).toEqual(["Alder Holdings"]);
      await cardButton(page, "Clients").click();
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Redwood");
      const redwood = clientRow(page, "Redwood Pharma");
      await expect(redwood.locator("td").nth(1), "a net-new client that received a copy stays net new").toContainText("Net new");
      await expect(redwood.locator("td").nth(3)).toContainText("✓ Standard copy");
      await expect(redwood.locator("td").nth(4)).toContainText("✓ Standard copy");
      await expectNoRawUuid(page);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 client panel: replace a standard copy with a client copy, remove and re-attach, remove a client copy, mark covered and remove the mark, change relationship", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Granite");
      await expect(clientRows(page)).toHaveCount(1);
      const opener = clientNameButton(page, "Granite Media");
      await opener.click();
      const panel = page.getByRole("dialog");
      await expect(panel.getByRole("heading", { name: "Granite Media" })).toBeVisible();
      await expect(panel.getByText("Client · agreements")).toBeVisible();
      await expect(panel).toContainText("RelationshipNet new");
      await expect(panel).toContainText("Business unitRetro Rabbit· South Africa");
      const nda = panel.getByRole("article", { name: "NDA" });
      const msa = panel.getByRole("article", { name: "MSA" });
      await expect(nda).toContainText("✓ Standard copy");
      await expect(nda).toContainText(`Standard NDA v1 · batch ${label}`);
      await expect(nda.getByRole("button", { name: "Mark covered" }), "a held file is removed before a mark (docs/bugs #29)").toHaveCount(0);

      // Replace the standard copy with this client's own copy: it replaces it for this client only.
      await nda.getByRole("button", { name: "Replace with client copy" }).click();
      await expect(panel.getByRole("heading", { name: "Upload a document" })).toBeVisible();
      await expect(panel.getByText("This client holds the standard NDA. Your upload replaces it for this client only. The standard copy stays for everyone else.")).toBeVisible();
      await panel.locator('input[type="file"]').setInputFiles(pdfFile("granite-nda-v2.pdf", "Granite NDA"));
      await panel.getByLabel("Note about this version (optional)").fill("Changed liability cap (synthetic)");
      const replaced = page.waitForResponse((r) => r.url().endsWith("/client-copy") && r.request().method() === "POST");
      await panel.getByRole("button", { name: "Upload", exact: true }).click();
      expect((await replaced).status()).toBe(201);
      await expect(nda).toContainText("✓ Client copy");
      await expect(nda).toContainText("Client copy for this client");
      await expect(nda).toContainText("granite-nda-v2.pdf");
      await nda.getByText(/^History \(\d+\)$/).click();
      await expect(nda).toContainText("Standard copy replaced with a client copy: granite-nda-v2.pdf");
      await expect(nda.getByRole("button", { name: "Upload new version" })).toBeVisible();
      const others = (await (await admin.get(`clients/${ids["Redwood Pharma"]}/agreements`)).json()) as { nda: { state: string; standard_version: number } };
      expect(others.nda.state, "the other holders keep the standard copy").toBe("standard");

      // Remove the standard MSA from this client only; the shared file stays and can be attached again.
      await msa.getByRole("button", { name: "Remove from client" }).click();
      await expect(panel.getByRole("heading", { name: "Remove MSA from this client" })).toBeVisible();
      await expect(panel.getByText("The standard copy is detached from Granite Media. The shared standard file stays for every other client, and you can attach it again later.")).toBeVisible();
      await panel.getByRole("button", { name: "Remove", exact: true }).click();
      await expect(msa).toContainText("Missing");
      await expect(panel.locator("p:not(.sr-only)", { hasText: /^MSA removed\.$/ }), "the receipt").toBeVisible();
      await expect(panel.getByText("This client is net new and past stage 1 with MSA missing. This is a warning only. Nothing is blocked.")).toBeVisible();
      await msa.getByRole("button", { name: "Attach standard copy" }).click();
      await expect(page.getByText("Standard MSA attached.").first()).toBeVisible();
      await expect(msa).toContainText("✓ Standard copy");
      await expect(msa.getByText(/^Standard MSA v1$/), "a manual attach belongs to no batch").toBeVisible();

      // Remove the client copy: it goes through the deletion job, and the panel says so.
      await nda.getByRole("button", { name: "Remove from client" }).click();
      await expect(panel.getByText("The client copy is removed from Granite Media with all its versions. The stored files are queued for cleanup. This cannot be undone.")).toBeVisible();
      const detached = page.waitForResponse((r) => r.url().endsWith("/agreements/NDA") && r.request().method() === "DELETE");
      await panel.getByRole("button", { name: "Remove", exact: true }).click();
      expect((await detached).status()).toBe(202);
      await expect(panel.getByText("NDA removed. Its stored files are queued for cleanup.")).toBeVisible();
      await expect(panel.getByRole("link", { name: "View cleanup status" })).toBeVisible();
      await expect(nda).toContainText("Missing");

      // Mark covered: the date cannot be in the future; the mark records who, when, why and the note.
      const today = pacificToday();
      await nda.getByRole("button", { name: "Mark covered" }).click();
      await expect(panel.getByRole("heading", { name: "Mark NDA covered" })).toBeVisible();
      await expect(panel.getByText("Use this when the NDA is in place but there is no file to attach here. The warning for this client clears. Records who marked it and why.")).toBeVisible();
      await expect(panel.getByLabel("Reason")).toHaveValue("signed_outside_dealgate");
      await expect(panel.getByLabel("Date it was signed or confirmed")).toHaveValue(today.iso);
      await panel.getByLabel("Date it was signed or confirmed").fill(today.tomorrowIso);
      await panel.getByRole("button", { name: "Mark covered" }).click();
      await expect(panel.getByRole("alert")).toHaveText("The date cannot be in the future.");
      await panel.getByLabel("Date it was signed or confirmed").fill(today.iso);
      await panel.getByLabel("Note (optional)").fill("Confirmed by email (synthetic)");
      await panel.getByRole("button", { name: "Mark covered" }).click();
      await expect(page.getByText("NDA marked covered.").first()).toBeVisible();
      await expect(nda).toContainText("✓ Marked covered");
      await expect(nda).toContainText(`Marked byadmin.local · ${today.text}`);
      await expect(nda).toContainText("ReasonSigned outside DealGate");
      await expect(nda).toContainText("SourceDealGate");
      await expect(nda).toContainText("Confirmed by email (synthetic)");
      await expect(panel.getByText(/This client is net new and past stage 1/)).toHaveCount(0);

      // Remove the mark (soft; history keeps it).
      await nda.getByRole("button", { name: "Remove mark" }).click();
      await expect(panel.getByRole("heading", { name: "Remove NDA mark" })).toBeVisible();
      await expect(panel.getByText("The client goes back to its normal status.")).toBeVisible();
      await panel.getByRole("button", { name: "Remove", exact: true }).click();
      await expect(nda).toContainText("Missing");
      await nda.getByText(/^History \(\d+\)$/).click();
      await expect(nda).toContainText("Mark removed");

      // Change the relationship by hand.
      await panel.getByRole("button", { name: "Change relationship" }).click();
      await expect(panel.getByRole("heading", { name: "Change relationship" })).toBeVisible();
      await expect(panel.getByText("Existing clients are covered by the standard copies. Net-new clients need their own copy. Use this to correct a client, for example a duplicate or a test record.")).toBeVisible();
      await panel.getByLabel("Relationship").selectOption("existing");
      await panel.getByRole("button", { name: "Save" }).click();
      await expect(panel).toContainText("RelationshipExisting");
      await expect(panel).toContainText("Marked existing by admin.local");
      await expect(nda).toContainText("Existing · none attached");
      await expect(panel.getByText(/This client is net new and past stage 1/)).toHaveCount(0);
      await expectNoRawUuid(page);
      await shot(page, "local-d1440-panel-after-actions");
      await escapeDrawer(page);
      await expect(opener).toBeFocused();
      await expect.poll(() => cardValue(page, "Existing clients")).toBe(12);
      expect(await cardValue(page, "Net-new clients")).toBe(17);
      const row = clientRow(page, "Granite Media");
      await expect(row.locator("td").nth(1)).toContainText("Marked existing by admin.local");
      await expect(row.locator("td").nth(3)).toContainText("Existing · none attached");
      await expect(row.locator("td").nth(4)).toContainText("✓ Standard copy");

      // A first client copy from the panel, for a client whose deals are all in stage 1 (a Word file this time).
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Harbor");
      await clientNameButton(page, "Harbor Labs").click();
      const harbor = page.getByRole("dialog");
      const harborNda = harbor.getByRole("article", { name: "NDA" });
      await expect(harborNda).toContainText("Due at stage 2");
      await expect(harborNda).toContainText("Not required until a deal reaches stage 2. You can upload it early.");
      await harborNda.getByRole("button", { name: "Upload client copy" }).click();
      await expect(harbor.getByRole("heading", { name: "Upload a document" })).toBeVisible();
      await expect(harbor.getByLabel("Client", { exact: true })).toHaveValue("Harbor Labs");
      await expect(harbor.getByLabel("Document type")).toHaveValue("NDA");
      await harbor.locator('input[type="file"]').setInputFiles(docxFile("harbor-nda.docx"));
      await expect(harbor.locator("code")).toHaveText("harbor-nda.docx");
      const first = page.waitForResponse((r) => r.url().endsWith("/client-copy") && r.request().method() === "POST");
      await harbor.getByRole("button", { name: "Upload", exact: true }).click();
      expect((await first).status()).toBe(201);
      await expect(harborNda).toContainText("✓ Client copy");
      await expect(harborNda).toContainText("harbor-nda.docx");
      await expect(harbor.getByRole("article", { name: "MSA" })).toContainText("Due at stage 2");
      await escapeDrawer(page);
      await page.getByRole("searchbox", { name: "Search clients" }).fill("");
      await everyCardEqualsItsList(page);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 Documents and Activity: each tab's count follows its list and its search; the export downloads the whole filtered view as CSV", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;

      await tabButton(page, "Documents").click();
      await expect(page.getByRole("searchbox", { name: "Search by client, type, file name or uploader" })).toBeVisible();
      await settled(page);
      const docs = await basisCount(page);
      expect(await tabCount(page, "Documents")).toBe(docs);
      await expect(page.getByRole("table", { name: "Documents" }).locator("tbody tr")).toHaveCount(Math.min(docs, 25));
      await page.getByRole("searchbox", { name: "Search by client, type, file name or uploader" }).fill("Pinnacle");
      await expect.poll(() => settledCount(page)).toBe(2);
      expect(await tabCount(page, "Documents"), "the open tab's count follows its search").toBe(2);
      const docRows = page.getByRole("table", { name: "Documents" }).locator("tbody tr");
      await expect(docRows).toHaveCount(2);
      const clientCopy = docRows.filter({ hasText: "pinnacle-nda.pdf.pdf" });
      await expect(clientCopy).toContainText("Client copy");
      await expect(clientCopy).toContainText("admin.local");
      const standardRow = docRows.filter({ hasText: "standard-msa.pdf" });
      await expect(standardRow).toContainText("Standard v1");
      await expect(standardRow).toContainText(`Batch ${label}`);
      await expect(page.getByRole("button", { name: "Replace Pinnacle Motors NDA" })).toBeVisible();
      await page.getByRole("button", { name: "Download Pinnacle Motors NDA" }).click();
      await expect(page.getByText("A download link for Pinnacle Motors's NDA was created. It expires in 5 minutes and the download is recorded.").first()).toBeVisible();
      const history = page.getByRole("button", { name: "History of Pinnacle Motors NDA" });
      await history.click();
      const drawer = page.getByRole("dialog");
      await expect(drawer.getByRole("heading", { name: "NDA document history" })).toBeVisible();
      await expect(drawer).toContainText("v1: pinnacle-nda.pdf.pdf");
      await expect(drawer).toContainText("Note: Updated payment terms (synthetic test copy)");
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(history).toBeFocused();

      // Activity: newest first, sentences without ids; the count follows the list and its search.
      await tabButton(page, "Activity").click();
      await expect(page.getByRole("searchbox", { name: "Search activity" })).toBeVisible();
      await settled(page);
      const events = await basisCount(page);
      expect(await tabCount(page, "Activity")).toBe(events);
      const activity = page.getByRole("table", { name: "Activity" });
      await expect(activity.locator("tbody tr")).toHaveCount(Math.min(events, 25));
      await page.getByRole("searchbox", { name: "Search activity" }).fill("Pinnacle");
      await settled(page);
      const pinnacleEvents = await settledCount(page);
      expect(await tabCount(page, "Activity")).toBe(pinnacleEvents);
      await expect(activity.locator("tbody tr")).toHaveCount(Math.min(pinnacleEvents, 25));
      await expect(activity).toContainText("Uploaded client NDA for Pinnacle Motors (pinnacle-nda.pdf.pdf)");
      await expect(activity).toContainText("Downloaded NDA for Pinnacle Motors");
      await page.getByRole("searchbox", { name: "Search activity" }).fill(label);
      await expect(activity).toContainText(new RegExp(`Attached standard NDA and MSA to \\d+ clients \\(batch ${label}\\)`));
      await expectNoRawUuid(page);
      await shot(page, "local-d1440-activity");

      // Export: the whole filtered view (every row, not just this page), UTF-8 with BOM, the contract's columns.
      await tabButton(page, "Clients").click();
      await page.getByRole("combobox", { name: "Relationship" }).selectOption("net_new");
      await settled(page);
      const netNew = await basisCount(page);
      const before = await tabCount(page, "Activity");
      const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Export view/ }).click()]);
      const file = download.suggestedFilename();
      expect(file).toMatch(/\.csv$/);
      const csv = fs.readFileSync(await download.path(), "utf8");
      expect(csv.charCodeAt(0), "UTF-8 BOM").toBe(0xfeff);
      const lines = csv.slice(1).split(/\r?\n/).filter(Boolean);
      expect(lines[0]).toBe("Client,Business unit,Relationship,Relationship basis,Furthest open stage,NDA,MSA,Needs attention,Possible duplicate");
      expect(lines.length - 1, "every row of the filtered view").toBe(netNew);
      expect(csv).toContain(`"${HOSTILE.replace(/"/g, '""')}"`);
      expect(csv).toContain("IT Avalon · US");
      await expect(page.getByText(`Downloaded ${file}.`).first()).toBeVisible();
      await expect(page.getByText(`${netNew} clients from the filtered view, every row, not just this page.`).first()).toBeVisible();
      await expect.poll(() => tabCount(page, "Activity"), { message: "the export is recorded" }).toBe(before + 1);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 HubSpot hints: the stored values with client counts, SystemAdmin's choice shows the server's count, nothing is saved by choosing; the not-stored state", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      const values = (await (await admin.get("agreements/hubspot-values")).json()) as {
        stored: boolean;
        items: { value: string; clients: number; action: string; would_mark: number }[];
      };
      expect(values.stored).toBe(true);
      await openAgreements(page, LOCAL_WEB);
      const opener = page.getByRole("button", { name: "HubSpot hints" });
      await opener.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: "HubSpot hints" })).toBeVisible();
      await expect(dialog.getByText("Source: HubSpot")).toBeVisible();
      await expect(dialog).toContainText("Map a value to Covered and the MSA is marked for clients that have no record yet. Clients that already have a file or mark are never changed.");
      await expect(dialog).toContainText("Nothing is saved until you apply. After that, the nightly sync applies the saved mapping after each successful sync.");
      const list = dialog.getByRole("list", { name: "msa_type values" });
      await expect(list.getByRole("listitem")).toHaveCount(values.items.length);
      for (const item of values.items) {
        await expect(list).toContainText(`“${item.value}” ${item.clients} ${item.clients === 1 ? "client" : "clients"}`);
        await expect(dialog.getByLabel(`“${item.value}”`, { exact: false })).toHaveValue("ignore");
      }
      const signed = values.items.find((i) => i.value === "Signed")!;
      await dialog.getByLabel("“Signed”", { exact: false }).selectOption("covered");
      await expect(dialog.getByText(`${signed.would_mark} ${signed.would_mark === 1 ? "client" : "clients"} would be marked.`)).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Apply mapping" })).toBeEnabled();
      await dialog.getByRole("button", { name: "Close" }).last().click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(opener).toBeFocused();
      const after = (await (await admin.get("agreements/hubspot-values")).json()) as { saved_by: string | null; items: { action: string }[] };
      expect(after.saved_by, "choosing saves nothing").toBeNull();
      expect(after.items.every((i) => i.action === "ignore")).toBe(true);

      // The hint on the client panel is a hint only, never a state.
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Redwood");
      await clientNameButton(page, "Redwood Pharma").click();
      const msa = page.getByRole("dialog").getByRole("article", { name: "MSA" });
      await expect(msa).toContainText("HubSpot msa_type: “Signed” hint only");
      await expect(msa).toContainText("✓ Standard copy");
      await escapeDrawer(page);

      // Before the sync stores a value: the not-stored words and a Close button.
      await page.route("**/api/agreements/hubspot-values", (route) =>
        route.fulfill({ json: { stored: false, items: [], saved_by: null, saved_at: null, can_edit: true } }),
      );
      await opener.click();
      await expect(dialog).toContainText("HubSpot's deal record has a property called msa_type. The nightly sync stores its raw value, and the values it finds appear here for you to map. No value has been stored yet.");
      await expect(dialog).toContainText("Nothing is marked automatically until you map a value to “Covered”. DealGate's own record always wins, and marks made here stay even if HubSpot is switched off one day.");
      await shot(page, "local-d1440-hints-not-stored");
      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
      await page.unroute("**/api/agreements/hubspot-values");
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 Legal: writes through the page; the batch, its undo and the mapping are locked, and the server answers 403", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "legal");
    try {
      await openAgreements(page, LOCAL_WEB);
      const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;
      const upload = page.getByRole("button", { name: /Upload document/ });
      await expect(upload).not.toHaveAttribute("data-locked", /.+/);
      const attach = page.getByRole("button", { name: /^Attach standard copies…/ });
      await expect(attach).toHaveAttribute("aria-disabled", "true");
      await expect(attach).toHaveAttribute("data-locked", "admin");
      await expect(attach).toHaveAccessibleDescription(/locked: Only SystemAdmin can do this/);
      await attach.click({ force: true }); // a locked control is aria-disabled, not disabled: the click still lands
      await expect(page.getByText(BULK_LOCK).first()).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      const undo = page.getByRole("button", { name: new RegExp(`^Undo batch ${label}`) });
      await expect(undo).toHaveAttribute("data-locked", "admin");

      // HubSpot hints: Legal reads; choosing and applying are SystemAdmin's.
      await page.getByRole("button", { name: "HubSpot hints" }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByLabel("“Signed”", { exact: false })).toBeDisabled();
      await expect(dialog.getByRole("button", { name: /^Apply mapping/ })).toHaveAttribute("data-locked", "admin");
      await expect(dialog.getByText(/would be marked/)).toHaveCount(0);
      await page.keyboard.press("Escape");

      // Legal writes: mark Alder's MSA covered from the panel.
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Alder");
      await clientNameButton(page, "Alder Holdings").click();
      const panel = page.getByRole("dialog");
      const msa = panel.getByRole("article", { name: "MSA" });
      await expect(msa).toContainText("Missing");
      await expect(msa.getByRole("button", { name: "Mark covered" })).not.toHaveAttribute("data-locked", /.+/);
      await msa.getByRole("button", { name: "Mark covered" }).click();
      await panel.getByLabel("Reason").selectOption("confirmed_with_client");
      await panel.getByRole("button", { name: "Mark covered" }).click();
      await expect(msa).toContainText("✓ Marked covered");
      await expect(msa).toContainText(/Marked bylegal\.local · /);
      await expect(msa).toContainText("ReasonConfirmed with the client");
      await escapeDrawer(page);

      // The server refuses Legal the SystemAdmin-only actions (not only a locked button).
      const preview = await pageFetch(page, { method: "POST", path: "/api/agreements/batches", json: { kinds: ["NDA"], dry_run: true } });
      expect(preview.status, "Legal cannot run a batch, not even a dry run").toBe(403);
      const run = await pageFetch(page, {
        method: "POST",
        path: "/api/agreements/batches",
        json: { kinds: ["NDA"], dry_run: false, idempotency_key: "legal-refused", confirm: "ATTACH 1" },
      });
      expect(run.status).toBe(403);
      expect((await pageFetch(page, { method: "POST", path: `/api/agreements/batches/${label}/undo` })).status).toBe(403);
      expect((await pageFetch(page, { method: "PUT", path: "/api/agreements/hubspot-mapping", json: { items: [{ value: "Signed", action: "covered" }] } })).status).toBe(403);
      expect((await pageFetch(page, { method: "POST", path: "/api/agreements/hubspot-mapping/apply?dry_run=false" })).status).toBe(403);
      const batches = (await (await admin.get("agreements/batches")).json()) as { items: { id: string; status: string }[] };
      expect(batches.items.map((b) => `${b.id} ${b.status}`), "nothing changed").toEqual([`${label} done`]);
      await expectNoRawUuid(page);
      await shot(page, "local-d1440-legal");
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 Sales: every write is locked with its reason, view and download work, and a write sent anyway is refused by the server", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "sales");
    try {
      await openAgreements(page, LOCAL_WEB);
      const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;
      const lockedAs = async (button: Locator, reason: "writer" | "admin") => {
        await expect(button).toHaveAttribute("aria-disabled", "true");
        await expect(button).toHaveAttribute("data-locked", reason);
        await expect(button).toHaveAccessibleDescription(
          reason === "writer" ? /locked: Only Legal and SystemAdmin can change agreements/ : /locked: Only SystemAdmin can do this/,
        );
      };
      const upload = page.getByRole("button", { name: /Upload document/ });
      await lockedAs(upload, "writer");
      await upload.click({ force: true }); // aria-disabled, not disabled: the click lands and explains the lock
      await expect(page.getByText(WRITER_LOCK).first()).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await lockedAs(page.getByRole("button", { name: /^Attach standard copies…/ }), "admin");
      await lockedAs(page.getByRole("button", { name: new RegExp(`^Undo batch ${label}`) }), "admin");
      await page.getByRole("button", { name: "HubSpot hints" }).click();
      const hints = page.getByRole("dialog");
      await expect(hints.getByRole("list", { name: "msa_type values" })).toBeVisible();
      await expect(hints.getByLabel("“Signed”", { exact: false })).toBeDisabled();
      await lockedAs(hints.getByRole("button", { name: /^Apply mapping/ }), "admin");
      await expect(hints.getByText(/would be marked/)).toHaveCount(0);
      await escapeDrawer(page);
      const standards = page.getByRole("region", { name: "Standard documents" });
      await lockedAs(standards.getByRole("button", { name: /^Upload new version of the standard NDA/ }), "writer");
      await lockedAs(standards.getByRole("button", { name: /^Upload new version of the standard MSA/ }), "writer");
      await expect(standards.getByRole("button", { name: "Download the standard MSA" })).not.toHaveAttribute("aria-disabled", "true");
      await cardButton(page, "Needs attention").click();
      await lockedAs(page.getByRole("button", { name: /^Upload client copy for Alder Holdings/ }), "writer");

      // The client panel: every write locked, the download open.
      await cardButton(page, "Clients").click();
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Pinnacle");
      await clientNameButton(page, "Pinnacle Motors").click();
      const panel = page.getByRole("dialog");
      await expect(panel.getByRole("heading", { name: "Pinnacle Motors" })).toBeVisible();
      await lockedAs(panel.getByRole("button", { name: /^Change relationship/ }), "writer");
      const nda = panel.getByRole("article", { name: "NDA" });
      await lockedAs(nda.getByRole("button", { name: /^Upload new version/ }), "writer");
      await lockedAs(nda.getByRole("button", { name: /^Remove from client/ }), "writer");
      const msa = panel.getByRole("article", { name: "MSA" });
      await expect(msa).toContainText("✓ Standard copy");
      await lockedAs(msa.getByRole("button", { name: /^Replace with client copy/ }), "writer");
      await lockedAs(msa.getByRole("button", { name: /^Remove from client/ }), "writer");
      const writes = panel.getByRole("button", { name: /^(Change relationship|Upload|Replace|Remove|Mark covered|Attach standard copy)/ });
      for (const button of await writes.all()) await expect(button).toHaveAttribute("aria-disabled", "true");
      await nda.getByRole("button", { name: /Download/ }).click();
      await expect(page.getByText("A download link for Pinnacle Motors's NDA was created. It expires in 5 minutes and the download is recorded.").first()).toBeVisible();
      expect((await openedUrls(page)).at(-1)).toMatch(/pinnacle-nda\.pdf\?stub=1$/);
      await escapeDrawer(page);

      // Alder: a mark and a missing kind — both locked.
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Alder");
      await clientNameButton(page, "Alder Holdings").click();
      const alder = page.getByRole("dialog");
      await lockedAs(alder.getByRole("article", { name: "MSA" }).getByRole("button", { name: /^Remove mark/ }), "writer");
      await lockedAs(alder.getByRole("article", { name: "NDA" }).getByRole("button", { name: /^Mark covered/ }), "writer");
      await lockedAs(alder.getByRole("article", { name: "NDA" }).getByRole("button", { name: /^Attach standard copy/ }), "writer");
      await lockedAs(alder.getByRole("article", { name: "NDA" }).getByRole("button", { name: /^Upload client copy/ }), "writer");
      await alder.getByRole("article", { name: "NDA" }).getByRole("button", { name: /^Mark covered/ }).click({ force: true });
      await expect(page.getByText(WRITER_LOCK).first()).toBeVisible();
      await expect(alder.getByRole("heading", { name: "Mark NDA covered" })).toHaveCount(0);
      await shot(page, "local-d1440-sales-panel");
      await escapeDrawer(page);

      // Documents: Replace locked, Download open.
      await tabButton(page, "Documents").click();
      await page.getByRole("searchbox", { name: "Search by client, type, file name or uploader" }).fill("Pinnacle");
      await lockedAs(page.getByRole("button", { name: /^Replace Pinnacle Motors NDA/ }), "writer");
      await expect(page.getByRole("button", { name: "Download Pinnacle Motors NDA" })).not.toHaveAttribute("aria-disabled", "true");

      // Writes sent anyway are refused by the server, and nothing changes.
      const before = (await (await admin.get("agreements/workspace")).json()) as { cards: { key: string; value: number }[] };
      const pinnacle = ids["Pinnacle Motors"]!;
      const alderId = ids["Alder Holdings"]!;
      const refused = [
        await pageFetch(page, { method: "PUT", path: `/api/clients/${pinnacle}/relationship`, json: { relationship: "existing" } }),
        await pageFetch(page, { method: "POST", path: `/api/clients/${pinnacle}/agreements/NDA/client-copy`, pdf: { field: "file", name: "sales.pdf" } }),
        await pageFetch(page, { method: "DELETE", path: `/api/clients/${pinnacle}/agreements/MSA` }),
        await pageFetch(page, { method: "PUT", path: `/api/clients/${alderId}/agreements/NDA/mark`, json: { reason: "other", marked_on: pacificToday().iso } }),
        await pageFetch(page, { method: "DELETE", path: `/api/clients/${alderId}/agreements/MSA/mark` }),
        await pageFetch(page, { method: "POST", path: `/api/clients/${alderId}/agreements/NDA/attach-standard` }),
        await pageFetch(page, { method: "POST", path: "/api/agreements/standard/NDA", pdf: { field: "file", name: "sales-standard.pdf" } }),
        await pageFetch(page, { method: "POST", path: "/api/agreements/batches", json: { kinds: ["NDA"] } }),
        await pageFetch(page, { method: "POST", path: `/api/agreements/batches/${label}/undo` }),
      ];
      expect(refused.map((r) => r.status), "every write is a 403 from the server").toEqual(refused.map(() => 403));
      const after = (await (await admin.get("agreements/workspace")).json()) as { cards: { key: string; value: number }[] };
      expect(after.cards).toEqual(before.cards);
      const reads = await pageFetch(page, { method: "GET", path: `/api/clients/${pinnacle}/agreements` });
      expect(reads.status, "Sales can view").toBe(200);
      expect(JSON.parse(reads.body).can_write).toBe(false);
      await expectNoRawUuid(page);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("F12/T9 375 and 1440 px, light and dark: no horizontal overflow on the page or in any dialog", async ({ browser }) => {
    const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;
    for (const [width, height] of [[375, 812], [1440, 900]] as const) {
      for (const colorScheme of ["light", "dark"] as const) {
        const name = `${width === 375 ? "m375" : "d1440"}-${colorScheme}`;
        const { context, page, errors } = await openAs(browser, "admin", { width, height, colorScheme });
        try {
          await openAgreements(page, LOCAL_WEB);
          expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(colorScheme);
          await expectNoOverflow(page, `${name} page`);
          await shot(page, `local-${name}-page`, true);
          for (const tab of ["Documents", "Activity"] as const) {
            await tabButton(page, tab).click();
            await settled(page);
            await expectNoOverflow(page, `${name} ${tab}`);
          }
          await tabButton(page, "Clients").click();
          const dialogs: [string, () => Promise<void>][] = [
            ["upload", () => page.getByRole("button", { name: /Upload document/ }).click()],
            ["wizard", async () => {
              await page.getByRole("button", { name: "Attach standard copies…" }).click();
              await page.getByRole("dialog").getByRole("button", { name: /Review who gets them/ }).click();
              await expect(page.getByRole("dialog").getByText("This is a dry run. No client changes yet.")).toBeVisible();
              await expect(page.getByRole("dialog").getByRole("list", { name: "Clients" })).toBeVisible();
            }],
            ["panel", async () => {
              await page.getByRole("searchbox", { name: "Search clients" }).fill("Hostile");
              await clientNameButton(page, HOSTILE).click();
              await expect(page.getByRole("dialog").getByRole("heading", { name: HOSTILE })).toBeVisible();
            }],
            ["hints", () => page.getByRole("button", { name: "HubSpot hints" }).click()],
            ["undo", async () => {
              await page.getByRole("button", { name: `Undo batch ${label}` }).click();
              await expect(page.getByRole("dialog").getByRole("button", { name: "Undo batch" })).toBeVisible();
            }],
          ];
          for (const [what, open] of dialogs) {
            await open();
            await expect(page.getByRole("dialog")).toBeVisible();
            await page.waitForTimeout(350); // the drawer's slide-in
            await expectNoOverflow(page, `${name} ${what}`);
            await expectNoXss(page);
            await expectNoRawUuid(page);
            if (width === 375 || what === "panel") await shot(page, `local-${name}-${what}`);
            await page.keyboard.press("Escape");
            await expect(page.getByRole("dialog")).toHaveCount(0);
          }
          expect(errors).toEqual([]);
        } finally {
          await context.close();
        }
      }
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T14 page: the Tab order lands on visible, labelled controls in reading order with a visible focus ring; every input is labelled", async ({ browser }) => {
    const { context, page } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      expect(await unlabelledControls(page, "main")).toEqual([]);
      await page.getByRole("heading", { level: 1 }).click(); // the sequential focus starting point
      const stops: FocusStop[] = [];
      for (let i = 0; i < 45; i += 1) {
        await page.keyboard.press("Tab");
        const stop = await focusStop(page);
        if (stop) stops.push(stop);
      }
      const problems: string[] = [];
      stops.forEach((s, i) => {
        if (!s.visible) problems.push(`${i}: ${s.tag} «${s.name}» has focus but is not visible`);
        if (!s.name) problems.push(`${i}: ${s.tag} has no accessible name`);
        if (!s.ring) problems.push(`${i}: ${s.tag} «${s.name}» shows no focus ring`);
        const prev = stops[i - 1];
        if (prev) {
          const up = s.bottom < prev.top - 4 && s.left < prev.right - 1;
          const leftOnLine = Math.abs(s.top - prev.top) < 6 && s.right <= prev.left + 1;
          if (up || leftOnLine) problems.push(`${i}: «${s.name}» comes after «${prev.name}» but sits before it on screen`);
        }
      });
      const names = stops.map((s) => s.name);
      const at = (re: RegExp) => names.findIndex((n) => re.test(n));
      // Reading order: header actions, the cutover line, the six cards, the standard panels, the tabs, the filters, the rows.
      const order = [/^↓\s*Export view/, /^HubSpot hints/, /^Attach standard copies…/, /^↑\s*Upload document/, /^Undo batch AG-/, /^Clients \d+ /, /^Client copies on file/, /^Download the standard NDA/, /^Download the standard MSA/, /^Clients \d+$/, /^Documents \d+$/, /^Activity \d+$/, /^Search clients/, /^Relationship$/];
      const positions = order.map((re) => at(re));
      expect(positions.every((p) => p >= 0), `every landmark control is reached: ${JSON.stringify(names)}`).toBe(true);
      expect([...positions].sort((a, b) => a - b), `reading order: ${JSON.stringify(names)}`).toEqual(positions);
      expect(problems, JSON.stringify(stops.map((s) => s.name))).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T14 dialogs: Escape closes each one and focus returns to its opener; the page behind is inert; focus stays inside; inputs are labelled; focus ring visible", async ({ browser }) => {
    const { context, page } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const label = ((await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] }).items[0]!.id;
      const check = async (what: string, opener: Locator, ready: (dialog: Locator) => Promise<void>) => {
        await opener.focus();
        await page.keyboard.press("Enter");
        const dialog = page.getByRole("dialog");
        await expect(dialog, what).toBeVisible();
        await ready(dialog);
        // The page behind is inert: hidden from assistive tech (Radix marks #root aria-hidden) or inert.
        const inert = await page.evaluate(() => {
          const root = document.getElementById("root");
          return Boolean(root && (root.getAttribute("aria-hidden") === "true" || root.hasAttribute("inert")));
        });
        expect(inert, `${what}: #root is aria-hidden or inert while the dialog is open`).toBe(true);
        expect(await unlabelledControls(page, '[role="dialog"]'), `${what}: unlabelled controls`).toEqual([]);
        // Tab never leaves the dialog, and every stop is named, visible and ringed.
        const problems: string[] = [];
        const stops: FocusStop[] = [];
        for (let i = 0; i < 20; i += 1) {
          await page.keyboard.press("Tab");
          const stop = await focusStop(page);
          if (!stop) continue;
          stops.push(stop);
          if (!stop.inDialog) problems.push(`focus left the dialog to «${stop.name}»`);
          if (!stop.name) problems.push(`${stop.tag} has no accessible name`);
          if (!stop.visible) problems.push(`«${stop.name}» is not visible`);
          if (!stop.ring) problems.push(`«${stop.name}» shows no focus ring`);
        }
        // Reading order over one full Tab cycle: top to bottom, left to right (the close button sits top right, last).
        const key = (s: FocusStop) => `${s.name}|${Math.round(s.top)}|${Math.round(s.left)}`;
        const end = stops.findIndex((s, i) => i > 0 && key(s) === key(stops[0]!));
        const cycle = stops.slice(0, end > 0 ? end : stops.length);
        cycle.forEach((s, i) => {
          const prev = cycle[i - 1];
          if (!prev || s.dialogClose || prev.dialogClose) return;
          const up = s.bottom < prev.top - 4 && s.left < prev.right - 1;
          const leftOnLine = Math.abs(s.top - prev.top) < 6 && s.right <= prev.left + 1;
          if (up || leftOnLine) problems.push(`«${s.name}» comes after «${prev.name}» but sits before it`);
        });
        expect(Array.from(new Set(problems)), `${what}: ${JSON.stringify(cycle.map((s) => s.name))}`).toEqual([]);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("dialog"), `${what}: Escape closes it`).toHaveCount(0);
        await expect(opener, `${what}: focus returns to the opener`).toBeFocused();
      };

      await check("upload", page.getByRole("button", { name: /Upload document/ }), async (d) => {
        await expect(d.getByRole("heading", { name: "Upload a document" })).toBeVisible();
      });
      await check("attach wizard, step 1", page.getByRole("button", { name: "Attach standard copies…" }), async (d) => {
        await expect(d.getByRole("checkbox", { name: "Attach the standard NDA" })).toBeVisible();
      });
      await check("attach wizard, step 2", page.getByRole("button", { name: "Attach standard copies…" }), async (d) => {
        await d.getByRole("button", { name: /Review who gets them/ }).click();
        await expect(d.getByRole("list", { name: "Clients" }).getByRole("checkbox").first()).toBeVisible();
      });
      await check("attach wizard, step 3", page.getByRole("button", { name: "Attach standard copies…" }), async (d) => {
        await d.getByRole("button", { name: /Review who gets them/ }).click();
        await expect(d.getByRole("button", { name: /^Continue/ })).toBeEnabled();
        await d.getByRole("button", { name: /^Continue/ }).click();
        await expect(d.getByLabel(/^Type ATTACH \d+ to confirm$/)).toBeVisible();
      });
      await check("HubSpot hints", page.getByRole("button", { name: "HubSpot hints" }), async (d) => {
        await expect(d.getByRole("list", { name: "msa_type values" })).toBeVisible();
      });
      await check("undo", page.getByRole("button", { name: `Undo batch ${label}` }), async (d) => {
        await expect(d.getByRole("button", { name: "Undo batch" })).toBeVisible();
      });
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Alder");
      // Let the search answer land first: a late answer re-sizes the list and scrolls the page under the check.
      await expect.poll(() => rowNames(page)).toEqual(["Alder Holdings"]);
      await settled(page);
      await check("client panel", clientNameButton(page, "Alder Holdings"), async (d) => {
        await expect(d.getByRole("article", { name: "NDA" })).toBeVisible();
      });
      await check("client panel, mark covered", clientNameButton(page, "Alder Holdings"), async (d) => {
        await d.getByRole("article", { name: "NDA" }).getByRole("button", { name: "Mark covered" }).click();
        await expect(d.getByRole("heading", { name: "Mark NDA covered" })).toBeFocused();
      });
      await check("client panel, change relationship", clientNameButton(page, "Alder Holdings"), async (d) => {
        await d.getByRole("button", { name: "Change relationship" }).click();
        await expect(d.getByLabel("Relationship")).toBeVisible();
      });
      await check("client panel, upload", clientNameButton(page, "Alder Holdings"), async (d) => {
        await d.getByRole("article", { name: "NDA" }).getByRole("button", { name: /Upload client copy/ }).click();
        await expect(d.getByLabel("Note about this version (optional)")).toBeVisible();
      });
      await page.getByRole("searchbox", { name: "Search clients" }).fill("");
      await settled(page);
      await tabButton(page, "Documents").click();
      await page.getByRole("searchbox", { name: "Search by client, type, file name or uploader" }).fill("Pinnacle");
      await expect(page.getByRole("button", { name: "History of Pinnacle Motors NDA" })).toBeVisible();
      await settled(page);
      await check("document history", page.getByRole("button", { name: "History of Pinnacle Motors NDA" }), async (d) => {
        await expect(d.getByRole("heading", { name: "NDA document history" })).toBeVisible();
      });
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T14 Escape closes the client panel at once, also while a toast raised from it is on screen", async ({ browser }) => {
    // AG1 bug #109 (T14/F12), fixed: a toast raised by a drawer action (here a download) is the newest Radix
    // dismissable layer, so Escape used to dismiss that toast and leave the drawer open. The kit's sheet and dialog now
    // hand Escape back to themselves while such a toast is on screen (web/src/ui-v2/primitives/escapeAboveToasts.ts).
    const { context, page } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB, "q=Pinnacle");
      const opener = clientNameButton(page, "Pinnacle Motors");
      await opener.click();
      const panel = page.getByRole("dialog");
      await panel.getByRole("article", { name: "NDA" }).getByRole("button", { name: /Download/ }).click();
      await expect(toastItems(page)).toHaveCount(1);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog"), "one Escape closes the drawer that has focus").toHaveCount(0, { timeout: 3_000 });
      await expect(opener).toBeFocused();
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T14 contrast: every visible text on the page (three tabs), the client panel, the upload dialog, the wizard's three steps, HubSpot hints and undo is at least 4.5:1 (3:1 large), light and dark", async ({ browser }) => {
    const report: string[] = [];
    const failures: string[] = [];
    for (const colorScheme of ["light", "dark"] as const) {
      const { context, page } = await openAs(browser, "admin", { colorScheme });
      try {
        await openAgreements(page, LOCAL_WEB);
        const record = async (what: string, selector: string) => {
          const r = await contrastOf(page, selector);
          expect(r.checked, `${colorScheme} ${what}: texts checked`).toBeGreaterThanOrEqual(4);
          const lowest = [...r.samples].sort((a, b) => parseFloat(a) - parseFloat(b)).slice(0, 3);
          report.push(`${colorScheme} ${what}: ${r.checked} texts, ${r.samples.length} colour pairs; lowest ${lowest.join(" | ")}`);
          failures.push(...r.failures.map((f) => `${colorScheme} ${what}: ${f}`));
        };
        await basisCount(page);
        await record("page, Clients tab", "main");
        await cardButton(page, "Needs attention").click();
        await expect.poll(() => settledCount(page)).toBe(await cardValue(page, "Needs attention"));
        await record("page, Needs attention list", "main");
        await tabButton(page, "Documents").click();
        await expect(page.getByRole("table", { name: "Documents" })).toBeVisible();
        await basisCount(page);
        await record("page, Documents tab", "main");
        await tabButton(page, "Activity").click();
        await expect(page.getByRole("table", { name: "Activity" })).toBeVisible();
        await basisCount(page);
        await record("page, Activity tab", "main");
        await tabButton(page, "Clients").click();
        await basisCount(page);
        await page.getByRole("searchbox", { name: "Search clients" }).fill("Alder");
        await clientNameButton(page, "Alder Holdings").click();
        await expect(page.getByRole("dialog").getByRole("article", { name: "NDA" })).toBeVisible();
        await page.waitForTimeout(350);
        await record("client panel (warning note, states, mark)", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: /Upload document/ }).click();
        await page.getByRole("dialog").locator('input[type="file"]').setInputFiles({ name: "notes.pdf", mimeType: "application/pdf", buffer: Buffer.from("not a pdf") });
        await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
        await page.waitForTimeout(350);
        await record("upload dialog with an error", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Attach standard copies…" }).click();
        await page.getByRole("dialog").getByRole("button", { name: /Review who gets them/ }).click();
        await expect(page.getByRole("dialog").getByRole("list", { name: "Clients" })).toBeVisible();
        await page.waitForTimeout(350);
        await record("attach wizard, step 2", '[role="dialog"]');
        await page.getByRole("dialog").getByRole("button", { name: /^Continue/ }).click();
        await expect(page.getByRole("dialog").getByLabel(/^Type ATTACH \d+ to confirm$/)).toBeVisible();
        await record("attach wizard, step 3", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Attach standard copies…" }).click();
        await expect(page.getByRole("dialog").getByRole("checkbox", { name: "Attach the standard NDA" })).toBeVisible();
        await page.waitForTimeout(350);
        await record("attach wizard, step 1", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "HubSpot hints" }).click();
        await expect(page.getByRole("dialog").getByRole("list", { name: "msa_type values" })).toBeVisible();
        await page.waitForTimeout(350);
        await record("HubSpot hints", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: /^Undo batch AG-/ }).click();
        await expect(page.getByRole("dialog").getByRole("button", { name: "Undo batch" })).toBeVisible();
        await page.waitForTimeout(350);
        await record("undo", '[role="dialog"]');
        await page.keyboard.press("Escape");
        await cardButton(page, "Clients").click(); // the Needs attention drill is still on: back to every client
        await settled(page);
        await page.getByRole("searchbox", { name: "Search clients" }).fill("Pinnacle");
        await clientNameButton(page, "Pinnacle Motors").click();
        await page.getByRole("dialog").getByRole("article", { name: "NDA" }).getByRole("button", { name: "Remove from client" }).click();
        await expect(page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true })).toBeVisible();
        await page.waitForTimeout(350);
        await record("client panel, remove confirmation", '[role="dialog"]');
        await page.keyboard.press("Escape");
      } finally {
        await context.close();
      }
    }
    console.log(`[T14 contrast]\n${report.join("\n")}`);
    // Every text passes, the destructive buttons included (bug #110 fixed: --dg-on-danger).
    expect(failures, failures.join("\n")).toEqual([]);
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T14 contrast: the destructive buttons (the panel's Remove, Undo batch) are at least 4.5:1 in light and dark", async ({ browser }) => {
    // AG1 bug #110 (T14), fixed: the kit's destructive variant was white text on --dg-danger, and the dark theme's
    // --dg-danger is #FF9AAA, so "Undo batch" and the client panel's "Remove" read at about 2.0:1. The variant now uses
    // --dg-on-danger (white in light, #1A1230 in dark).
    const failures: string[] = [];
    for (const colorScheme of ["light", "dark"] as const) {
      const { context, page } = await openAs(browser, "admin", { colorScheme });
      try {
        await openAgreements(page, LOCAL_WEB);
        await page.getByRole("button", { name: /^Undo batch AG-/ }).click();
        await expect(page.getByRole("dialog").getByRole("button", { name: "Undo batch" })).toBeVisible();
        await page.waitForTimeout(350);
        failures.push(...(await contrastOf(page, '[role="dialog"]')).failures.map((f) => `${colorScheme} undo: ${f}`));
        await page.keyboard.press("Escape");
        await page.getByRole("searchbox", { name: "Search clients" }).fill("Pinnacle");
        await clientNameButton(page, "Pinnacle Motors").click();
        await page.getByRole("dialog").getByRole("article", { name: "NDA" }).getByRole("button", { name: "Remove from client" }).click();
        await expect(page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true })).toBeVisible();
        await page.waitForTimeout(350);
        failures.push(...(await contrastOf(page, '[role="dialog"]')).failures.map((f) => `${colorScheme} remove: ${f}`));
        await page.keyboard.press("Escape");
      } finally {
        await context.close();
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9 undo: the count comes from the server and equals the batch's standard rows still in place; client copies, marks and manual attaches stay", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const listed = (await (await admin.get("agreements/batches")).json()) as { items: { id: string }[] };
      const label = listed.items[0]!.id;
      const batch = (await (await admin.get(`agreements/batches/${label}`)).json()) as { undo_would_remove: number };
      // The Documents tab shows the same number: the rows still labelled with this batch.
      await tabButton(page, "Documents").click();
      await page.getByRole("searchbox", { name: "Search by client, type, file name or uploader" }).fill("standard");
      await records(page).getByRole("combobox", { name: "Rows" }).selectOption("100");
      await settled(page);
      await expect(page.getByRole("table", { name: "Documents" })).toBeVisible();
      const batchRows = await page.getByRole("table", { name: "Documents" }).locator("tbody tr").filter({ hasText: `Batch ${label}` }).count();
      expect(batchRows, "Documents rows from this batch").toBe(batch.undo_would_remove);
      const clientCopiesBefore = await cardValue(page, "Client copies on file");
      await tabButton(page, "Clients").click();

      const opener = page.getByRole("button", { name: `Undo batch ${label}` });
      await opener.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: `Undo batch ${label}` })).toBeVisible();
      await expect(dialog.getByText("Undo", { exact: true })).toBeVisible();
      await expect(dialog).toContainText(
        `This removes the ${batch.undo_would_remove} standard attachments made by batch ${label}. It does not touch client copies, marks, or anything attached another way. The standard files and the cutover date stay.`,
      );
      await shot(page, "local-d1440-undo");
      await dialog.getByRole("button", { name: "Undo batch" }).click();
      await expect(page.getByText(`Batch ${label} undone: ${batch.undo_would_remove} attachments removed.`).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole("dialog")).toHaveCount(0);

      // The cutover stays; no active batch; only the manual attach is still a standard copy.
      await expect(page.getByText(`${CUTOVER_SENTENCE} No active batch.`, { exact: false })).toBeVisible();
      await expect(page.getByText(/^Cutover [A-Z][a-z]{2} \d{1,2}, \d{4}\.$/)).toBeVisible();
      await expect(page.getByRole("button", { name: new RegExp(`Undo batch ${label}`) })).toHaveCount(0);
      await expect.poll(() => cardValue(page, "Standard copies attached")).toBe(1);
      expect(await cardValue(page, "Client copies on file"), "client copies made since stay").toBe(clientCopiesBefore);
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Pinnacle");
      const pinnacle = clientRow(page, "Pinnacle Motors");
      await expect(pinnacle.locator("td").nth(3)).toContainText("✓ Client copy");
      await expect(pinnacle.locator("td").nth(4)).toContainText("Missing");
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Alder");
      await expect(clientRow(page, "Alder Holdings").locator("td").nth(4), "marks stay").toContainText("✓ Marked covered");
      await page.getByRole("searchbox", { name: "Search clients" }).fill("Granite");
      await expect(clientRow(page, "Granite Media").locator("td").nth(4), "a manual attach stays").toContainText("✓ Standard copy");
      await page.getByRole("searchbox", { name: "Search clients" }).fill("");
      await everyCardEqualsItsList(page);
      const after = (await (await admin.get(`agreements/batches/${label}`)).json()) as { status: string; undone_by: string };
      expect(after.status).toBe("undone");
      await tabButton(page, "Activity").click();
      await page.getByRole("searchbox", { name: "Search activity" }).fill(label);
      await expect(page.getByRole("table", { name: "Activity" })).toContainText(`Undid batch ${label}: removed ${batch.undo_would_remove} standard attachments`);
      await expectNoRawUuid(page);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });

  // -----------------------------------------------------------------------------------------------------------
  test("T9/T12 Pipeline: the NDA and MSA tags read the shared states, the gap card has the new wording and equals the Needs attention card, and its list has its size", async ({ browser }) => {
    const { context, page, errors } = await openAs(browser, "admin");
    try {
      await openAgreements(page, LOCAL_WEB);
      const attention = await cardValue(page, "Needs attention");
      await cardButton(page, "Needs attention").click();
      await expect.poll(() => settledCount(page)).toBe(attention);
      const answered = page.waitForResponse((r) => r.url().includes("/pipeline/workspace") && r.status() === 200);
      await page.goto(`${LOCAL_WEB}/pipeline?status=open`);
      await answered;
      const cards = page.getByRole("region", { name: "Pipeline summary" });
      const gap = cards.getByRole("button", { name: /^Agreement gaps/ });
      await expect(gap).toContainText(GAP_NOTE);
      const value = Number((await gap.locator("strong").innerText()).trim());
      expect(value, "the Pipeline gap card equals the Agreements Needs attention card").toBe(attention);

      const recordsRegion = page.getByRole("region", { name: "Pipeline records" });
      const dealRow = (client: string) => recordsRegion.locator("tr").filter({ hasText: `${client} deal 1` });
      await expect(dealRow("Pinnacle Motors")).toContainText(/NDA\s*✓ Client copy/);
      await expect(dealRow("Pinnacle Motors")).toContainText(/MSA\s*Missing/);
      await expect(dealRow("Alder Holdings")).toContainText(/MSA\s*✓ Marked covered/);
      await expect(dealRow("Alder Holdings")).toContainText(/NDA\s*Missing/);
      await expect(dealRow("Granite Media")).toContainText(/NDA\s*Existing · none attached/);
      await expect(dealRow("Granite Media")).toContainText(/MSA\s*✓ Standard copy/);
      await expect(dealRow("Harbor Labs")).toContainText(/NDA\s*✓ Client copy/);
      await expect(dealRow("Harbor Labs")).toContainText(/MSA\s*Due at stage 2/);
      await expect(recordsRegion.getByText("NDA missing")).toHaveCount(0);
      await expect(recordsRegion.getByText("NDA on file")).toHaveCount(0);

      // The deal preview explains the states; the client preview carries the shared panel.
      await recordsRegion.getByRole("button", { name: /^Pinnacle Motors deal 1$/ }).first().click();
      const preview = page.getByRole("dialog");
      await expect(preview.getByText(PREVIEW_SENTENCE)).toBeVisible();
      await shot(page, "local-d1440-pipeline-deal-preview");
      await page.keyboard.press("Escape");

      // The gap card opens a client list of exactly its size.
      await gap.click();
      await expect(page).toHaveURL(/tab=clients/);
      await expect(page).toHaveURL(/missing=agreements/);
      const line = page.getByText(/^(\d+) clients? · /).first();
      await expect.poll(async () => Number(/^(\d+)/.exec(await line.innerText())![1])).toBe(value);
      await expectNoXss(page);
      await shot(page, "local-d1440-pipeline-gap-list", true);

      // F6's seventh state: Willow Farms is net new with only a Closed Lost deal, so nothing is needed now.
      const everyStatus = page.waitForResponse((r) => r.url().includes("/pipeline/workspace") && r.status() === 200);
      await page.goto(`${LOCAL_WEB}/pipeline?status=lost&q=Willow`);
      await everyStatus;
      const allRecords = page.getByRole("region", { name: "Pipeline records" });
      const willow = allRecords.locator("tr").filter({ hasText: "Willow Farms deal 1" });
      await expect(willow).toContainText(/NDA\s*Not needed now/);
      await expect(willow).toContainText(/MSA\s*Not needed now/);
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });
});

// =============================================================================================================
// STAGING: the e2e bot on run-tagged fixtures only (the lead runs this after the deploy)
// =============================================================================================================

test.describe("S24-AG1 on staging (E2E_MODE=staging): run-tagged fixtures only", () => {
  test.skip(MODE !== "staging", "staging mode needs E2E_MODE=staging (the lead runs it after the deploy)");
  test.describe.configure({ mode: "serial" });

  const RUN_TAG = `S24 e2e ${Date.now()}`;
  const HOSTILE_LABEL = "<img src=x onerror=window.__agXss=1> Hostile & Co";
  type Fixture = { client_id: string; opportunity_id: string; name: string };
  const fixtures: Record<string, Fixture> = {};
  let api: APIRequestContext;

  async function json<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
    if (!res.ok()) throw new Error(`${res.status()} ${res.url()}: ${(await res.text()).slice(0, 300)}`);
    return (await res.json()) as T;
  }

  async function issue(key: string, label: string, pipelineDeal: Record<string, unknown>): Promise<void> {
    const body = await json<{ client_id: string; opportunity_id: string }>(
      await api.post("dev/test-fixtures", { data: { label: `${RUN_TAG} ${label}`, reviewer_ids: [], hours: 4, pipeline_deal: pipelineDeal } }),
    );
    const panel = await json<{ name: string }>(await api.get(`clients/${body.client_id}/agreements`));
    fixtures[key] = { client_id: body.client_id, opportunity_id: body.opportunity_id, name: panel.name };
  }

  /** Fixture names carry their run id (S21 isolation); they are the only ids allowed on screen. */
  const fixtureNames = () => Object.values(fixtures).map((f) => f.name);

  async function stagingPage(page: Page): Promise<void> {
    if (REHEARSAL) {
      const { api: target, web, user } = REHEARSAL;
      await page.context().route(`${web}/api/**`, async (route) => {
        const req = route.request();
        const url = new URL(req.url());
        const response = await route.fetch({ url: `${target}${url.pathname.replace(/^\/api/, "")}${url.search}`, headers: { ...req.headers(), "x-test-user": user } });
        await route.fulfill({ response });
      });
    } else {
      await authStaging(page, STAGING_BASE);
    }
    await page.addInitScript(RECORD_OPEN);
  }

  test.beforeAll(async () => {
    if (REHEARSAL) {
      api = await pwRequest.newContext({ baseURL: `${REHEARSAL.api}/`, extraHTTPHeaders: { "X-Test-User": REHEARSAL.user } });
    } else {
      const { idToken } = mintStagingTokens();
      api = await pwRequest.newContext({
        baseURL: `${STAGING_BASE}/api/`,
        extraHTTPHeaders: { Authorization: `Bearer ${idToken}` },
        timeout: 90_000,
      });
    }
    await issue("copy", "Agreements client copy", { stage: 3, amount: "40000.00", region: "US", owner: "none", close_in_days: 30 });
    await issue("hostile", HOSTILE_LABEL, { stage: 2, amount: "25000.00", region: "South Africa", owner: "none", close_in_days: 20 });
    await issue("stage1", "Early talks", { stage: 1, amount: "10000.00", region: "US - IT Avalon", owner: "none", close_in_days: 60 });
  });

  test.afterAll(async () => {
    try {
      for (const f of Object.values(fixtures)) {
        const del = await api.delete(`clients/${f.client_id}`, { params: { reason: "S24 AG1 spec teardown" } });
        const body = (await del.json().catch(() => ({}))) as { job_id?: string };
        for (let i = 0; body.job_id && i < 60; i += 1) {
          const state = (await (await api.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
          if (state.status === "done" || state.status === "failed") break;
          await new Promise((r) => setTimeout(r, 2_000));
        }
      }
    } finally {
      await api?.dispose();
    }
  });

  test("staging T9: the six cards equal their lists, the cutover line reads as the server says, and the hostile fixture name is text", async ({ page }) => {
    await stagingPage(page);
    const ws = await json<{ cutover: { set: boolean }; standard: { NDA: unknown; MSA: unknown } }>(await api.get("agreements/workspace"));
    await openAgreements(page, STAGING_WEB);
    if (!ws.cutover.set) {
      await expect(page.getByText(ws.standard.NDA || ws.standard.MSA ? NOT_SET_WITH_STANDARD : NOT_SET_TONIGHT, { exact: true })).toBeVisible();
    } else {
      await expect(page.getByText(/^Cutover [A-Z][a-z]{2} \d{1,2}, \d{4}\.$/)).toBeVisible();
      await expect(page.getByText(CUTOVER_SENTENCE, { exact: false })).toBeVisible();
    }
    expect(await cardNote(page, "Needs attention")).toBe(GAP_NOTE);
    await everyCardEqualsItsList(page);
    await cardButton(page, "Clients").click();
    await page.getByRole("searchbox", { name: "Search clients" }).fill(RUN_TAG);
    await expect.poll(() => settledCount(page)).toBe(3);
    await expect(clientNameButton(page, fixtures.hostile!.name)).toHaveText(fixtures.hostile!.name);
    await expect(clientRow(page, fixtures.copy!.name).locator("td").nth(3)).toContainText("Missing");
    await expect(clientRow(page, fixtures.stage1!.name).locator("td").nth(3)).toContainText("Due at stage 2");
    await expectNoXss(page);
    await expectNoRawUuid(page, fixtureNames());
    await shot(page, "staging-d1440-light-agreements", true);
  });

  test("staging T9/T12: Pipeline tags and gap-card wording; the gap card equals the Agreements Needs attention card", async ({ page }) => {
    await stagingPage(page);
    await openAgreements(page, STAGING_WEB);
    const attention = await cardValue(page, "Needs attention");
    const answered = page.waitForResponse((r) => r.url().includes("/api/pipeline/workspace") && r.status() === 200);
    await page.goto(`${STAGING_WEB}/pipeline?status=open`);
    await answered;
    const gap = page.getByRole("region", { name: "Pipeline summary" }).getByRole("button", { name: /^Agreement gaps/ });
    await expect(gap).toContainText(GAP_NOTE);
    expect(Number((await gap.locator("strong").innerText()).trim()), "Pipeline gap card = Agreements Needs attention").toBe(attention);
    const recordsRegion = page.getByRole("region", { name: "Pipeline records" });
    const row = (f: Fixture) => recordsRegion.locator("tr").filter({ hasText: f.name });
    await expect(row(fixtures.copy!).first()).toContainText(/NDA\s*Missing/);
    await expect(row(fixtures.copy!).first()).toContainText(/MSA\s*Missing/);
    await expect(row(fixtures.stage1!).first()).toContainText(/NDA\s*Due at stage 2/);
    await recordsRegion.getByRole("button", { name: new RegExp(`^${esc(fixtures.copy!.name)}$`) }).first().click();
    await expect(page.getByRole("dialog").getByText(PREVIEW_SENTENCE)).toBeVisible();
    await page.keyboard.press("Escape");
    await gap.click();
    const line = page.getByText(/^(\d+) clients? · /).first();
    await expect.poll(async () => Number(/^(\d+)/.exec(await line.innerText())![1])).toBe(attention);
    await expectNoXss(page);
    await shot(page, "staging-d1440-pipeline-gap", true);
  });

  test("staging T9: on a run-tagged fixture only — a client copy (synthetic bytes) and its download, mark and remove mark, detach", async ({ page }) => {
    await stagingPage(page);
    const fixture = fixtures.copy!;
    await openAgreements(page, STAGING_WEB, `client_id=${fixture.client_id}`);
    const panel = page.getByRole("dialog");
    await expect(panel.getByRole("heading", { name: fixture.name })).toBeVisible();
    const nda = panel.getByRole("article", { name: "NDA" });
    const msa = panel.getByRole("article", { name: "MSA" });
    await expect(nda).toContainText("Missing");
    await nda.getByRole("button", { name: /Upload client copy/ }).click();
    const bytes = synthPdf(`${RUN_TAG} fixture NDA`);
    await panel.locator('input[type="file"]').setInputFiles({ name: "s24-e2e-nda.pdf", mimeType: "application/pdf", buffer: bytes });
    await panel.getByLabel("Note about this version (optional)").fill(`${RUN_TAG} synthetic copy`);
    const saved = page.waitForResponse((r) => r.url().endsWith("/client-copy") && r.request().method() === "POST");
    await panel.getByRole("button", { name: "Upload", exact: true }).click();
    expect((await saved).status()).toBe(201);
    await expect(nda).toContainText("✓ Client copy");
    await nda.getByRole("button", { name: /Download/ }).click();
    await expect(page.getByText(/A download link for .*'s NDA was created\. It expires in 5 minutes and the download is recorded\./).first()).toBeVisible();
    const url = (await openedUrls(page)).at(-1)!;
    expect(url, "a fixture's object is keyed under its run (T11)").toContain("/agreements/e2e/");
    expect(url).toMatch(/s24-e2e-nda\.pdf/);
    if (!REHEARSAL) {
      // The presigned link itself (no Authorization header: it carries its own signature).
      const plain = await pwRequest.newContext();
      try {
        const got = await plain.get(url);
        expect(got.status()).toBe(200);
        expect(Buffer.compare(await got.body(), bytes), "the download returns the uploaded bytes").toBe(0);
      } finally {
        await plain.dispose();
      }
    }

    await msa.getByRole("button", { name: "Mark covered" }).click();
    await panel.getByLabel("Note (optional)").fill(`${RUN_TAG} synthetic mark`);
    await panel.getByRole("button", { name: "Mark covered" }).click();
    await expect(msa).toContainText("✓ Marked covered");
    await msa.getByRole("button", { name: "Remove mark" }).click();
    await panel.getByRole("button", { name: "Remove", exact: true }).click();
    await expect(msa).toContainText("Missing");

    await nda.getByRole("button", { name: "Remove from client" }).click();
    const detached = page.waitForResponse((r) => r.url().endsWith("/agreements/NDA") && r.request().method() === "DELETE");
    await panel.getByRole("button", { name: "Remove", exact: true }).click();
    expect((await detached).status()).toBe(202);
    await expect(panel.getByText("NDA removed. Its stored files are queued for cleanup.")).toBeVisible();
    await expect(nda).toContainText("Missing");
    await expectNoXss(page);
    await expectNoRawUuid(page, fixtureNames());
    await shot(page, "staging-d1440-fixture-panel");
  });

  test("staging F12: 375 and 1440 px, light and dark — no horizontal overflow on the page or the fixture's panel", async ({ browser }) => {
    for (const [width, height] of [[375, 812], [1440, 900]] as const) {
      for (const colorScheme of ["light", "dark"] as const) {
        const name = `${width === 375 ? "m375" : "d1440"}-${colorScheme}`;
        const context = await browser.newContext({ viewport: { width, height }, colorScheme });
        const page = await context.newPage();
        try {
          await stagingPage(page);
          await openAgreements(page, STAGING_WEB);
          await expectNoOverflow(page, `${name} page`);
          await shot(page, `staging-${name}-page`, true);
          await openAgreements(page, STAGING_WEB, `client_id=${fixtures.hostile!.client_id}`);
          await expect(page.getByRole("dialog").getByRole("heading", { name: fixtures.hostile!.name })).toBeVisible();
          await page.waitForTimeout(350);
          await expectNoOverflow(page, `${name} panel`);
          await expectNoXss(page);
          await shot(page, `staging-${name}-panel`);
        } finally {
          await context.close();
        }
      }
    }
  });
});
