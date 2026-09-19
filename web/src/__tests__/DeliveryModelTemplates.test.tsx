/**
 * DeliveryModelTemplates page — S7 wave 2.
 *
 * The page lists reusable templates and offers a soft-delete. Backend
 * is the source of truth for shape; the page only renders + wires
 * confirm() before dispatching the DELETE.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { DeliveryModelTemplatesPage } from "../pages/DeliveryModelTemplates";

const TPL_ID = "aaaaaaaa-1111-1111-1111-111111111111";

function fakeItem(overrides: Partial<apiClient.DeliveryTemplateSummary> = {}) {
  return {
    id: TPL_ID,
    name: "Discovery + Build",
    engagement_type: "fixed_price" as const,
    created_by: null,
    created_at: "2026-09-17T00:00:00Z",
    updated_at: "2026-09-17T00:00:00Z",
    active: true,
    phase_count: 2,
    resource_line_count: 3,
    cost_line_count: 1,
    ...overrides,
  };
}

describe("DeliveryModelTemplatesPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists templates returned by the API", async () => {
    vi.spyOn(apiClient, "listDeliveryTemplates").mockResolvedValue({
      items: [fakeItem()],
    });
    render(<DeliveryModelTemplatesPage />);
    await waitFor(() =>
      expect(screen.getByTestId(`template-row-${TPL_ID}`)).toBeInTheDocument(),
    );
    expect(screen.getByText("Discovery + Build")).toBeInTheDocument();
    expect(screen.getByText("fixed_price")).toBeInTheDocument();
  });

  it("dispatches DELETE when the Deactivate button is confirmed", async () => {
    vi.spyOn(apiClient, "listDeliveryTemplates")
      .mockResolvedValueOnce({ items: [fakeItem()] })
      .mockResolvedValueOnce({ items: [] });
    const del = vi
      .spyOn(apiClient, "deleteDeliveryTemplate")
      .mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<DeliveryModelTemplatesPage />);
    await waitFor(() =>
      expect(screen.getByTestId(`template-delete-${TPL_ID}`)).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId(`template-delete-${TPL_ID}`));
    await waitFor(() => expect(del).toHaveBeenCalledWith(TPL_ID));
  });

  it("renders empty state when there are no templates", async () => {
    vi.spyOn(apiClient, "listDeliveryTemplates").mockResolvedValue({
      items: [],
    });
    render(<DeliveryModelTemplatesPage />);
    await waitFor(() =>
      expect(screen.getByText(/No templates yet/i)).toBeInTheDocument(),
    );
  });
});
