import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ClientAgreementPresence } from "../../ui-v2/ClientAgreementPresence";
import * as api from "../../api/client";
vi.mock("../../api/client", () => ({
  listAgreements: vi.fn(),
  getMe: vi.fn(),
}));
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getMe).mockResolvedValue({
    groups: ["Legal"],
  } as api.MeResponse);
});
const mount = (id = "a") =>
  render(
    <MemoryRouter>
      <ClientAgreementPresence clientId={id} />
    </MemoryRouter>,
  );
it("keeps multiple documents and links actions to the exact client and kind", async () => {
  vi.mocked(api.listAgreements).mockResolvedValue({
    items: [
      { id: "1", kind: "NDA" },
      { id: "2", kind: "NDA" },
    ] as api.AgreementRow[],
  });
  mount();
  expect(await screen.findByText("NDA: 2 on file")).toBeTruthy();
  expect(screen.getByText("MSA: Not on file")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "Upload MSA" }).getAttribute("href"),
  ).toBe("/agreements?client_id=a&kind=MSA&upload=1");
  expect(
    screen
      .getByRole("link", { name: "View NDA documents" })
      .getAttribute("href"),
  ).toBe("/agreements?client_id=a&kind=NDA");
});
it("does not call failed loading absence", async () => {
  vi.mocked(api.listAgreements).mockRejectedValue(
    new Error("Access unavailable"),
  );
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Access unavailable",
  );
  expect(screen.queryByText(/Not on file/)).toBeNull();
});
it("readers see presence without mutation controls", async () => {
  vi.mocked(api.getMe).mockResolvedValue({
    groups: ["Sales"],
  } as api.MeResponse);
  vi.mocked(api.listAgreements).mockResolvedValue({ items: [] });
  mount();
  await screen.findByText("NDA: Not on file");
  expect(screen.queryByRole("link", { name: "Upload NDA" })).toBeNull();
});
it("does not show previous client presence after a route change", async () => {
  let resolve!: (value: api.AgreementListResponse) => void;
  vi.mocked(api.listAgreements).mockImplementation(({ client_id } = {}) =>
    client_id === "a"
      ? new Promise((r) => {
          resolve = r;
        })
      : Promise.resolve({ items: [] }),
  );
  const view = mount();
  view.rerender(
    <MemoryRouter>
      <ClientAgreementPresence clientId="b" />
    </MemoryRouter>,
  );
  await screen.findByText("NDA: Not on file");
  resolve({ items: [{ id: "old", kind: "NDA" }] as api.AgreementRow[] });
  await waitFor(() => expect(screen.queryByText("NDA: 1 on file")).toBeNull());
});
