// S24-AG1 F12 · every dynamic value in the FE-B dialogs and the shared client panel is a React text
// node (T9 uses a hostile client name), and colours come from tokens so dark mode follows data-theme.
// This guard fails the build if any of these files writes raw HTML or a raw hex colour.
import { readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../..");

const FILES = [
  "pages/v2/agreements/UploadDialog.tsx",
  "pages/v2/agreements/UploadForm.tsx",
  "pages/v2/agreements/fileRules.ts",
  "pages/v2/agreements/ClientAgreementsPanel.tsx",
  "pages/v2/agreements/AttachWizard.tsx",
  "pages/v2/agreements/UndoBatchDialog.tsx",
  "pages/v2/agreements/HubspotHintsDialog.tsx",
  "ui/FileDropzone.tsx",
  "ui-v2/ClientAgreementPresence.tsx",
  "pages/v2/pipeline/ClientPreview.tsx",
];

const RAW_HTML = [/dangerouslySetInnerHTML/, /\.innerHTML\b/, /\.outerHTML\b/, /insertAdjacentHTML/, /document\.write(ln)?\s*\(/];
const HEX = /#[0-9a-fA-F]{3,8}\b/g;

function code(path: string): string {
  return readFileSync(resolve(src, path), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

describe("FE-B raw-HTML and colour guard (F12)", () => {
  it.each(FILES)("%s exists and writes no raw HTML", (path) => {
    expect(statSync(resolve(src, path)).isFile()).toBe(true);
    const text = code(path);
    expect(RAW_HTML.filter((pattern) => pattern.test(text)).map(String)).toEqual([]);
  });

  it.each(FILES)("%s uses tokens, not raw hex colours", (path) => {
    expect(code(path).match(HEX)).toBeNull();
  });

  it("would catch a planted sink", () => {
    expect(RAW_HTML.some((pattern) => pattern.test("<p dangerouslySetInnerHTML={{ __html: name }} />"))).toBe(true);
    expect(RAW_HTML.some((pattern) => pattern.test("<p>{name}</p>"))).toBe(false);
  });
});
