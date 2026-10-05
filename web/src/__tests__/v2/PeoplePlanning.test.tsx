import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as people from "../../api/people";
import * as client from "../../api/client";
import { PeoplePlanningPage } from "../../pages/v2/PeoplePlanning";

const source = {
  id: "batch-one",
  source_system: "HR roster",
  revision: 1,
  person_count: 1,
  source_as_of: "2026-10-01T00:00:00Z",
  status: "committed",
};
const supply: people.PeopleAvailability = {
  basis: "gross_with_commitments",
  is_reservation: false,
  sources: [source],
  people: [
    {
      person_id: "person",
      version_id: "version",
      source_system: "HR roster",
      batch_id: "batch-one",
      display_name: "Morgan Example",
      role: "Engineer",
      skills: ["typescript"],
      level: "Senior",
      location: "US",
      timezone: "America/Los_Angeles",
      evidence: ["HR source row 1"],
      intervals: [
        {
          kind: "gross",
          allocation: "0.500001",
          start_date: "2026-11-01",
          end_date: "2027-04-30",
          assignment_key: null,
        },
        {
          kind: "committed",
          allocation: "0.25",
          start_date: "2026-11-01",
          end_date: "2026-11-15",
          assignment_key: "project-one",
        },
      ],
    },
  ],
};
const roster = {
  source_system: "HR roster",
  source_as_of: "2026-10-01T00:00:00Z",
  basis: "gross_with_commitments",
  people: [{ person_key: "p1", salary: "FORBIDDEN-MUST-REACH-VALIDATOR" }],
};
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["HR"],
  } as client.MeResponse);
  vi.spyOn(people, "getPeopleAvailability").mockResolvedValue(supply);
  vi.spyOn(people, "getPeopleImports").mockResolvedValue({
    items: [
      {
        ...source,
        imported_at: "2026-10-01",
        imported_by: "hr-owner",
        reason: "Initial roster",
        previous_batch_id: null,
      },
    ],
    total: 1,
    page: 1,
    size: 50,
  });
  vi.spyOn(people, "importPeopleSupply").mockResolvedValue({
    ...source,
    id: "batch-two",
    revision: 2,
  });
});
async function draft() {
  await screen.findByText("Morgan Example");
  fireEvent.change(screen.getByLabelText("Roster JSON"), {
    target: { value: JSON.stringify(roster) },
  });
  fireEvent.change(screen.getByLabelText("Import reason"), {
    target: { value: "Confirmed HR correction" },
  });
}
describe("People managed supply", () => {
  it("renders named supply, exact allocation, dated commitments and source freshness", async () => {
    render(<PeoplePlanningPage />);
    expect(await screen.findByText("Morgan Example")).toBeInTheDocument();
    expect(screen.getByText("typescript")).toBeInTheDocument();
    expect(screen.getByText(/0.500001/)).toBeInTheDocument();
    expect(screen.getByText(/project-one/)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-10-01T00:00:00Z/).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.queryByRole("button", { name: /hire|reserve|sourcing/i }),
    ).not.toBeInTheDocument();
  });
  it("submits original extra fields for whole-file validation and binds the latest same-source batch", async () => {
    vi.mocked(people.importPeopleSupply).mockRejectedValue(
      new client.ApiError(422, {
        detail: [
          {
            loc: ["body", "people", 0, "salary"],
            msg: "Extra inputs are not permitted",
          },
        ],
      }),
    );
    render(<PeoplePlanningPage />);
    await draft();
    fireEvent.click(screen.getByRole("button", { name: "Import roster" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "people.0.salary",
    );
    expect(people.importPeopleSupply).toHaveBeenCalledWith({
      ...roster,
      reason: "Confirmed HR correction",
      expected_previous_batch_id: "batch-one",
      request_key: expect.any(String),
    });
    expect(screen.getByLabelText("Roster JSON")).toHaveValue(
      JSON.stringify(roster),
    );
  });
  it("retains a stale draft and request identity until explicit source reload", async () => {
    vi.mocked(people.importPeopleSupply).mockRejectedValue(
      new Error("409: Workforce source changed"),
    );
    render(<PeoplePlanningPage />);
    await draft();
    fireEvent.click(screen.getByRole("button", { name: "Import roster" }));
    await screen.findByRole("alert");
    const key = vi.mocked(people.importPeopleSupply).mock.calls[0][0]
      .request_key;
    fireEvent.click(screen.getByRole("button", { name: "Import roster" }));
    await waitFor(() =>
      expect(people.importPeopleSupply).toHaveBeenCalledTimes(2),
    );
    expect(
      vi.mocked(people.importPeopleSupply).mock.calls[1][0].request_key,
    ).toBe(key);
    vi.mocked(people.getPeopleAvailability).mockResolvedValue({
      ...supply,
      sources: [{ ...source, id: "batch-new", revision: 3 }],
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Reload source versions" }),
    );
    await screen.findByText(/Current revision: 3/);
    fireEvent.click(screen.getByRole("button", { name: "Import roster" }));
    await waitFor(() => expect(people.importPeopleSupply).toHaveBeenCalledTimes(3));
    expect(vi.mocked(people.importPeopleSupply).mock.calls[2][0].expected_previous_batch_id).toBe("batch-new");
    expect(screen.getByLabelText("Roster JSON")).toHaveValue(
      JSON.stringify(roster),
    );
    expect(screen.getByLabelText("Import reason")).toHaveValue(
      "Confirmed HR correction",
    );
  });
  it("refreshes persisted supply and history only after a successful import", async () => {
    render(<PeoplePlanningPage />);
    await draft();
    fireEvent.click(screen.getByRole("button", { name: "Import roster" }));
    expect(await screen.findByText(/Imported revision 2/)).toBeInTheDocument();
    await waitFor(() =>
      expect(people.getPeopleAvailability).toHaveBeenCalledTimes(2),
    );
    expect(people.getPeopleImports).toHaveBeenCalledTimes(2);
  });
  it("does not fetch named supply for unauthorized roles", async () => {
    vi.mocked(client.getMe).mockResolvedValue({
      groups: ["Sales"],
    } as client.MeResponse);
    render(<PeoplePlanningPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "HR or SystemAdmin",
    );
    expect(people.getPeopleAvailability).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Roster JSON")).not.toBeInTheDocument();
  });
  it("keeps loading and read failure distinct from empty supply", async () => {
    vi.mocked(people.getPeopleAvailability).mockRejectedValue(
      new Error("Supply unavailable"),
    );
    render(<PeoplePlanningPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Supply unavailable",
    );
    expect(
      screen.queryByText("No workforce supply imported."),
    ).not.toBeInTheDocument();
  });
  it("loads an uploaded JSON file without dropping unknown fields", async () => {
    render(<PeoplePlanningPage />);
    await screen.findByText("Morgan Example");
    const file = new File([JSON.stringify(roster)], "roster.json", {
      type: "application/json",
    });
    fireEvent.change(screen.getByLabelText("Roster file"), {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Roster JSON")).toHaveValue(
        JSON.stringify(roster),
      ),
    );
    expect(
      screen.getByRole("button", { name: "Import roster" }),
    ).toBeDisabled();
  });
});
