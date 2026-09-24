/**
 * Rule 13 completeness test. A blocker key with no inline editor is
 * itself a bug — adding a blocker to the server without adding an entry
 * here must fail the build.
 *
 * The canonical list below mirrors every `needs_you.field` value the
 * server can emit today (see `api/app/services/sow_confirmation.py::_needs_you`
 * plus the sibling `SowFieldName` union in `web/src/api/client.ts`).
 * When a new blocker key ships, add it to CANONICAL_BLOCKER_KEYS AND to
 * the BLOCKER_REGISTRY in one PR.
 */
import { describe, it, expect } from "vitest";
import {
  BLOCKER_REGISTRY,
  assertRegistered,
  lookupBlocker,
} from "../../pages/v2/sow-studio/confirmation/blockerRegistry";

const CANONICAL_BLOCKER_KEYS = [
  "scope_summary",
  "price",
  "currency",
  "billing_basis",
  "term_start",
  "term_end",
  "notice_date",
  "deliverables",
  "signatories",
  "engagement_type",
  "gm_model",
  "rate_card",
  "client_legal_name",
  "client_domain",
] as const;

describe("Rule 13 · blocker registry completeness", () => {
  it("has an editor for every canonical blocker key", () => {
    expect(() => assertRegistered(CANONICAL_BLOCKER_KEYS)).not.toThrow();
  });

  it("names the missing keys in the error message when one is dropped", () => {
    // Simulate an accidental deletion by looking up an unregistered key.
    const missing = "totally_not_a_field";
    expect(lookupBlocker(missing)).toBeNull();
    expect(() => assertRegistered([missing])).toThrow(/totally_not_a_field/);
    expect(() => assertRegistered([missing])).toThrow(/Rule 13/);
  });

  it("resolves subscripted keys back to their base entry", () => {
    // The server sometimes emits blockers like `signatories[0].email` or
    // `staffing[0].hourly_bill_rate` — the registry lookup folds those
    // to the base key so the row still resolves to a real editor.
    expect(lookupBlocker("signatories[0].email")?.label).toBe("Signatories");
    expect(lookupBlocker("gm_model.us_gm")?.label).toBe("Staffing & GM");
  });

  it("exports one entry per canonical key", () => {
    for (const key of CANONICAL_BLOCKER_KEYS) {
      expect(BLOCKER_REGISTRY[key], `missing registry entry for ${key}`).toBeDefined();
      expect(typeof BLOCKER_REGISTRY[key].Editor).toBe("function");
      expect(BLOCKER_REGISTRY[key].label.length).toBeGreaterThan(0);
    }
  });
});
