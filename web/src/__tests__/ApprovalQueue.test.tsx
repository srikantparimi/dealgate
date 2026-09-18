/**
 * ApprovalQueue + ApprovalPackageDetail — S4 E7 web tests.
 *
 * The API client is mocked. We assert the page renders the two pending
 * inboxes, calls decideApprovalPackage when a reviewer clicks Approve,
 * and that the detail page renders the floor chips from the ``floors``
 * block on the server response.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type {
  ApprovalPackage,
  ApprovalPackageListResponse,
} from "../api/client";
import { ApprovalPackageDetailPage } from "../pages/ApprovalPackageDetail";
import { ApprovalQueuePage } from "../pages/ApprovalQueue";

// AuthProvider is used inside the pages; stub the hook to a Delivery user.
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      email: "d@smartek21.com",
      name: "Delivery Reviewer",
      groups: ["Delivery"],
    },
  }),
}));

const PACKAGE_ID = "11111111-1111-1111-1111-111111111111";
const OPP_ID = "22222222-2222-2222-2222-222222222222";
const SOW_ID = "33333333-3333-3333-3333-333333333333";
const GM_ID = "44444444-4444-4444-4444-444444444444";
const SUBMITTER_ID = "55555555-5555-5555-5555-555555555555";

function samplePackage(overrides: Partial<ApprovalPackage> = {}): ApprovalPackage {
  return {
    id: PACKAGE_ID,
    opportunity_id: OPP_ID,
    sow_version_id: SOW_ID,
    gm_model_id: GM_ID,
    package_hash: "a".repeat(64),
    status: "pending_delivery_hr",
    submitted_by: SUBMITTER_ID,
    submitted_at: "2026-09-17T10:00:00",
    released_at: null,
    voided_at: null,
    voided_reason: null,
    policy_version_id: null,
    approvals: [],
    floors: {
      us_pass: true,
      india_pass: true,
      requires_ceo: false,
      failing: [],
    },
    ...overrides,
  };
}

function sampleListResponse(
  items: ApprovalPackage[],
): ApprovalPackageListResponse {
  return { items, page: 1, size: 25, total: items.length };
}

function renderQueue() {
  return render(
    <MemoryRouter initialEntries={["/approvals"]}>
      <Routes>
        <Route path="/approvals" element={<ApprovalQueuePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={[`/approvals/${PACKAGE_ID}`]}>
      <Routes>
        <Route path="/approvals/:id" element={<ApprovalPackageDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ApprovalQueue", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders packages awaiting the current user's role", async () => {
    const pkg = samplePackage();
    vi.spyOn(apiClient, "listApprovalPackages").mockImplementation(async (q) => {
      if (q?.status === "pending_delivery_hr") return sampleListResponse([pkg]);
      return sampleListResponse([]);
    });
    renderQueue();
    await waitFor(() => {
      expect(
        screen.getByRole("table", { name: /approval packages/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/pending_delivery_hr/i)).toBeInTheDocument();
    expect(screen.getByTestId(`approve-${PACKAGE_ID}`)).toBeInTheDocument();
  });

  it("calls decideApprovalPackage when Approve is clicked", async () => {
    const pkg = samplePackage();
    vi.spyOn(apiClient, "listApprovalPackages").mockImplementation(async (q) => {
      if (q?.status === "pending_delivery_hr") return sampleListResponse([pkg]);
      return sampleListResponse([]);
    });
    const decide = vi
      .spyOn(apiClient, "decideApprovalPackage")
      .mockResolvedValue(samplePackage({ status: "pending_finance_legal" }));
    renderQueue();
    await waitFor(() => {
      expect(screen.getByTestId(`approve-${PACKAGE_ID}`)).toBeInTheDocument();
    });
    const user = userEvent.setup();
    await user.click(screen.getByTestId(`approve-${PACKAGE_ID}`));
    await waitFor(() => {
      expect(decide).toHaveBeenCalledTimes(1);
    });
    expect(decide.mock.calls[0][0]).toBe(PACKAGE_ID);
    expect(decide.mock.calls[0][1]).toBe("delivery");
    expect(decide.mock.calls[0][2]).toEqual({ decision: "approve" });
  });

  it("shows empty state when nothing pending for this role", async () => {
    vi.spyOn(apiClient, "listApprovalPackages").mockResolvedValue(
      sampleListResponse([]),
    );
    renderQueue();
    await waitFor(() => {
      expect(screen.getByText(/Nothing to review/i)).toBeInTheDocument();
    });
  });
});

describe("ApprovalPackageDetail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders floor pass/fail chips from the server response", async () => {
    vi.spyOn(apiClient, "getApprovalPackage").mockResolvedValue(
      samplePackage({
        floors: {
          us_pass: false,
          india_pass: true,
          requires_ceo: true,
          failing: ["US"],
        },
      }),
    );
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText(/US fail/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/India pass/i)).toBeInTheDocument();
    expect(screen.getByText(/CEO exception/i)).toBeInTheDocument();
  });

  it("renders the package hash and pinned snapshot ids", async () => {
    vi.spyOn(apiClient, "getApprovalPackage").mockResolvedValue(samplePackage());
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    });
    expect(screen.getByText(SOW_ID)).toBeInTheDocument();
    expect(screen.getByText(GM_ID)).toBeInTheDocument();
  });
});
