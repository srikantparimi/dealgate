// S23-PL2 F15 · every HubSpot-sourced string on the Pipeline renders as a React
// text node. This guard fails the build if the page or anything in its folder
// writes raw HTML: dangerouslySetInnerHTML, innerHTML / outerHTML assignments,
// insertAdjacentHTML or document.write.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const pagesV2 = resolve(here, "../../pages/v2");
const PAGE = join(pagesV2, "Pipeline.tsx");
const FOLDER = join(pagesV2, "pipeline");

const RAW_HTML_SINKS: { name: string; pattern: RegExp }[] = [
  { name: "dangerouslySetInnerHTML", pattern: /dangerouslySetInnerHTML/ },
  { name: "innerHTML", pattern: /\.innerHTML\b/ },
  { name: "outerHTML", pattern: /\.outerHTML\b/ },
  { name: "insertAdjacentHTML", pattern: /insertAdjacentHTML/ },
  { name: "document.write", pattern: /document\.write(ln)?\s*\(/ },
];

/** Names of the raw-HTML sinks found in a source text. */
function rawHtmlSinks(source: string): string[] {
  return RAW_HTML_SINKS.filter(({ pattern }) => pattern.test(source)).map(({ name }) => name);
}

function sourcesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourcesUnder(path);
    return /\.(ts|tsx|js|jsx)$/.test(entry) ? [path] : [];
  });
}

const files = [PAGE, ...sourcesUnder(FOLDER)];

describe("Pipeline raw-HTML guard (F15)", () => {
  it("scans the page and every file of web/src/pages/v2/pipeline/**", () => {
    expect(statSync(PAGE).isFile()).toBe(true);
    const names = files.map((f) => relative(pagesV2, f));
    expect(names).toContain("Pipeline.tsx");
    expect(names).toContain(join("pipeline", "RecordsPanel.tsx"));
    expect(names).toContain(join("pipeline", "DealPreview.tsx"));
  });

  it("finds no dangerouslySetInnerHTML or other raw-HTML sink on the page", () => {
    const offending = files
      .map((f) => ({ file: relative(pagesV2, f), sinks: rawHtmlSinks(readFileSync(f, "utf8")) }))
      .filter((f) => f.sinks.length > 0);
    expect(offending).toEqual([]);
  });

  it("would catch a planted sink (the guard itself works)", () => {
    expect(rawHtmlSinks("<div dangerouslySetInnerHTML={{ __html: deal.title }} />")).toEqual([
      "dangerouslySetInnerHTML",
    ]);
    expect(rawHtmlSinks("el.innerHTML = name;")).toEqual(["innerHTML"]);
    expect(rawHtmlSinks("cell.insertAdjacentHTML('beforeend', x)")).toEqual(["insertAdjacentHTML"]);
    expect(rawHtmlSinks("<span>{deal.title}</span>")).toEqual([]);
  });
});
