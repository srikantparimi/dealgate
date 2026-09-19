import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * One-accent enforcement — v2.1 addendum rule 1.
 *
 * Design tokens live in `tailwind.config.ts` and `src/index.css`. Every
 * `.tsx` / `.ts` file under `web/src/pages/v2/` and `web/src/ui-v2/`
 * must reach for colour by class or CSS variable, never a raw hex.
 *
 * This test scans those directories for a `#rrggbb` (or `#rgb` / rgba)
 * pattern. It ignores:
 *   - comments (line comments starting with `//` and everything inside
 *     `/* ... *\/` blocks)
 *   - strings passed to `data-testid=` or `aria-*=`
 *   - the small allow-list below for known SVG glyph fills / stroke
 *     values that are UI iconography, not colour tokens
 *   - the tailwind config and CSS variable files themselves (they are
 *     the *source* of hex values by definition — the tokens.test.ts
 *     guards those separately)
 *   - test files themselves
 */
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../../../");
const WEB_SRC = path.join(REPO_ROOT, "web/src");

const SCAN_ROOTS = [
  path.join(WEB_SRC, "pages/v2"),
  path.join(WEB_SRC, "ui-v2"),
];

// Files here are the palette source; hex values are expected.
const SOURCE_ALLOWLIST = new Set<string>([
  path.join(REPO_ROOT, "web/tailwind.config.ts"),
  path.join(WEB_SRC, "index.css"),
]);

/**
 * Documented one-off hex glyphs. Keep this list short and add a
 * comment for every entry. If the list starts to grow, promote the
 * value to a token in `DealGate_Design_Tokens_v2.1.json` instead.
 */
const KNOWN_GLYPH_HEXES = new Set<string>([
  // (currently empty — no SVG glyph in ui-v2 or pages/v2 uses a hex.)
]);

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = path.join(dir, entry);
    const s = statSync(p);
    if (s.isDirectory()) {
      out.push(...walk(p));
      continue;
    }
    if (!/\.(tsx?|ts)$/.test(entry)) continue;
    if (/\.test\.(tsx?|ts)$/.test(entry)) continue;
    out.push(p);
  }
  return out;
}

/**
 * Strip line comments and block comments so we don't flag `// #abc`
 * or `/* #123 *\/`. Naive but sufficient for TS/TSX source we control.
 */
function stripComments(source: string): string {
  let out = "";
  let i = 0;
  const n = source.length;
  while (i < n) {
    const ch = source[i];
    const next = source[i + 1];
    if (ch === "/" && next === "/") {
      while (i < n && source[i] !== "\n") i++;
      continue;
    }
    if (ch === "/" && next === "*") {
      i += 2;
      while (i < n && !(source[i] === "*" && source[i + 1] === "/")) i++;
      i += 2;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

interface Finding {
  file: string;
  line: number;
  match: string;
  context: string;
}

function findHexes(file: string): Finding[] {
  const raw = readFileSync(file, "utf-8");
  const stripped = stripComments(raw);
  const findings: Finding[] = [];
  const lines = stripped.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const m of line.matchAll(HEX_RE)) {
      const match = m[0];
      // Skip allow-listed glyph hexes.
      if (KNOWN_GLYPH_HEXES.has(match.toLowerCase())) continue;
      // Skip data-testid / aria-* string values that happen to look
      // like a hex.
      const before = line.slice(0, m.index ?? 0);
      if (/(data-testid|aria-[a-z]+)=?\s*["'`]?[^"'`]*$/i.test(before)) {
        continue;
      }
      findings.push({
        file,
        line: i + 1,
        match,
        context: line.trim(),
      });
    }
  }
  return findings;
}

describe("no raw hex in v2 components", () => {
  it("no #rrggbb / #rgb inside pages/v2 or ui-v2 (tokens only)", () => {
    const files: string[] = [];
    for (const root of SCAN_ROOTS) {
      try {
        files.push(...walk(root));
      } catch {
        // Directory missing — nothing to scan.
      }
    }
    const allFindings: Finding[] = [];
    for (const f of files) {
      if (SOURCE_ALLOWLIST.has(f)) continue;
      allFindings.push(...findHexes(f));
    }
    if (allFindings.length > 0) {
      const lines = allFindings
        .map(
          (f) =>
            `  ${path.relative(REPO_ROOT, f.file)}:${f.line}  ${f.match}  →  ${f.context}`,
        )
        .join("\n");
      throw new Error(
        `Found raw hex colours in v2 components. Use design-token classes ` +
          `instead (e.g. bg-primary, text-danger):\n${lines}`,
      );
    }
    expect(allFindings.length).toBe(0);
  });
});
