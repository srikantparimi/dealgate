/**
 * Discovery (`/discovery`) — Sprint 8 Wave 3 acceptance tests
 * (spec §10 + R02/R03/R04).
 *
 * The tests cover the non-negotiables:
 *
 * - "Indicative planning only" badge is present on first paint and
 *   remains after the user generates an estimate.
 * - Rendered sources carry a URL and a retrieval date (spec §10).
 * - `research_status === "unavailable"` renders the explicit banner
 *   "Public research unavailable — no verified source found."
 * - When sources[] is empty the UI shows the "No verified source"
 *   empty state — it NEVER fabricates a citation.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type { AdviserEstimate, AdviserListResponse } from "../../api/client";
import { DiscoveryPage } from "../../pages/v2/Discovery";

function makeEstimate(overrides: Partial<AdviserEstimate>): AdviserEstimate {
  return {
    kind: "estimate",
    id: "00000000-0000-0000-0000-000000000aaa",
    submitted_at: "2026-06-10T10:00:00Z",
    submitted_by: "u-1",
    label: "Acme discovery",
    scope: "Migrate legacy portal to a modern stack in two increments.",
    confidence: "medium",
    reasons: ["Client SLA reference on public site"],
    team: [
      {
        role: "Engineer",
        seniority: "Senior",
        location: "US",
        hours: "400",
        allocation_pct: "50",
        cost_low: "40000",
        cost_base: "48000",
        cost_high: "56000",
        is_sentinel: false,
      },
    ],
    cost_low: "40000",
    cost_base: "48000",
    cost_high: "56000",
    options: [
      {
        key: "us_only",
        label: "US only",
        cost_low: "40000",
        cost_base: "48000",
        cost_high: "56000",
        min_price: "75000",
        floor_applied: "0.35",
        eligible: true,
      },
    ],
    sources: [],
    model: "bedrock",
    prompt_version: "v1",
    inputs: { client: "Acme" },
    rate_card_version_id: null,
    has_sentinel_costs: false,
    reviewer_id: null,
    reviewed_at: null,
    ...overrides,
  };
}

function listResponse(items: AdviserEstimate[]): AdviserListResponse {
  return { items, page: 1, size: 25, total: items.length };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/discovery"]}>
      <DiscoveryPage />
    </MemoryRouter>,
  );
}

describe("DiscoveryPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listAdviserEstimates").mockResolvedValue(
      listResponse([]),
    );
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows 'Indicative planning only' on first paint and after generate", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(
      makeEstimate({
        sources: [
          {
            url: "https://example.com/case-study",
            title: "Client case study",
            retrieved_at: "2026-06-10",
            relevance: "sla reference",
          },
        ],
      }),
    );

    renderPage();

    expect(screen.getAllByText(/Indicative planning only/i).length).toBeGreaterThan(0);

    // Fill required field and generate.
    await user.type(screen.getByLabelText(/Client name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /Generate estimate/i }));

    // After the async completes the badge must still be visible.
    await waitFor(() =>
      expect(screen.getByText(/Scope interpretation/i)).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/Indicative planning only/i).length).toBeGreaterThan(0);
  });

  it("renders sources with URL and retrieval date", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(
      makeEstimate({
        sources: [
          {
            url: "https://example.com/whitepaper",
            title: "Acme whitepaper",
            retrieved_at: "2026-06-01",
            relevance: "corroborates stack",
          },
        ],
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/Client name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /Generate estimate/i }));

    const region = await screen.findByTestId("adviser-sources");
    const link = await screen.findByRole("link", { name: /Acme whitepaper/i });
    expect(link.getAttribute("href")).toBe("https://example.com/whitepaper");
    expect(region.textContent ?? "").toMatch(/Retrieved: 2026-06-01/);
  });

  it("renders the unavailable banner when research_status is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(
      makeEstimate({
        research_status: "unavailable",
        sources: [],
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/Client name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /Generate estimate/i }));

    const banner = await screen.findByTestId("research-unavailable-banner");
    expect(banner.textContent ?? "").toMatch(
      /Public research unavailable — no verified source found/i,
    );
  });

  it("never fabricates a citation when sources[] is empty", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(
      makeEstimate({
        research_status: "ok",
        sources: [],
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/Client name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /Generate estimate/i }));

    const region = await screen.findByTestId("adviser-sources");
    // The empty state renders inside the sources region — no anchor
    // link should be present (that would be a fabricated citation).
    expect(
      region.querySelectorAll("a").length,
    ).toBe(0);
    expect(region.textContent ?? "").toMatch(/No verified source found/i);
  });

  it("drops sources without a URL — no fabricated citations", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(
      makeEstimate({
        research_status: "ok",
        sources: [
          // Missing URL — must be dropped.
          { title: "Trust me", retrieved_at: "2026-06-01" },
          // Non-http(s) — must be dropped.
          {
            url: "javascript:alert(1)",
            title: "Bad",
            retrieved_at: "2026-06-01",
          },
        ],
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/Client name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /Generate estimate/i }));

    const region = await screen.findByTestId("adviser-sources");
    expect(region.querySelectorAll("a").length).toBe(0);
    expect(region.textContent ?? "").toMatch(/No verified source found/i);
  });
});
