/**
 * FloorBar — v2.1 spec `components.floorBar`.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FloorBar } from "../../ui-v2/FloorBar";

describe("FloorBar", () => {
  it("shows a 'Fails by' chip below the floor", () => {
    render(<FloorBar value="0.278" floor="0.35" label="US" />);
    expect(screen.getByText(/Fails by 7\.2 pts/)).toBeInTheDocument();
  });

  it("shows a 'Passes by' chip at or above the floor", () => {
    render(<FloorBar value="0.55" floor="0.50" label="India" />);
    expect(screen.getByText(/Passes by 5\.0 pts/)).toBeInTheDocument();
  });

  it("accepts both fraction (0.35) and percentage (35) forms", () => {
    const { rerender } = render(<FloorBar value="0.35" floor="0.35" />);
    expect(screen.getByText(/Passes by 0\.0 pts/)).toBeInTheDocument();
    rerender(<FloorBar value="35" floor="35" />);
    expect(screen.getByText(/Passes by 0\.0 pts/)).toBeInTheDocument();
  });

  it("exposes a meter role with the achieved percentage", () => {
    render(<FloorBar value="0.278" floor="0.35" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "27.8");
    expect(meter).toHaveAttribute("aria-valuemax", "60");
  });
});
