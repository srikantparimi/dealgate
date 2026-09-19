/**
 * BarChart — v2.1 chart primitive.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart } from "../../ui-v2/BarChart";

describe("BarChart", () => {
  const data = [
    { label: "US", value: 27.8 },
    { label: "India", value: 45.5 },
    { label: "Combined", value: 34.5 },
  ];

  it("renders bars with an accessible chart label", () => {
    render(<BarChart data={data} floor={35} ariaLabel="GM by geography" />);
    expect(screen.getByLabelText("GM by geography")).toBeInTheDocument();
  });

  it("swaps to a table view when showTable is true", () => {
    render(
      <BarChart
        data={data}
        floor={35}
        showTable
        ariaLabel="GM by geography"
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("India")).toBeInTheDocument();
  });

  it("renders a floor line label in svg mode", () => {
    const { container } = render(<BarChart data={data} floor={35} />);
    const floorLabel = Array.from(container.querySelectorAll("text")).find(
      (t) => (t.textContent ?? "").startsWith("floor "),
    );
    expect(floorLabel).toBeTruthy();
  });
});
