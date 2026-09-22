import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { DirectCostCategories } from "../../pages/v2/settings/DirectCostCategories";

let groups = ["Finance"];
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: { groups } }) }));

beforeEach(() => {
  groups = ["Finance"];
  vi.spyOn(api, "getDirectCostCategories").mockResolvedValue({ categories: ["Travel", "Other"] });
  vi.spyOn(api, "saveDirectCostCategories").mockImplementation(async (categories) => ({ categories }));
});
afterEach(() => vi.restoreAllMocks());

it("loads shared categories and saves a Finance edit", async () => {
  render(<DirectCostCategories />);
  fireEvent.change(await screen.findByDisplayValue("Travel"), { target: { value: "Software" } });
  fireEvent.click(screen.getByRole("button", { name: "Save categories" }));
  await waitFor(() => expect(api.saveDirectCostCategories).toHaveBeenCalledWith(["Software", "Other"]));
  expect(await screen.findByRole("status")).toHaveTextContent("Categories saved");
});

it("gives CEO a read-only view", async () => {
  groups = ["CEO"];
  render(<DirectCostCategories />);
  expect(await screen.findByDisplayValue("Travel")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Save categories" })).not.toBeInTheDocument();
});

it("keeps pending edits and exposes a save error", async () => {
  vi.mocked(api.saveDirectCostCategories).mockRejectedValue(new Error("Unable to save categories"));
  render(<DirectCostCategories />);
  fireEvent.change(await screen.findByDisplayValue("Travel"), { target: { value: "Software" } });
  fireEvent.click(screen.getByRole("button", { name: "Save categories" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save categories");
  expect(screen.getByDisplayValue("Software")).toBeInTheDocument();
});
