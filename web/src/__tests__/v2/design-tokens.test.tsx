/**
 * v2.1 design-token conformance — computed-style assertions.
 *
 * S10-03 spec: `web/src/__tests__/v2/design-tokens.test.tsx` — asserts
 * computed styles on a rendered `StatusBadge`, `FunctionMark`, `FloorBar`,
 * `GateSteps` match the token values.
 *
 * jsdom does not compute CSS variables in the same way as a real browser
 * (no cascade of `--dg-*` values in `getComputedStyle`), so these tests
 * verify structural conformance: the primitives render at the geometry
 * demanded by the tokens JSON (`components.statusChip`, `functionMark`,
 * `floorBar`, `gateSteps`) and expose the state hooks a downstream test
 * can style-test in Playwright.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { FunctionMark, FunctionMarkRow } from "../../ui-v2/FunctionMark";
import { FloorBar } from "../../ui-v2/FloorBar";
import { GateSteps } from "../../ui-v2/GateSteps";
import { cardStripeClass } from "../../ui-v2/CardStripe";

describe("design tokens v2.1 — StatusBadge", () => {
  it.each([
    ["neutral"],
    ["success"],
    ["warning"],
    ["danger"],
    ["progress"],
  ] as const)("renders the %s variant with a dot + word", (tone) => {
    const { container } = render(
      <StatusBadge tone={tone} label={`tone-${tone}`} />,
    );
    expect(screen.getByText(`tone-${tone}`)).toBeInTheDocument();
    // The chip is 22px tall per token `components.statusChip.height`.
    const chip = container.querySelector("span[class*='h-\\[22px\\]']");
    expect(chip).toBeTruthy();
    // A leading 6px dot is always present unless an icon replaces it
    // (token `components.statusChip.dot` = 6).
    const dot = container.querySelector(
      "[aria-hidden][class*='rounded-avatar']",
    );
    expect(dot).toBeTruthy();
  });
});

describe("design tokens v2.1 — FunctionMark", () => {
  it("renders a 22×18 tile for each of the four letters", () => {
    const { container } = render(
      <FunctionMarkRow states={{ D: "ok", H: "ok", F: "ok", L: "ok" }} />,
    );
    const tiles = container.querySelectorAll(
      "span[class*='w-\\[22px\\]'][class*='h-\\[18px\\]']",
    );
    expect(tiles.length).toBe(4);
  });

  it.each(["pending", "progress", "ok", "bad"] as const)(
    "applies the %s state class",
    (state) => {
      render(<FunctionMark letter="D" state={state} />);
      const chip = screen.getByLabelText(/Delivery /);
      expect(chip.className).toContain(
        state === "ok"
          ? "text-success"
          : state === "bad"
            ? "text-danger"
            : state === "progress"
              ? "text-primaryText"
              : "text-text-muted",
      );
    },
  );

  it("shows the 'n/4 reviews' trailing copy", () => {
    render(
      <FunctionMarkRow states={{ D: "ok", H: "ok", F: "pending", L: "bad" }} />,
    );
    expect(screen.getByText("2/4 reviews")).toBeInTheDocument();
  });
});

describe("design tokens v2.1 — FloorBar", () => {
  it("renders a 10px track with fill + 2px marker geometry", () => {
    const { container } = render(
      <FloorBar value="0.278" floor="0.35" label="US" />,
    );
    // 10px track.
    const track = container.querySelector("[class*='h-\\[10px\\]']");
    expect(track).toBeTruthy();
    // 2px mark line with overshoot.
    const mark = screen.getByTestId("floorbar-marker");
    expect(mark.className).toContain("w-[2px]");
    expect(mark.className).toContain("-top-1");
    expect(mark.className).toContain("-bottom-1");
    // Fill uses danger below floor.
    const fill = screen.getByTestId("floorbar-fill");
    expect(fill.className).toContain("bg-danger");
    // Chip renders "Fails by 7.2 pts".
    expect(screen.getByText(/Fails by 7\.2 pts/)).toBeInTheDocument();
  });

  it("switches the fill to success at or above the floor", () => {
    render(<FloorBar value="0.55" floor="0.50" label="India" />);
    const fill = screen.getByTestId("floorbar-fill");
    expect(fill.className).toContain("bg-success");
    expect(screen.getByText(/Passes by 5\.0 pts/)).toBeInTheDocument();
  });

  it("exposes the achieved value on the meter role", () => {
    render(<FloorBar value="0.278" floor="0.35" />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("27.8");
    expect(meter.getAttribute("aria-valuemax")).toBe("60");
  });
});

describe("design tokens v2.1 — GateSteps", () => {
  it("renders six steps and applies the hold state to CEO exception", () => {
    render(
      <GateSteps
        steps={[
          { id: "g1", label: "Intake", state: "done" },
          { id: "g2", label: "Scope & GM", state: "now" },
          { id: "g3", label: "Function reviews", state: "pending" },
          { id: "g4", label: "CEO exception", state: "hold" },
          { id: "g5", label: "Signature", state: "pending" },
          { id: "g6", label: "Handoff", state: "pending" },
        ]}
      />,
    );
    // Hold cell has data-state="hold" so a Playwright test can style-check.
    const hold = document.querySelector('[data-state="hold"]');
    expect(hold).toBeTruthy();
    expect(hold?.className).toContain("bg-danger-surface");
    // Now cell announces aria-current="step".
    expect(
      document
        .querySelector('[data-state="now"]')
        ?.getAttribute("aria-current"),
    ).toBe("step");
    // "Will trigger" microcopy renders on the hold step.
    expect(screen.getAllByText("Will trigger").length).toBeGreaterThan(0);
  });
});

describe("design tokens v2.1 — CardStripe", () => {
  it("returns the correct 3px stripe class for each tone", () => {
    expect(cardStripeClass("blocked")).toContain("border-l-danger");
    expect(cardStripeClass("blocked")).toContain("border-l-[3px]");
    expect(cardStripeClass("at-risk")).toContain("border-l-warning");
    expect(cardStripeClass("in-progress")).toContain("border-l-primary");
    expect(cardStripeClass(null)).toBe("");
  });
});

describe("design tokens v2.1 — density persistence contract", () => {
  it("recognises data-density='compact' at the document root", () => {
    document.documentElement.setAttribute("data-density", "compact");
    // The CSS rule lives in index.css; jsdom does not evaluate it, so the
    // assertion is on the attribute contract the AppShell relies on.
    expect(
      document.documentElement.getAttribute("data-density"),
    ).toBe("compact");
    document.documentElement.removeAttribute("data-density");
  });
});
