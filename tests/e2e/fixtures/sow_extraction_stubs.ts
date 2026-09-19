/**
 * SOW extraction stubs — TS loader for the fixture PDFs (S9 wave 2).
 *
 * Source of truth: `fixtures/sample_sows/extraction_stubs.py`. The
 * generator (`fixtures/sample_sows/generate.py`) emits
 * `extraction_stubs.json` alongside the PDFs — this module loads that
 * JSON so the TS + Python sides never disagree on what "the extract"
 * should have produced for a given fixture.
 *
 * Regenerate:
 *
 *   cd api && . .venv/bin/activate
 *   python ../fixtures/sample_sows/generate.py
 *
 * A validating pytest lives at
 * `fixtures/sample_sows/test_extraction_stubs.py`.
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export interface ExtractedField {
  value: unknown;
  page_ref: number;
  status: "unconfirmed" | "disputed";
}

export interface FixtureStub {
  /** Schema fields — validated by `bedrock_sow_extract.validate_extract`. */
  fields: Record<string, ExtractedField>;
  /** Auxiliary hints (resource_table, monthly_fee, …) — not schema-validated. */
  aux: Record<string, unknown>;
  expected_engagement_type: string;
  expected_rule: string;
}

export type FixtureName =
  | "01_staff_aug_us.pdf"
  | "02_managed_service_india.pdf"
  | "03_fixed_price_mixed.pdf"
  | "04_assessment_4week.pdf"
  | "05_tm_capped.pdf"
  | "06_below_floor.pdf";

/** Absolute path to the shared fixtures directory.
 *
 * Playwright's test runner transpiles TS to CommonJS, so `import.meta`
 * is not available. `__dirname` is injected by the transpile shim; we
 * fall back to the well-known repo-relative path when neither is set.
 */
export function fixturesRoot(): string {
  const here =
    typeof __dirname === "string"
      ? __dirname
      : dirname(resolve(process.cwd(), "tests/e2e/fixtures/sow_extraction_stubs.ts"));
  return resolve(here, "..", "..", "..", "fixtures", "sample_sows");
}

let _cache: Record<FixtureName, FixtureStub> | null = null;

/** Load `extraction_stubs.json` once per process. */
export function loadStubMap(): Record<FixtureName, FixtureStub> {
  if (_cache) return _cache;
  const path = join(fixturesRoot(), "extraction_stubs.json");
  const raw = readFileSync(path, "utf8");
  _cache = JSON.parse(raw) as Record<FixtureName, FixtureStub>;
  return _cache;
}

/** Return one fixture's canonical stub payload. */
export function stubFor(name: FixtureName): FixtureStub {
  const map = loadStubMap();
  const entry = map[name];
  if (!entry) {
    throw new Error(
      `unknown fixture ${name}; known: ${Object.keys(map).join(", ")}`,
    );
  }
  return entry;
}

/** Absolute path to a fixture's PDF on disk. */
export function pdfPathFor(name: FixtureName): string {
  return join(fixturesRoot(), name);
}
