/**
 * Settings → Client rate cards — S9 wave 1 acceptance test.
 *
 * Empty landing (no client selected) is the intentional first-render
 * state per docs/sow-first-principles.md: this page is "pick a client
 * to open the editor", not a giant client list.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ClientCardsSection } from "../../pages/v2/settings/ClientCardsSection";

describe("ClientCardsSection", () => {
  it("renders the pick-a-client empty state on first open", () => {
    render(
      <MemoryRouter>
        <ClientCardsSection />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: /Client rate cards/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Pick a client to view its rate card/i),
    ).toBeInTheDocument();
    // Explicit callout that cost bands + policy live elsewhere.
    expect(screen.getByText(/live in their own sections/i)).toBeInTheDocument();
  });

  it("names the loud fallback warning for clients with no card", () => {
    render(
      <MemoryRouter>
        <ClientCardsSection />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/loud fallback warning/i),
    ).toBeInTheDocument();
  });
});
