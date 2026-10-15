// S23-PL2 F18 · Settings → Users: each user's HubSpot owner link, whether it
// was matched automatically by email, and the admin override (including former
// HubSpot users) and unlink. Ids never show; only names do.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import type { AdminUserRow, HubspotOwnerOption, UserListResponse } from "../../api/client";
import { PeopleSection } from "../../pages/v2/settings/PeopleSection";

const RITA = "11111111-1111-1111-1111-111111111111";
const GUS_USER = "22222222-2222-2222-2222-222222222222";
const NEW_USER = "33333333-3333-3333-3333-333333333333";
const OTTO = "44444444-4444-4444-4444-444444444444";

function user(id: string, name: string, link: Partial<AdminUserRow>): AdminUserRow {
  return {
    id, name, email: `${name.split(" ")[0].toLowerCase()}@example.test`, groups: ["Sales"],
    last_login: "2026-10-01T10:00:00Z", created_at: "2026-01-01T00:00:00Z",
    hubspot_owner_id: null, hubspot_owner_name: null, hubspot_owner_state: "none", hubspot_owner_link: null,
    ...link,
  };
}

const USERS: AdminUserRow[] = [
  user(RITA, "Rita Rep", { hubspot_owner_id: "o-rita", hubspot_owner_name: "Rita Rep",
    hubspot_owner_state: "active", hubspot_owner_link: "email" }),
  user(GUS_USER, "Gus Gone", { hubspot_owner_id: "o-gus", hubspot_owner_name: "Gus Gone",
    hubspot_owner_state: "archived", hubspot_owner_link: "admin" }),
  user(NEW_USER, "Nora New", {}),
  user(OTTO, "Otto Other", { hubspot_owner_id: "o-otto", hubspot_owner_name: "Otto Other",
    hubspot_owner_state: "active", hubspot_owner_link: "admin" }),
];

const OWNERS: HubspotOwnerOption[] = [
  { id: "o-nora", name: "Nora New", email: "nora@example.test", archived: false, linked_user_id: null, linked_user_name: null },
  { id: "o-otto", name: "Otto Other", email: "otto@example.test", archived: false, linked_user_id: OTTO, linked_user_name: "Otto Other" },
  { id: "o-rita", name: "Rita Rep", email: "rita@example.test", archived: false, linked_user_id: RITA, linked_user_name: "Rita Rep" },
  { id: "o-gus", name: "Gus Gone", email: "gus@example.test", archived: true, linked_user_id: GUS_USER, linked_user_name: "Gus Gone" },
  { id: "o-fay", name: null, email: "fay@example.test", archived: true, linked_user_id: null, linked_user_name: null },
];

function listResponse(items: AdminUserRow[]): UserListResponse {
  return { items, page: 1, size: 50, total: items.length, allowed_groups: [] } as UserListResponse;
}

function renderUsers() {
  render(
    <MemoryRouter initialEntries={["/settings/people?tab=users"]}>
      <PeopleSection />
    </MemoryRouter>,
  );
}

function userRow(name: string): HTMLElement {
  return screen.getByRole("row", { name: new RegExp(`^${name}`) });
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listUsers").mockResolvedValue(listResponse(USERS));
  vi.spyOn(api, "listHubspotOwners").mockResolvedValue(OWNERS);
});

describe("HubSpot owner link on Settings → Users", () => {
  it("shows each user's link and how it was decided, by name only", async () => {
    renderUsers();
    await screen.findAllByText("Rita Rep");
    expect(within(userRow("Rita Rep")).getByText("Auto-matched by email")).toBeInTheDocument();
    expect(within(userRow("Gus Gone")).getByText("Gus Gone · Former HubSpot user")).toBeInTheDocument();
    expect(within(userRow("Gus Gone")).getByText("Set by an admin")).toBeInTheDocument();
    expect(within(userRow("Nora New")).getByText("Not linked")).toBeInTheDocument();
    for (const id of ["o-rita", "o-gus", "o-otto"]) {
      expect(document.body.textContent).not.toContain(id);
    }
  });

  it("lets an admin pick an owner, former ones labelled, taken ones unavailable", async () => {
    const save = vi.spyOn(api, "setUserHubspotOwner").mockResolvedValue(undefined);
    renderUsers();
    await screen.findByText("Nora New");
    fireEvent.click(within(userRow("Nora New")).getByRole("button", { name: "Change HubSpot owner for Nora New" }));
    const dialog = await screen.findByRole("dialog", { name: "HubSpot owner for Nora New" });
    const select = await within(dialog).findByLabelText("HubSpot owner");
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual([
      "No HubSpot owner",
      "Nora New",
      "Otto Other (linked to Otto Other)",
      "Rita Rep (linked to Rita Rep)",
      "Gus Gone · Former HubSpot user (linked to Gus Gone)",
      "fay@example.test · Former HubSpot user",
    ]);
    expect(within(select).getByRole("option", { name: "Otto Other (linked to Otto Other)" })).toBeDisabled();
    expect(document.body.textContent).not.toContain("o-nora");

    fireEvent.change(select, { target: { value: "o-nora" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(NEW_USER, "o-nora"));
    await waitFor(() => expect(api.listUsers).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("unlinks a user", async () => {
    const save = vi.spyOn(api, "setUserHubspotOwner").mockResolvedValue(undefined);
    renderUsers();
    await screen.findAllByText("Rita Rep");
    fireEvent.click(within(userRow("Rita Rep")).getByRole("button", { name: "Change HubSpot owner for Rita Rep" }));
    const dialog = await screen.findByRole("dialog", { name: "HubSpot owner for Rita Rep" });
    const select = await within(dialog).findByLabelText("HubSpot owner");
    expect(select).toHaveValue("o-rita");
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(RITA, null));
  });

  it("keeps the dialog open with the server's message when the owner is taken", async () => {
    vi.spyOn(api, "setUserHubspotOwner").mockRejectedValue(
      new api.ApiError(409, { detail: "Otto Other is already linked to this HubSpot owner. Unlink them first." },
        "Otto Other is already linked to this HubSpot owner. Unlink them first."),
    );
    renderUsers();
    await screen.findByText("Nora New");
    fireEvent.click(within(userRow("Nora New")).getByRole("button", { name: "Change HubSpot owner for Nora New" }));
    const dialog = await screen.findByRole("dialog", { name: "HubSpot owner for Nora New" });
    fireEvent.change(await within(dialog).findByLabelText("HubSpot owner"), { target: { value: "o-nora" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Otto Other is already linked");
  });
});
