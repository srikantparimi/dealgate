// S24-AG1 FE-A · the page's URL state (agreementsState.ts) and its display
// formatting (agreementsFormat.ts): validated reading with fallbacks, writing
// without defaults, reset-then-drill for cards (never merged with the current
// filters), tab switching, chips, the request queries and the row facts.
import { describe, expect, it } from "vitest";

import { batchSentence, canUndo } from "../../pages/v2/agreements/CutoverLine";
import { fileSizeText, isBatchLabel, pacificDate } from "../../pages/v2/agreements/agreementsFormat";
import {
  applyCardDrill,
  basisText,
  buildChips,
  firstMissingKind,
  listQueryOf,
  readAgreementsUrl,
  resetFilters,
  setTab,
  stageLabel,
  stageTone,
  workspaceQueryOf,
  writeAgreementsUrl,
  type AgreementsBatch,
} from "../../pages/v2/agreements/agreementsState";

const BATCH_DONE: AgreementsBatch = {
  id: "AG-0001",
  status: "done",
  kinds: ["NDA", "MSA"],
  created_by: "Srikanth Parimi",
  created_at: "2026-10-15T18:05:00Z",
  target_count: 85,
  done_count: 85,
  attached_count: 157,
  skipped_count: 0,
  attached_clients: 85,
};

const read = (search: string) => readAgreementsUrl(new URLSearchParams(search));

describe("reading and writing the URL", () => {
  it("reads every field and falls back on anything unknown", () => {
    const s = read(
      "tab=documents&relationship=net_new&status=attention&stage=past_stage_1&bu=Retro+Rabbit&bu=ST21&bu=Mars&q=+cob+&sort=stage&page=3&page_size=50&client_id=abc",
    );
    expect(s).toEqual({
      tab: "documents",
      relationship: "net_new",
      status: "attention",
      stage: "past_stage_1",
      bu: ["ST21", "Retro Rabbit"],
      q: "cob",
      sort: "stage",
      page: 3,
      page_size: 50,
      clientId: "abc",
      kind: null,
      upload: false,
    });
    const bad = read("tab=files&relationship=x&status=x&stage=x&sort=x&page=-2&page_size=30&kind=SOW&upload=yes");
    expect(bad).toMatchObject({
      tab: "clients",
      relationship: "all",
      status: "any",
      stage: "any",
      sort: "attention",
      page: 1,
      page_size: 25,
      kind: null,
      upload: false,
    });
  });

  it("accepts the old links: client_id or client, kind and upload=1", () => {
    expect(read("client=xyz").clientId).toBe("xyz");
    expect(read("client_id=a&client=b").clientId).toBe("a");
    expect(read("client_id=a&kind=MSA&upload=1")).toMatchObject({ clientId: "a", kind: "MSA", upload: true });
  });

  it("writes only what differs from the defaults and never writes the one-shot parameters back", () => {
    expect(writeAgreementsUrl(read("")).toString()).toBe("");
    const s = read("relationship=existing&bu=ST21&q=acme&page=2&page_size=100&client_id=c1&kind=NDA&upload=1");
    expect(writeAgreementsUrl(s).toString()).toBe(
      "relationship=existing&bu=ST21&q=acme&page=2&page_size=100&client_id=c1",
    );
    // A round trip is stable.
    expect(read(writeAgreementsUrl(s).toString())).toEqual({ ...s, kind: null, upload: false });
  });

  it("caps the search at 120 characters", () => {
    expect(read(`q=${"a".repeat(200)}`).q).toHaveLength(120);
  });
});

describe("transitions", () => {
  it("a card resets every filter, opens Clients and applies only its validated drill", () => {
    const current = read("tab=activity&relationship=existing&status=missing_nda&stage=no_active_deal&bu=ST21&q=x&page=4&sort=name&page_size=50");
    const next = applyCardDrill(current, { status: "attention" });
    expect(next).toMatchObject({
      tab: "clients",
      relationship: "all",
      status: "attention",
      stage: "any",
      bu: [],
      q: "",
      page: 1,
      sort: "name",
      page_size: 50,
    });
    // Unknown keys and values in a drill are ignored, arrays are kept.
    const odd = applyCardDrill(current, { status: "nonsense", tab: "documents", page: "7", bu: ["IT Avalon", "Mars"] });
    expect(odd).toMatchObject({ tab: "clients", status: "any", page: 1, bu: ["IT Avalon"] });
    expect(applyCardDrill(current, {})).toMatchObject({ relationship: "all", status: "any" });
    expect(applyCardDrill(current, null)).toMatchObject({ relationship: "all", status: "any" });
  });

  it("switching tab clears the search and the page and keeps the client filters", () => {
    const s = setTab(read("status=attention&q=x&page=3&sort=stage"), "documents");
    expect(s).toMatchObject({ tab: "documents", status: "attention", q: "", page: 1, sort: "stage" });
  });

  it("Reset filters keeps the tab, sort, page size and the open panel", () => {
    const s = resetFilters(read("tab=documents&status=attention&q=x&page=3&sort=stage&page_size=100&client_id=c"));
    expect(s).toMatchObject({ tab: "documents", status: "any", q: "", page: 1, sort: "stage", page_size: 100, clientId: "c" });
  });

  it("the workspace query leaves out the search and the page of the Documents and Activity tabs", () => {
    const clients = read("status=attention&q=cob&page=2&page_size=50");
    expect(workspaceQueryOf(clients)).toEqual({
      relationship: "all",
      status: "attention",
      stage: "any",
      bu: [],
      q: "cob",
      sort: "attention",
      page: 2,
      page_size: 50,
    });
    const docs = read("tab=documents&status=attention&q=nda&page=2&page_size=50");
    expect(workspaceQueryOf(docs)).toMatchObject({ status: "attention", q: "", page: 1, page_size: 50 });
    expect(listQueryOf(docs)).toEqual({ q: "nda", page: 2, page_size: 50 });
  });
});

describe("chips", () => {
  it("one chip per active filter with the prototype's words; each removes only itself", () => {
    const s = read("relationship=net_new&status=possible_duplicate&stage=stage_1_only&bu=ST21&bu=Retro+Rabbit&q=acme");
    const chips = buildChips(s);
    expect(chips.map((c) => c.text)).toEqual([
      "Net-new clients",
      "Possible duplicate names",
      "Stage 1 only",
      "ST21 · US",
      "Retro Rabbit · South Africa",
      "Search: acme",
    ]);
    const withoutSt21 = chips.find((c) => c.key === "bu-ST21")!.next;
    expect(withoutSt21.bu).toEqual(["Retro Rabbit"]);
    expect(withoutSt21.status).toBe("possible_duplicate");
    expect(buildChips(read(""))).toEqual([]);
  });
});

describe("row facts", () => {
  const base = { stage_text: undefined, furthest_open_stage: 0, on_hold: false };

  it("uses the server's stage words; falls back without inventing a stage name", () => {
    expect(stageLabel({ ...base, stage_text: "4 · Proposal", furthest_open_stage: 4 })).toBe("4 · Proposal");
    expect(stageLabel({ ...base, stage_text: "No active deal" })).toBeNull();
    expect(stageLabel({ ...base, stage_text: "On hold", on_hold: true })).toBe("On hold");
    expect(stageLabel({ ...base, furthest_open_stage: 3 })).toBe("Stage 3");
    expect(stageLabel({ ...base, on_hold: true })).toBe("On hold");
    expect(stageLabel(base)).toBeNull();
  });

  it("stage tone: past stage 1 in the accent, stage 1 quiet, Hold alone or unknown warns", () => {
    expect(stageTone({ furthest_open_stage: 2, on_hold: false })).toBe("progress");
    expect(stageTone({ furthest_open_stage: 1, on_hold: true })).toBe("progress");
    expect(stageTone({ furthest_open_stage: 1, on_hold: false })).toBe("neutral");
    expect(stageTone({ furthest_open_stage: 0, on_hold: true })).toBe("warning");
  });

  it("the upload starts on the first missing kind", () => {
    expect(firstMissingKind({ nda: { state: "missing" }, msa: { state: "missing" } })).toBe("NDA");
    expect(firstMissingKind({ nda: { state: "covered" }, msa: { state: "missing" } })).toBe("MSA");
    expect(firstMissingKind({ nda: { state: "client" }, msa: { state: "standard" } })).toBe("NDA");
  });

  it("basis words: the server's text, else the basis", () => {
    expect(basisText({ basis_text: "Engagement from the forecast model", relationship: "existing", relationship_basis: "sow_engagement" })).toBe(
      "Engagement from the forecast model",
    );
    expect(basisText({ relationship: "existing", relationship_basis: "closed_won_and_sow" })).toBe("Closed Won deal and SOW");
    expect(basisText({ relationship: "net_new", relationship_basis: "manual" })).toBe("Marked net new");
  });
});

describe("the cutover line's batch sentence", () => {
  it("names the batch by its label and counts clients, not rows", () => {
    expect(batchSentence(BATCH_DONE)).toBe(" Latest batch AG-0001 attached 85 clients.");
    expect(batchSentence({ ...BATCH_DONE, attached_clients: 1 })).toBe(" Latest batch AG-0001 attached 1 client.");
    expect(batchSentence({ ...BATCH_DONE, attached_clients: undefined })).toBe(" Latest batch AG-0001.");
    expect(batchSentence(null)).toBe(" No active batch.");
    expect(batchSentence({ ...BATCH_DONE, status: "undoing" })).toBe(" Batch AG-0001 is being undone.");
    // The phase decides the words, and the server's sentence is never doubled (review finding).
    expect(
      batchSentence({ ...BATCH_DONE, status: "failed", failed_phase: "run", done_count: 50, target_count: 85 }),
    ).toBe(" Batch AG-0001 stopped after 50 of 85 clients. Attach the standard copies again to finish.");
    expect(batchSentence({ ...BATCH_DONE, status: "failed", failed_phase: "undo", error: "The undo stopped." })).toBe(
      " The undo of batch AG-0001 stopped before it finished. Press Undo again to finish.",
    );
    expect(batchSentence({ ...BATCH_DONE, id: "6fa459ea-ee8a-4ca4-894e-db77e160355e" })).toBe(" No active batch.");
  });

  it("offers undo for a finished batch only", () => {
    expect(canUndo(BATCH_DONE)).toBe(true);
    expect(canUndo({ ...BATCH_DONE, status: "failed" })).toBe(true);
    expect(canUndo({ ...BATCH_DONE, status: "running" })).toBe(false);
    expect(canUndo({ ...BATCH_DONE, status: "undoing" })).toBe(false);
    expect(canUndo(null)).toBe(false);
  });
});

describe("formatting", () => {
  it("Pacific calendar dates for instants", () => {
    expect(pacificDate("2026-10-16T05:30:00Z")).toBe("Oct 15, 2026");
    expect(pacificDate("2026-10-15T18:00:00Z")).toBe("Oct 15, 2026");
    expect(pacificDate(null)).toBe("Date not recorded");
    expect(pacificDate("not a date")).toBe("Date not recorded");
  });

  it("file sizes in the prototype's words", () => {
    expect(fileSizeText(999)).toBe("under 1 KB");
    expect(fileSizeText(214_000)).toBe("214 KB");
    expect(fileSizeText(3_400_000)).toBe("3.4 MB");
    expect(fileSizeText(null)).toBeNull();
  });

  it("only label-shaped batch ids are shown", () => {
    expect(isBatchLabel("AG-0001")).toBe(true);
    expect(isBatchLabel("6fa459ea-ee8a-4ca4-894e-db77e160355e")).toBe(false);
    expect(isBatchLabel(null)).toBe(false);
  });
});
