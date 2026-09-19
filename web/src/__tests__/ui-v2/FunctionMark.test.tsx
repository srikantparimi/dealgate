/**
 * FunctionMark — v2.1 spec `components.functionMark`.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  FunctionMark,
  FunctionMarkRow,
} from "../../ui-v2/FunctionMark";

describe("FunctionMark", () => {
  it("renders the letter with an accessible state label", () => {
    render(<FunctionMark letter="D" state="ok" />);
    expect(screen.getByLabelText("Delivery approved")).toBeInTheDocument();
  });

  it("row shows all four letters and the count copy", () => {
    render(
      <FunctionMarkRow
        states={{ D: "ok", H: "ok", F: "progress", L: "pending" }}
      />,
    );
    expect(screen.getByLabelText("Delivery approved")).toBeInTheDocument();
    expect(screen.getByLabelText("HR approved")).toBeInTheDocument();
    expect(screen.getByLabelText("Finance in review")).toBeInTheDocument();
    expect(screen.getByLabelText("Legal pending")).toBeInTheDocument();
    expect(screen.getByText("2/4 reviews")).toBeInTheDocument();
  });
});
