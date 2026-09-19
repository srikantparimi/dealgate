/**
 * GateSteps — v2.1 spec `components.gateSteps`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GateSteps } from "../../ui-v2/GateSteps";

describe("GateSteps", () => {
  it("renders six steps and the 'Will trigger' microcopy for hold", () => {
    render(
      <GateSteps
        steps={[
          { id: "g1", label: "Draft", state: "done" },
          { id: "g2", label: "Scope & GM", state: "done" },
          { id: "g3", label: "Functional", state: "now" },
          { id: "g4", label: "CEO", state: "hold" },
          { id: "g5", label: "Client sig", state: "pending" },
          { id: "g6", label: "Handoff", state: "pending" },
        ]}
      />,
    );
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Handoff")).toBeInTheDocument();
    // Hold state announces "Will trigger" — the whole reason it exists.
    expect(screen.getAllByText("Will trigger").length).toBeGreaterThan(0);
    // Now state carries aria-current="step" for assistive tech.
    expect(
      document.querySelector('[data-state="now"]')?.getAttribute("aria-current"),
    ).toBe("step");
  });

  it("fires onSelect when a clickable step is activated", () => {
    const spy = vi.fn();
    render(
      <GateSteps
        steps={[
          {
            id: "g1",
            label: "Draft",
            state: "done",
            onSelect: spy,
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId("gate-step-g1"));
    expect(spy).toHaveBeenCalled();
  });
});
