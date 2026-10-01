/**
 * S21 item 2 regression · route-level assertion.
 *
 * Kanna's finding: clicking the Staffing & GM tab inside a SOW
 * workspace used to leave the workspace for a full page because
 * App.tsx had a more-specific `/sows/:id/staffing` route pointing
 * at `<StaffingGatePage />` that shadowed the generic
 * `/sows/:id/:tab` → `<SowWorkspacePage />` route.
 *
 * This test reads App.tsx source and asserts the shadowing route
 * is gone. Not elegant, but reliable: a route table is static
 * data, and the regression was a route-table mistake. The
 * Playwright spec in `tests/e2e/specs/s21/t45-s21-click-through.spec.ts`
 * is the user-visible proof on staging.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const appTsx = readFileSync(resolve(here, "../../App.tsx"), "utf8");

describe("S21 item 2 · App route table does not shadow /sows/:id/:tab", () => {
  it("has no specific /sows/:id/staffing route that could render a standalone page", () => {
    // Permitted: the generic `/sows/:id/:tab` route (which the
    // workspace reads to render the Staffing tab).
    expect(appTsx).toContain('path="/sows/:id/:tab"');
    // Forbidden: a dedicated /staffing route that beats the tab
    // route due to react-router's more-specific-wins ordering.
    expect(appTsx).not.toMatch(/path=["']\/sows\/:id\/staffing["']/);
  });

  it("does not import StaffingGatePage into the app router", () => {
    expect(appTsx).not.toMatch(/import\s*\{[^}]*StaffingGatePage[^}]*\}/);
  });
});
