// S23-PL2 F19 · the HubSpot portal id comes from GET /config (B14). The deal
// and client pages build "Open in HubSpot" from it and hide the link when the
// deployment has none; no source file hard-codes a portal any more.
import { render, screen, waitFor } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import { ClientDetailPageV2 } from "../../pages/v2/ClientDetail";
import { DealDetailPage } from "../../pages/v2/DealDetail";

vi.mock("../../ui-v2/WatchStar", () => ({ WatchStar: () => null }));
vi.mock("../../ui-v2/ClientAgreementPresence", () => ({ ClientAgreementPresence: () => null }));

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, "../..");

function sourcesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === "__tests__" ? [] : sourcesUnder(path);
    return /\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry) ? [path] : [];
  });
}

/** Answer GET /config with this portal; any other unmocked request is a test bug. */
function configWithPortal(portal: string | null) {
  vi.spyOn(api, "request").mockImplementation(async (path: string) => {
    if (path === "/config") return { hubspot_portal_id: portal } as never;
    throw new Error(`unexpected request ${path}`);
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  appConfig.resetAppConfigCache();
});

describe("no hard-coded HubSpot portal", () => {
  it("leaves no portal id in any web source file", () => {
    const offenders = sourcesUnder(SRC)
      .filter((path) => /app\.hubspot\.com\/contacts\/\d+|48656168/.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path));
    expect(offenders).toEqual([]);
  });
});

describe("deal page", () => {
  beforeEach(() => {
    vi.spyOn(api, "getPipelineOpportunity").mockResolvedValue({
      opportunity_id: "deal", name: "Cloud modernization", hubspot_deal_id: "9001",
      attention_flags: [], sow_count: 0,
    } as never);
    vi.spyOn(api, "getDealTimeline").mockResolvedValue({ items: [] });
    vi.spyOn(api, "listNextActions").mockResolvedValue({ items: [], can_create: false, assignees: [] } as never);
    vi.spyOn(api, "listDealComments").mockResolvedValue({ items: [], latest: null, can_create: false } as never);
  });

  function openDeal() {
    render(
      <MemoryRouter initialEntries={["/deals/deal"]}>
        <Routes><Route path="/deals/:id" element={<DealDetailPage />} /></Routes>
      </MemoryRouter>,
    );
  }

  it("links to the deal in the configured portal", async () => {
    configWithPortal("4242");
    openDeal();
    const link = await screen.findByRole("link", { name: /Open in HubSpot/ });
    expect(link).toHaveAttribute("href", "https://app.hubspot.com/contacts/4242/record/0-3/9001");
  });

  it("hides the link when the deployment has no portal", async () => {
    configWithPortal(null);
    openDeal();
    await screen.findAllByText("Cloud modernization");
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("/config"));
    expect(screen.queryByRole("link", { name: /Open in HubSpot/ })).toBeNull();
  });
});

describe("client page", () => {
  beforeEach(() => {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "me", email: "rep@example.test", name: "Rep", groups: ["Sales"] } as never);
    vi.spyOn(api, "getClient").mockResolvedValue({
      id: "client", name: "Keystone Energy", hubspot_company_id: "777", timezone: null,
      legal_entities: [], opportunities: [], recent_activity: [],
    } as never);
    vi.spyOn(api, "listPipelineOpportunities").mockResolvedValue({ items: [], total: 0 } as never);
    vi.spyOn(api, "getClientTimeline").mockResolvedValue({ items: [] } as never);
  });

  function openClient() {
    render(
      <MemoryRouter initialEntries={["/clients/client"]}>
        <Routes><Route path="/clients/:id" element={<ClientDetailPageV2 />} /></Routes>
      </MemoryRouter>,
    );
  }

  it("links to the company in the configured portal", async () => {
    configWithPortal("4242");
    openClient();
    const link = await screen.findByRole("link", { name: /Open in HubSpot/ });
    expect(link).toHaveAttribute("href", "https://app.hubspot.com/contacts/4242/record/0-2/777");
  });

  it("hides the link when the deployment has no portal", async () => {
    configWithPortal(null);
    openClient();
    await screen.findByTestId("client-heading");
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("/config"));
    expect(screen.queryByRole("link", { name: /Open in HubSpot/ })).toBeNull();
  });
});
