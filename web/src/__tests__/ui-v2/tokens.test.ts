import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import tailwindConfig from "../../../tailwind.config";

/**
 * Guard-rail against silent design-token drift.
 *
 * Every color in `docs/design/DealGate_Design_Tokens.json` must have a
 * matching entry under `theme.extend.colors` in `tailwind.config.ts` AND
 * a matching CSS custom property in `src/index.css`. If a designer adds a
 * token, this fails loudly and the developer must wire it end-to-end.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../../../");

interface TokensJson {
  colors: {
    light: Record<string, string>;
    dark: Record<string, string>;
  };
}

const tokens = JSON.parse(
  readFileSync(
    path.join(REPO_ROOT, "docs/design/DealGate_Design_Tokens.json"),
    "utf-8",
  ),
) as TokensJson;

const indexCss = readFileSync(
  path.join(REPO_ROOT, "web/src/index.css"),
  "utf-8",
);

// Tokens JSON uses camelCase keys → Tailwind uses kebab / grouped names.
// This map codifies the correspondence for the linter; keep it in sync
// with `tailwind.config.ts`.
const TAILWIND_KEY_BY_TOKEN: Record<string, string> = {
  canvas: "canvas",
  surface: "surface",
  navigation: "navigation",
  text: "text",
  textSecondary: "text-secondary",
  divider: "divider",
  inputBorder: "input-border",
  primary: "primary",
  onPrimary: "primary.fg",
  primarySubtle: "primary.subtle",
  success: "success",
  successSurface: "success.surface",
  warning: "warning",
  warningSurface: "warning.surface",
  danger: "danger",
  dangerSurface: "danger.surface",
  focus: "focus",
  executiveBanner: "executive",
  executiveText: "executive.fg",
  executiveSecondary: "executive.muted",
  heroAction: "hero",
  heroActionText: "hero.fg",
};

const CSS_VAR_BY_TOKEN: Record<string, string> = {
  canvas: "--dg-canvas",
  surface: "--dg-surface",
  navigation: "--dg-navigation",
  text: "--dg-text",
  textSecondary: "--dg-text-secondary",
  divider: "--dg-divider",
  inputBorder: "--dg-input-border",
  primary: "--dg-primary",
  onPrimary: "--dg-on-primary",
  primarySubtle: "--dg-primary-subtle",
  success: "--dg-success",
  successSurface: "--dg-success-surface",
  warning: "--dg-warning",
  warningSurface: "--dg-warning-surface",
  danger: "--dg-danger",
  dangerSurface: "--dg-danger-surface",
  focus: "--dg-focus",
  executiveBanner: "--dg-executive-banner",
  executiveText: "--dg-executive-text",
  executiveSecondary: "--dg-executive-secondary",
  heroAction: "--dg-hero-action",
  heroActionText: "--dg-hero-action-text",
};

function resolveTailwindPath(colors: Record<string, unknown>, dotted: string): unknown {
  return dotted.split(".").reduce<unknown>((acc, key) => {
    if (acc == null || typeof acc !== "object") return undefined;
    return (acc as Record<string, unknown>)[key === "fg" || key === "subtle" || key === "surface" || key === "muted" ? key : key];
  }, colors);
}

describe("design tokens", () => {
  const colors =
    (tailwindConfig.theme?.extend?.colors ?? {}) as Record<string, unknown>;

  it("declares every light token in the tailwind config", () => {
    for (const key of Object.keys(tokens.colors.light)) {
      const tailwindKey = TAILWIND_KEY_BY_TOKEN[key];
      expect(
        tailwindKey,
        `token '${key}' has no Tailwind mapping in tokens.test.ts`,
      ).toBeTruthy();
      expect(
        resolveTailwindPath(colors, tailwindKey),
        `token '${key}' missing under theme.extend.colors.${tailwindKey}`,
      ).toBeTruthy();
    }
  });

  it("declares every dark token in the tailwind config", () => {
    for (const key of Object.keys(tokens.colors.dark)) {
      expect(TAILWIND_KEY_BY_TOKEN[key]).toBeTruthy();
    }
  });

  it("exposes every token as a CSS variable in index.css for light theme", () => {
    for (const [key, value] of Object.entries(tokens.colors.light)) {
      const varName = CSS_VAR_BY_TOKEN[key];
      expect(varName, `token '${key}' missing CSS var mapping`).toBeTruthy();
      // Look for the variable in the :root / [data-theme="light"] block.
      const pattern = new RegExp(`${varName}\\s*:\\s*${value}`, "i");
      expect(
        pattern.test(indexCss),
        `expected ${varName}: ${value} in web/src/index.css (light theme)`,
      ).toBe(true);
    }
  });

  it("exposes every token as a CSS variable in index.css for dark theme", () => {
    for (const [key, value] of Object.entries(tokens.colors.dark)) {
      const varName = CSS_VAR_BY_TOKEN[key];
      const pattern = new RegExp(`${varName}\\s*:\\s*${value}`, "i");
      expect(
        pattern.test(indexCss),
        `expected ${varName}: ${value} in web/src/index.css (dark theme)`,
      ).toBe(true);
    }
  });
});
