/**
 * v2.1 StatusBadge — 5 variants + dot + word rendering.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../../ui-v2/StatusBadge";

describe("StatusBadge (v2.1)", () => {
  it.each(["neutral", "success", "warning", "danger", "progress"] as const)(
    "renders the %s variant with the label",
    (tone) => {
      render(<StatusBadge tone={tone} label={`Label ${tone}`} />);
      expect(screen.getByText(`Label ${tone}`)).toBeInTheDocument();
    },
  );

  it("keeps legacy tone names (ok / warn / primarySubtle) rendering", () => {
    render(
      <>
        <StatusBadge tone="ok" label="Legacy ok" />
        <StatusBadge tone="warn" label="Legacy warn" />
        <StatusBadge tone="primarySubtle" label="Legacy primarySubtle" />
      </>,
    );
    expect(screen.getByText("Legacy ok")).toBeInTheDocument();
    expect(screen.getByText("Legacy warn")).toBeInTheDocument();
    expect(screen.getByText("Legacy primarySubtle")).toBeInTheDocument();
  });

  it("renders a coloured dot before the word by default", () => {
    const { container } = render(<StatusBadge tone="success" label="OK" />);
    // Dot is a 6px×6px sibling of the text label.
    const dot = container.querySelector(
      "[aria-hidden][class*='rounded-avatar']",
    );
    expect(dot).toBeTruthy();
  });
});
