// S23-PL2 F20 · not built, verify absent: per-deal alert controls (D2, deferred),
// notes or comments on this page (D29, deferred), client sector (D1, cut).
// Every records surface is rendered with populated data and searched for any
// control, label or text that would offer them.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { BoardLane, DealRow } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { ClientPreview } from "../../pages/v2/pipeline/ClientPreview";
import { DealPreview } from "../../pages/v2/pipeline/DealPreview";
import { RecordsPanel, type RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import { Toaster } from "../../ui-v2/primitives/toaster";
import {
  TODAY,
  client,
  deal,
  overdueDeal,
  reviewDeal,
  urlState,
  wonDeal,
  workspace,
} from "./S23PipelineRecordsFixtures";

const FORBIDDEN: { what: string; pattern: RegExp }[] = [
  { what: "alert control (D2)", pattern: /\balert(s|ing)?\b|notif(y|ication)|\bbell\b|subscri(be|ption)|remind(er)?/i },
  { what: "notes or comments (D29)", pattern: /\bnotes?\b|\bcomments?\b/i },
  { what: "client sector (D1)", pattern: /\bsectors?\b|\bindustry\b|\bvertical\b/i },
];

/** The app shell's toast region (Radix labels it "Notifications (F8)"); it is not a control of this page. */
const isToastRegion = (el: Element) =>
  el.getAttribute("role") === "region" && /^Notifications \(/.test(el.getAttribute("aria-label") ?? "");

/** Every visible string and every accessible label in the document. */
function everythingShown(): string[] {
  const labels = Array.from(document.querySelectorAll("[aria-label], [placeholder], [title]"))
    .filter((el) => !isToastRegion(el))
    .flatMap((el) => ["aria-label", "placeholder", "title"].map((a) => el.getAttribute(a) ?? "").filter(Boolean));
  const options = Array.from(document.querySelectorAll("option")).map((o) => o.textContent ?? "");
  return [document.body.textContent ?? "", ...labels, ...options];
}

function expectNothingForbidden() {
  const shown = everythingShown();
  for (const { what, pattern } of FORBIDDEN) {
    const hits = shown.filter((s) => pattern.test(s)).map((s) => s.match(pattern)?.[0]);
    expect({ what, hits }).toEqual({ what, hits: [] });
  }
  expect(document.querySelector("textarea")).toBeNull();
}

function show(ui: ReactElement) {
  render(<MemoryRouter>{ui}</MemoryRouter>);
}

const populated: DealRow[] = [
  overdueDeal(),
  reviewDeal(),
  wonDeal(),
  deal({ title: "Unmapped deal", business_unit: null, region: null, bu_unmapped: true, hubspot_region: "US - Other" }),
];

function panel(overrides: Partial<RecordsPanelProps>): RecordsPanelProps {
  return {
    workspace: workspace({ rows: populated, unmapped_regions: 1 }),
    loading: false,
    error: null,
    state: urlState(),
    onStateChange: vi.fn(),
    onShowStageInList: vi.fn(),
    selected: new Set([populated[0]!.id]),
    onSelectedChange: vi.fn(),
    onOpenDeal: vi.fn(),
    onOpenClient: vi.fn(),
    onToggleWatch: vi.fn().mockResolvedValue(undefined),
    onWatchSelected: vi.fn().mockResolvedValue(undefined),
    onAddSelectedToGroup: vi.fn(),
    onOpenViewsPanel: vi.fn(),
    onResetFilters: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("F20 · nothing deferred or cut is offered on the records surfaces", () => {
  it("deals list with the bulk bar", () => {
    show(<RecordsPanel {...panel({})} />);
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expectNothingForbidden();
  });

  it("deals board", () => {
    const lanes: Record<string, BoardLane> = {
      "3": { total: 1, value_usd: "420000", deals: [populated[0]!] },
      "5": { total: 1, value_usd: "404000", deals: [populated[1]!] },
    };
    show(
      <RecordsPanel
        {...panel({ state: urlState({ layout: "board" }), workspace: workspace({ rows: [], rows_by_stage: lanes }) })}
      />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expectNothingForbidden();
  });

  it("clients list and cards", () => {
    const rows = [client(), client({ name: "Sapphire Foods", matching_deals: 0, open_deals: 0, matching_value_usd: null })];
    const { unmount } = render(
      <MemoryRouter>
        <RecordsPanel {...panel({ state: urlState({ tab: "clients" }), workspace: workspace({ rows }), selected: new Set() })} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Sapphire Foods" })).toBeInTheDocument();
    expectNothingForbidden();
    unmount();
    show(
      <RecordsPanel
        {...panel({ state: urlState({ tab: "clients", layout: "board" }), workspace: workspace({ rows }), selected: new Set() })}
      />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expectNothingForbidden();
  });

  it("deal preview of an open deal with its next-action editor, and of a closed deal", async () => {
    const d = overdueDeal();
    vi.spyOn(api, "listNextActions").mockResolvedValue({
      items: [
        {
          id: d.next_action!.id,
          opportunity_id: d.id,
          title: d.next_action!.text,
          description: d.next_action!.text,
          assignee_user_id: "me-id",
          owner_user_id: "me-id",
          due_date: d.next_action!.due_on,
          status: "open",
          blocker: null,
          outcome: null,
          approval_package_id: null,
          revision: "r1",
          can_edit: true,
        },
      ],
    });
    const props = {
      open: true,
      onOpenChange: vi.fn(),
      today: TODAY,
      hubspotPortalId: "48656168",
      assigneeId: "me-id",
      onOpenClient: vi.fn(),
      onToggleWatch: vi.fn().mockResolvedValue(undefined),
      onChanged: vi.fn(),
    };
    const { unmount } = render(
      <MemoryRouter>
        <DealPreview deal={d} {...props} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.listNextActions).toHaveBeenCalled());
    expect(screen.getByRole("textbox", { name: "Next action" })).toBeInTheDocument();
    expectNothingForbidden();
    unmount();
    show(<DealPreview deal={wonDeal()} {...props} />);
    expect(screen.getByText("Deal is closed.")).toBeInTheDocument();
    expectNothingForbidden();
  });

  it("client preview", async () => {
    vi.spyOn(wsApi, "getWorkspace").mockResolvedValue(workspace({ rows: populated }));
    show(
      <ClientPreview
        client={{ id: "c-1", name: "Vector Systems" }}
        open
        onOpenChange={vi.fn()}
        state={urlState()}
        today={TODAY}
        onOpenDeal={vi.fn()}
        onShowClientDeals={vi.fn()}
      />,
    );
    expect(await screen.findByText(`All linked opportunities · ${populated.length}`)).toBeInTheDocument();
    expectNothingForbidden();
  });
});

describe("F20 · the whole Pipeline page", () => {
  it("offers no alert, notes or client-sector control, on the page or in More filters", async () => {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "me-id", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
    vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "48656168", loading: false });
    vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
    vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([]);
    vi.spyOn(wsApi, "getWorkspace").mockResolvedValue(workspace({ rows: populated, unmapped_regions: 1 }));
    render(
      <Toaster>
        <MemoryRouter initialEntries={["/pipeline"]}>
          <PipelinePage />
        </MemoryRouter>
      </Toaster>,
    );
    expect(await screen.findByRole("button", { name: "Quality engineering pod" })).toBeInTheDocument();
    expectNothingForbidden();
    fireEvent.click(screen.getByRole("button", { name: /^More filters/ }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expectNothingForbidden();
  });
});
