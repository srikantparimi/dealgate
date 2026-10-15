// S23-PL2 F4/F5 · the view-state transitions in workspaceState.ts: a metric
// card's drill and the stage selection's status memory working together.
import { describe, expect, it } from "vitest";

import {
  applyDrill,
  readWorkspaceUrl,
  toggleStage,
  writeWorkspaceUrl,
} from "../../pages/v2/pipeline/workspaceState";

describe("a metric drill while stages are selected (F4 with F5)", () => {
  it("keeps the drilled status when the last stage is removed", () => {
    // Closed won → select stage 7 (status All, Closed won remembered).
    let s = readWorkspaceUrl(new URLSearchParams("status=won"));
    s = toggleStage(s, 7);
    expect(s.query.status).toBe("all");
    expect(s.statusBefore).toBe("won");
    // The "Open deals" card: status Open, stage 7 kept.
    s = applyDrill(s, { tab: "deals", status: "open" });
    expect(s.query.status).toBe("open");
    expect(s.query.stage).toEqual([7]);
    expect(writeWorkspaceUrl(s).get("status_before")).toBe("open");
    // Removing the last stage keeps the status the card applied.
    s = toggleStage(s, 7);
    expect(s.query.stage).toEqual([]);
    expect(s.query.status).toBe("open");
    expect(s.statusBefore).toBeNull();
  });

  it("a drill that does not set a status keeps the remembered one", () => {
    let s = readWorkspaceUrl(new URLSearchParams("status=won"));
    s = toggleStage(s, 7);
    s = applyDrill(s, { tab: "deals", attention: "overdue" });
    expect(s.query.status).toBe("all");
    expect(s.statusBefore).toBe("won");
    s = toggleStage(s, 7);
    expect(s.query.status).toBe("won");
  });

  it("a drill without stages selected remembers nothing", () => {
    const s = applyDrill(readWorkspaceUrl(new URLSearchParams("status=won")), { tab: "deals", status: "open" });
    expect(s.query.status).toBe("open");
    expect(s.statusBefore).toBeNull();
    expect(writeWorkspaceUrl(s).get("status_before")).toBeNull();
  });
});
