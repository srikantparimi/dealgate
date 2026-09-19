import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { CapabilityCatalogPage } from "../pages/CapabilityCatalog";

const CAP_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

const sample: apiClient.CapabilityRow = {
  id: CAP_ID,
  name: "Salesforce implementation",
  description: "Custom Salesforce CRM flows for sales teams",
  tags: ["salesforce", "crm"],
  has_embedding: true,
  curated_by: null,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
};

function renderPage(
  props: { canWrite?: boolean; canDelete?: boolean } = {},
) {
  return render(
    <MemoryRouter initialEntries={["/admin/capabilities"]}>
      <CapabilityCatalogPage {...props} />
    </MemoryRouter>,
  );
}

describe("CapabilityCatalog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listCapabilities").mockResolvedValue({
      items: [sample],
      page: 1,
      size: 25,
      total: 1,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders capabilities from the API and flags the embedding state", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Salesforce implementation")).toBeInTheDocument();
    });
    expect(screen.getByText(/Custom Salesforce CRM flows/i)).toBeInTheDocument();
    expect(screen.getByText("salesforce")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
  });

  it("submits createCapability from the add modal", async () => {
    const created = vi.spyOn(apiClient, "createCapability").mockResolvedValue({
      ...sample,
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      name: "Data warehouse",
      description: "Lakehouse rollout",
      tags: ["data"],
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Salesforce implementation")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /add capability/i }));

    await user.type(await screen.findByLabelText("Capability name"), "Data warehouse");
    await user.type(screen.getByLabelText("Capability description"), "Lakehouse rollout");
    await user.type(screen.getByLabelText("Capability tags"), "data");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    await waitFor(() => {
      expect(created).toHaveBeenCalledTimes(1);
    });
    const body = created.mock.calls[0][0];
    expect(body).toEqual({
      name: "Data warehouse",
      description: "Lakehouse rollout",
      tags: ["data"],
    });
  });

  it("submits patchCapability from the edit modal", async () => {
    const patched = vi.spyOn(apiClient, "patchCapability").mockResolvedValue({
      ...sample,
      description: "Refreshed CRM rollout playbook",
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Salesforce implementation")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: /edit salesforce implementation/i }),
    );

    const desc = await screen.findByLabelText("Capability description");
    await user.clear(desc);
    await user.type(desc, "Refreshed CRM rollout playbook");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patched).toHaveBeenCalledTimes(1);
    });
    const [id, body] = patched.mock.calls[0];
    expect(id).toBe(CAP_ID);
    // Only the description changed — the tags/name diffs should stay
    // undefined so the API skips the redundant re-embed on those keys.
    expect(body.description).toBe("Refreshed CRM rollout playbook");
    expect(body.name).toBeUndefined();
    expect(body.tags).toBeUndefined();
  });

  it("hides write actions when canWrite is false", async () => {
    renderPage({ canWrite: false, canDelete: false });
    await waitFor(() => {
      expect(screen.getByText("Salesforce implementation")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /add capability/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /edit salesforce implementation/i }),
    ).not.toBeInTheDocument();
  });
});
