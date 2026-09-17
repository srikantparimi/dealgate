import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { UsersAdminPage } from "../pages/UsersAdmin";

const ADMIN_ID = "11111111-1111-1111-1111-111111111111";
const SALES_ID = "22222222-2222-2222-2222-222222222222";

const list: apiClient.UserListResponse = {
  items: [
    {
      id: ADMIN_ID,
      email: "admin@smartek21.com",
      name: "Admin One",
      groups: ["SystemAdmin"],
      last_login: "2026-09-15T10:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: SALES_ID,
      email: "sales@smartek21.com",
      name: "Sales One",
      groups: ["Sales"],
      last_login: null,
      created_at: "2026-02-01T00:00:00Z",
    },
  ],
  page: 1,
  size: 25,
  total: 2,
  allowed_groups: [
    "Marketing",
    "Sales",
    "SalesLeader",
    "Presales",
    "Delivery",
    "HR",
    "Finance",
    "Legal",
    "CEO",
    "SystemAdmin",
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <UsersAdminPage />
    </MemoryRouter>,
  );
}

describe("UsersAdmin", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listUsers").mockResolvedValue(list);
    vi.spyOn(apiClient, "getRoleHistory").mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders users from listUsers", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("admin@smartek21.com")).toBeInTheDocument();
    });
    expect(screen.getByText("sales@smartek21.com")).toBeInTheDocument();
    // "Sales" appears in the group filter dropdown AND as a chip on the row;
    // asserting via the accessible table row keeps the assertion unambiguous.
    const salesRow = screen.getByText("sales@smartek21.com").closest("tr");
    expect(salesRow).not.toBeNull();
    expect(salesRow!.textContent).toContain("Sales");
    const adminRow = screen.getByText("admin@smartek21.com").closest("tr");
    expect(adminRow).not.toBeNull();
    expect(adminRow!.textContent).toContain("SystemAdmin");
  });

  it("opens the invite modal, calls inviteUser, and shows an error on 409", async () => {
    const invite = vi
      .spyOn(apiClient, "inviteUser")
      .mockRejectedValueOnce(
        new apiClient.ApiError(409, { detail: "user with email 'x@y.com' already exists" }, "user with email 'x@y.com' already exists"),
      );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("admin@smartek21.com")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /invite user/i }));

    // Modal fields become visible.
    const emailInput = await screen.findByLabelText("Email");
    const nameInput = screen.getByLabelText("Name");
    await user.type(emailInput, "x@y.com");
    await user.type(nameInput, "X Y");
    await user.click(screen.getByLabelText("Group Sales"));

    await user.click(screen.getByRole("button", { name: /^invite$/i }));

    await waitFor(() => {
      expect(invite).toHaveBeenCalledTimes(1);
    });
    expect(invite.mock.calls[0][0]).toEqual({
      email: "x@y.com",
      name: "X Y",
      groups: ["Sales"],
    });

    // 409 error is surfaced inline; modal stays open.
    await waitFor(() => {
      expect(
        screen.getByText("user with email 'x@y.com' already exists"),
      ).toBeInTheDocument();
    });
  });

  it("opens the edit-groups drawer, calls patchUserGroups, shows last-admin error", async () => {
    const patch = vi
      .spyOn(apiClient, "patchUserGroups")
      .mockRejectedValueOnce(
        new apiClient.ApiError(
          409,
          { detail: "cannot remove the last SystemAdmin" },
          "cannot remove the last SystemAdmin",
        ),
      );

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("admin@smartek21.com")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    // Click the admin row → drawer opens.
    await user.click(screen.getByText("admin@smartek21.com"));

    // Drawer shows current groups + remove checkbox for SystemAdmin.
    const removeCheckbox = await screen.findByLabelText("Remove SystemAdmin");
    await user.click(removeCheckbox);

    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch.mock.calls[0][0]).toBe(ADMIN_ID);
    expect(patch.mock.calls[0][1]).toEqual({
      add: [],
      remove: ["SystemAdmin"],
    });

    // 409 last-admin error is surfaced inline in the drawer.
    await waitFor(() => {
      expect(
        screen.getByText("cannot remove the last SystemAdmin"),
      ).toBeInTheDocument();
    });
  });
});
