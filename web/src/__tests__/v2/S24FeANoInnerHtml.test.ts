// S24-AG1 F12 · every client name, file name and audit sentence on the NDA &
// MSA page renders as a React text node. This guard fails the build if the page
// or anything in its folder (web/src/pages/v2/agreements/**) writes raw HTML:
// dangerouslySetInnerHTML, innerHTML / outerHTML assignments,
// insertAdjacentHTML or document.write. (The Pipeline has its own guard.)
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const pagesV2 = resolve(here, "../../pages/v2");
const PAGE = join(pagesV2, "AgreementsRegister.tsx");
const FOLDER = join(pagesV2, "agreements");
const SHARED = [resolve(here, "../../ui-v2/AgreementStateTag.tsx"), resolve(here, "../../ui-v2/LockedButton.tsx")];

const RAW_HTML_SINKS: { name: string; pattern: RegExp }[] = [
  { name: "dangerouslySetInnerHTML", pattern: /dangerouslySetInnerHTML/ },
  { name: "innerHTML", pattern: /\.innerHTML\b/ },
  { name: "outerHTML", pattern: /\.outerHTML\b/ },
  { name: "insertAdjacentHTML", pattern: /insertAdjacentHTML/ },
  { name: "document.write", pattern: /document\.write(ln)?\s*\(/ },
];

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

const files = [PAGE, ...sourcesUnder(FOLDER), ...SHARED];

describe("NDA & MSA raw-HTML guard (F12)", () => {
  it("scans the page, every file of web/src/pages/v2/agreements/** and the shared agreement parts", () => {
    const names = files.map((f) => relative(pagesV2, f));
    expect(names).toContain("AgreementsRegister.tsx");
    expect(names).toContain(join("agreements", "AgreementsClientsTable.tsx"));
    expect(names).toContain(join("agreements", "DocumentsTable.tsx"));
    expect(names).toContain(join("agreements", "UploadDialog.tsx"));
  });

  it("finds no raw-HTML sink", () => {
    const offending = files
      .map((f) => ({ file: relative(pagesV2, f), sinks: rawHtmlSinks(readFileSync(f, "utf8")) }))
      .filter((f) => f.sinks.length > 0);
    expect(offending).toEqual([]);
  });

  it("would catch a planted sink (the guard itself works)", () => {
    expect(rawHtmlSinks("<td dangerouslySetInnerHTML={{ __html: row.name }} />")).toEqual(["dangerouslySetInnerHTML"]);
    expect(rawHtmlSinks("cell.innerHTML = row.file_name;")).toEqual(["innerHTML"]);
    expect(rawHtmlSinks("<span>{row.file_name}</span>")).toEqual([]);
  });
});
