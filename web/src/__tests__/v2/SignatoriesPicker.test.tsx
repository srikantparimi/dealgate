/**
 * SignatoriesPicker acceptance tests.
 *
 * Anchored to docs/directives/one-staffing-model.md rule 6 and
 * docs/directives/gm-correctness.md root cause 4:
 *
 * - The picker reads the current list off ``extracted_fields.signatories``.
 * - Picking an internal signatory appends to the list and PATCHes the
 *   ``signatories`` field via ``confirmSowField``.
 * - The "+ Add contact" form persists via ``createClientContact`` and then
 *   appends the created row to the list.
 * - Removing a picked signatory PATCHes the shortened list.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  ClientContactRow,
  InternalSignatoryRow,
  PickedSignatory,
} from "../../api/client";
import { SignatoriesPicker } from "../../pages/v2/sow-studio/confirmation/SignatoriesPicker";

const SOW_VERSION_ID = "00000000-0000-0000-0000-0000000000ff";
const CLIENT_ID = "c0000000-0000-0000-0000-000000000001";

const INTERNAL: InternalSignatoryRow[] = [
  {
    id: "u0000000-0000-0000-0000-000000000001",
    name: "Ada Lovelace",
    email: "ada@smartek21.example",
    groups: ["CEO"],
  },
  {
    id: "u0000000-0000-0000-0000-000000000002",
    name: "Grace Hopper",
    email: "grace@smartek21.example",
    groups: ["Finance"],
  },
];

const CONTACTS: ClientContactRow[] = [
  {
    id: "cc000000-0000-0000-0000-000000000010",
    client_id: CLIENT_ID,
    name: "Jane Doe",
    email: "jane@northwind.example",
    title: "General Counsel",
  },
];

function mockLoaders() {
  vi.spyOn(apiClient, "listInternalSignatories").mockResolvedValue(INTERNAL);
  vi.spyOn(apiClient, "listClientContacts").mockResolvedValue(CONTACTS);
}

describe("SignatoriesPicker", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the current list from the payload value", async () => {
    mockLoaders();
    // A partially-populated list — one internal, one client contact.
    const value: PickedSignatory[] = [
      {
        source: "internal",
        user_id: INTERNAL[0].id,
        name: INTERNAL[0].name,
        email: INTERNAL[0].email,
      },
      {
        source: "client",
        contact_id: CONTACTS[0].id,
        name: CONTACTS[0].name,
        email: CONTACTS[0].email,
        title: CONTACTS[0].title,
      },
    ];

    render(
      <SignatoriesPicker
        sowVersionId={SOW_VERSION_ID}
        clientId={CLIENT_ID}
        value={value}
      />,
    );

    // Both rows render as focusable remove-buttons.
    expect(screen.getByTestId("signatory-row-0")).toHaveTextContent(
      "Ada Lovelace",
    );
    expect(screen.getByTestId("signatory-row-1")).toHaveTextContent("Jane Doe");
    expect(screen.getByTestId("signatory-remove-0")).toBeInTheDocument();
    expect(screen.getByTestId("signatory-remove-1")).toBeInTheDocument();
    // Let the internal + contacts loaders resolve inside the test's act
    // scope so no state update happens after the test returns.
    await waitFor(() => {
      expect(
        screen.getByTestId("signatories-internal-list"),
      ).not.toBeEmptyDOMElement();
    });
  });

  it("appends a picked internal signatory and PATCHes the field", async () => {
    mockLoaders();
    const patch = vi
      .spyOn(apiClient, "confirmSowField")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .mockResolvedValue({} as any);
    const onChange = vi.fn();

    render(
      <SignatoriesPicker
        sowVersionId={SOW_VERSION_ID}
        clientId={CLIENT_ID}
        value={[]}
        onChange={onChange}
      />,
    );

    // Wait for the internal list to load.
    await waitFor(() => {
      expect(
        screen.getByTestId(`signatories-internal-pick-${INTERNAL[0].id}`),
      ).toBeInTheDocument();
    });

    await userEvent.click(
      screen.getByTestId(`signatories-internal-pick-${INTERNAL[0].id}`),
    );

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    // Called with the appended list.
    const args = patch.mock.calls[0];
    expect(args[0]).toBe(SOW_VERSION_ID);
    expect(args[1]).toBe("signatories");
    expect(args[2]).toEqual([
      {
        source: "internal",
        user_id: INTERNAL[0].id,
        name: INTERNAL[0].name,
        email: INTERNAL[0].email,
      },
    ]);
    // The optimistic callback fires so the parent's payload updates
    // and the ``signatories`` blocker can drop off the needs_you list.
    expect(onChange).toHaveBeenCalledWith(args[2]);
  });

  it("creates a client contact inline and appends it to the picked list", async () => {
    mockLoaders();
    const created: ClientContactRow = {
      id: "cc000000-0000-0000-0000-0000000000ff",
      client_id: CLIENT_ID,
      name: "Priya Rao",
      email: "priya@northwind.example",
      title: "VP Procurement",
    };
    const createSpy = vi
      .spyOn(apiClient, "createClientContact")
      .mockResolvedValue(created);
    const patch = vi
      .spyOn(apiClient, "confirmSowField")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .mockResolvedValue({} as any);

    render(
      <SignatoriesPicker
        sowVersionId={SOW_VERSION_ID}
        clientId={CLIENT_ID}
        value={[]}
      />,
    );

    // Wait for the picker to hydrate before we touch the add form.
    await waitFor(() => {
      expect(screen.getByTestId("signatories-add-toggle")).not.toBeDisabled();
    });

    await userEvent.click(screen.getByTestId("signatories-add-toggle"));
    await userEvent.type(
      screen.getByTestId("signatories-add-name"),
      created.name,
    );
    await userEvent.type(
      screen.getByTestId("signatories-add-email"),
      created.email,
    );
    await userEvent.type(
      screen.getByTestId("signatories-add-title"),
      created.title ?? "",
    );
    await userEvent.click(screen.getByTestId("signatories-add-submit"));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(CLIENT_ID, {
        name: created.name,
        email: created.email,
        title: created.title,
      });
    });

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    const args = patch.mock.calls[0];
    expect(args[2]).toEqual([
      {
        source: "client",
        contact_id: created.id,
        name: created.name,
        email: created.email,
        title: created.title,
      },
    ]);
  });

  it("removes a picked signatory by PATCHing the shortened list", async () => {
    mockLoaders();
    const patch = vi
      .spyOn(apiClient, "confirmSowField")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .mockResolvedValue({} as any);
    const value: PickedSignatory[] = [
      {
        source: "internal",
        user_id: INTERNAL[0].id,
        name: INTERNAL[0].name,
        email: INTERNAL[0].email,
      },
      {
        source: "client",
        contact_id: CONTACTS[0].id,
        name: CONTACTS[0].name,
        email: CONTACTS[0].email,
        title: CONTACTS[0].title,
      },
    ];

    render(
      <SignatoriesPicker
        sowVersionId={SOW_VERSION_ID}
        clientId={CLIENT_ID}
        value={value}
      />,
    );

    // Let the internal + contacts loaders resolve before the click so their
    // setState doesn't fire outside act.
    await waitFor(() => {
      expect(
        screen.getByTestId(`signatories-internal-pick-${INTERNAL[1].id}`),
      ).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId("signatory-remove-0"));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    const args = patch.mock.calls[0];
    // The saved list is the normalised shape — the picker rehydrates every
    // input row through `normaliseSignatories` so free-text and object shapes
    // land at the same wire format. `user_id`/`role` are the placeholder
    // nulls the normaliser stamps for a client-source row.
    expect(args[2]).toEqual([
      {
        source: "client",
        user_id: null,
        contact_id: CONTACTS[0].id,
        name: CONTACTS[0].name,
        email: CONTACTS[0].email,
        title: CONTACTS[0].title,
        role: null,
      },
    ]);
  });
});
