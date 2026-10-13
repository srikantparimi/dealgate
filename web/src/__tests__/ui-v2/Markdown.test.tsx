import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown, parseMarkdown } from "../../ui-v2/Markdown";

const REPORT = [
  "# Forecast model — dry run",
  "",
  "Parsed **3 business units** from the `Dashboard` tab.",
  "Second line of the same paragraph.",
  "",
  "## By business unit",
  "",
  "| Business unit | Clients | People |",
  "|---|---:|---:|",
  "| ST21 | 4 | 31 |",
  "| IT Avalon | 2 | 9 |",
  "",
  "### Needs attention",
  "- Gamma Health-VMS: **2 people** without a location",
  "- <script>alert(1)</script> is text, not markup",
].join("\n");

describe("ui-v2 · Markdown", () => {
  it("parses headings, paragraphs, bullets and pipe tables into blocks", () => {
    const blocks = parseMarkdown(REPORT);
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "heading", "table", "heading", "list"]);
    expect(blocks[1]).toEqual({ kind: "paragraph", text: "Parsed **3 business units** from the `Dashboard` tab. Second line of the same paragraph." });
    expect(blocks[3]).toEqual({ kind: "table", header: ["Business unit", "Clients", "People"], rows: [["ST21", "4", "31"], ["IT Avalon", "2", "9"]] });
  });

  it("renders bold, code and tables, and never interprets raw HTML", () => {
    render(<Markdown source={REPORT} />);
    expect(screen.getByRole("heading", { level: 2, name: "Forecast model — dry run" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "By business unit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Needs attention" })).toBeInTheDocument();
    expect(screen.getByText("3 business units").tagName).toBe("STRONG");
    expect(screen.getByText("Dashboard").tagName).toBe("CODE");
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Business unit", "Clients", "People"]);
    expect(within(table).getByText("IT Avalon")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[1]).toHaveTextContent("<script>alert(1)</script> is text, not markup");
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders nothing for an empty report", () => {
    const { container } = render(<Markdown source="" />);
    expect(container.firstChild).toBeEmptyDOMElement();
  });
});
