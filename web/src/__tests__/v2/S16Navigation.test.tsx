import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";
import { PrimaryNavigation } from "../../ui-v2/PrimaryNavigation";
import { RetiredPage } from "../../pages/v2/RetiredPage";

it("S16 exposes only the current navigation destinations", () => {
  render(
    <MemoryRouter>
      <PrimaryNavigation groups={["SystemAdmin"]} />
    </MemoryRouter>,
  );
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Command center",
    "My work",
    "Pipeline clients",
    "AI discovery",
    "NDA & MSA",
    "SOW approvals",
    "New SOW studio",
    "Projects",
    "Renewals",
    "Signed handoff",
    "Reporting",
    "Settings",
  ]);
  expect(screen.queryByText(/Legacy/)).not.toBeInTheDocument();
});

it.each([
  ["/tasks", "/work"],
  ["/deals", "/pipeline"],
  // S20 W3: `/deals/:id` no longer forwards into `/sows/:id` (L09/L11).
  // Until W2 ships a real deal detail page the retired page sends the
  // user to Pipeline; see `docs/reports/s20/requests.md`
  // #W3-2026-09-30-02.
  ["/deals/record", "/pipeline"],
  ["/gm/sandbox", "/sows"],
  ["/margin-lab", "/sows"],
])("%s has a friendly replacement link", (path, target) => {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/deals/:id" element={<RetiredPage />} />
        <Route path="*" element={<RetiredPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("404")).toBeInTheDocument();
  expect(screen.getByRole("link")).toHaveAttribute("href", target);
});
