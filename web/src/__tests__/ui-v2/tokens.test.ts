import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import tailwindConfig from "../../../tailwind.config";

/**
 * Guard-rail against silent design-token drift.
 *
 * Every color in `docs/design/DealGate_Design_Tokens_v2.1.json` must
 * have a matching entry under `theme.extend.colors` in
 * `tailwind.config.ts` AND a matching CSS custom property in
 * `src/index.css` — for both the light and the dark theme. If a
 * designer adds a token, this fails loudly and the developer must wire
 * it end-to-end.
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
    path.join(REPO_ROOT, "docs/design/DealGate_Design_Tokens_v2.1.json"),
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
  surfaceSunken: "surface-sunken",
  navigation: "navigation",
  text: "text",
  textSecondary: "text-secondary",
  textMuted: "text-muted",
  border: "border",
  borderStrong: "border-strong",
  inputBorder: "input-border",
  primary: "primary",
  primaryHover: "primary.hover",
  primaryText: "primary.text",
  primarySubtle: "primary.subtle",
  onPrimary: "primary.fg",
  plum: "plum",
  plumRaised: "plum.raised",
  plumLine: "plum.line",
  onPlum: "onPlum",
  onPlumSecondary: "onPlumSecondary",
  lime: "lime",
  onLime: "onLime",
  success: "success",
  successSurface: "success.surface",
  warning: "warning",
  warningSurface: "warning.surface",
  danger: "danger",
  dangerSurface: "danger.surface",
  focus: "focus",
  chartSeries1: "chartSeries1",
  chartSeries2: "chartSeries2",
  // Not a color per se — the JSON stores it alongside the palette but it
  // maps onto Tailwind's boxShadow scale, not `colors`. Skip during the
  // color contract check.
  shadowOverlay: "__shadow__",
};

const CSS_VAR_BY_TOKEN: Record<string, string> = {
  canvas: "--dg-canvas",
  surface: "--dg-surface",
  surfaceSunken: "--dg-surface-sunken",
  navigation: "--dg-navigation",
  text: "--dg-text",
  textSecondary: "--dg-text-secondary",
  textMuted: "--dg-text-muted",
  border: "--dg-border",
  borderStrong: "--dg-border-strong",
  inputBorder: "--dg-input-border",
  primary: "--dg-primary",
  primaryHover: "--dg-primary-hover",
  primaryText: "--dg-primary-text",
  primarySubtle: "--dg-primary-subtle",
  onPrimary: "--dg-on-primary",
  plum: "--dg-plum",
  plumRaised: "--dg-plum-raised",
  plumLine: "--dg-plum-line",
  onPlum: "--dg-on-plum",
  onPlumSecondary: "--dg-on-plum-secondary",
  lime: "--dg-lime",
  onLime: "--dg-on-lime",
  success: "--dg-success",
  successSurface: "--dg-success-surface",
  warning: "--dg-warning",
  warningSurface: "--dg-warning-surface",
  danger: "--dg-danger",
  dangerSurface: "--dg-danger-surface",
  focus: "--dg-focus",
  chartSeries1: "--dg-chart-series-1",
  chartSeries2: "--dg-chart-series-2",
  shadowOverlay: "--dg-shadow-overlay",
};

function resolveTailwindPath(
  colors: Record<string, unknown>,
  dotted: string,
): unknown {
  return dotted.split(".").reduce<unknown>((acc, key) => {
    if (acc == null || typeof acc !== "object") return undefined;
    return (acc as Record<string, unknown>)[key];
  }, colors);
}

describe("design tokens v2.1", () => {
  const colors = (tailwindConfig.theme?.extend?.colors ?? {}) as Record<
    string,
    unknown
  >;

  it("declares every light token in the tailwind config", () => {
    for (const key of Object.keys(tokens.colors.light)) {
      const tailwindKey = TAILWIND_KEY_BY_TOKEN[key];
      expect(
        tailwindKey,
        `token '${key}' has no Tailwind mapping in tokens.test.ts`,
      ).toBeTruthy();
      if (tailwindKey === "__shadow__") continue;
      expect(
        resolveTailwindPath(colors, tailwindKey),
        `token '${key}' missing under theme.extend.colors.${tailwindKey}`,
      ).toBeTruthy();
    }
  });

  it("declares every dark token in the tailwind config", () => {
    for (const key of Object.keys(tokens.colors.dark)) {
      const tailwindKey = TAILWIND_KEY_BY_TOKEN[key];
      expect(tailwindKey, `token '${key}' missing tailwind key`).toBeTruthy();
      if (tailwindKey === "__shadow__") continue;
      expect(
        resolveTailwindPath(colors, tailwindKey),
        `token '${key}' missing under theme.extend.colors.${tailwindKey}`,
      ).toBeTruthy();
    }
  });

  it("exposes every token as a CSS variable in index.css for light theme", () => {
    for (const [key, value] of Object.entries(tokens.colors.light)) {
      const varName = CSS_VAR_BY_TOKEN[key];
      expect(varName, `token '${key}' missing CSS var mapping`).toBeTruthy();
      const escapedValue = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = new RegExp(`${varName}\\s*:\\s*${escapedValue}`, "i");
      expect(
        pattern.test(indexCss),
        `expected ${varName}: ${value} in web/src/index.css (light theme)`,
      ).toBe(true);
    }
  });

  it("exposes every token as a CSS variable in index.css for dark theme", () => {
    for (const [key, value] of Object.entries(tokens.colors.dark)) {
      const varName = CSS_VAR_BY_TOKEN[key];
      const escapedValue = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = new RegExp(`${varName}\\s*:\\s*${escapedValue}`, "i");
      expect(
        pattern.test(indexCss),
        `expected ${varName}: ${value} in web/src/index.css (dark theme)`,
      ).toBe(true);
    }
  });

  it("declares the v2.1 layout tokens (sidebar 224, header 56, page 24)", () => {
    const spacing = (tailwindConfig.theme?.extend?.spacing ?? {}) as Record<
      string,
      string
    >;
    expect(spacing.sidebar).toBe("224px");
    expect(spacing.header).toBe("56px");
    expect(spacing["page-x"]).toBe("24px");
    expect(spacing["page-x-mobile"]).toBe("16px");

    const radius = (tailwindConfig.theme?.extend?.borderRadius ?? {}) as Record<
      string,
      string
    >;
    expect(radius.control).toBe("6px");
    expect(radius.chip).toBe("4px");
    expect(radius.card).toBe("12px");
    expect(radius.panel).toBe("16px");
    expect(radius.avatar).toBe("9999px");

    const screens = (tailwindConfig.theme?.screens ?? {}) as Record<
      string,
      unknown
    >;
    expect(screens.sixLaneBoard).toBe("1560px");
    expect(screens.twoColumnCollapse).toBe("1180px");
    expect(screens.mobile).toEqual({ max: "819px" });

    const minH = (tailwindConfig.theme?.extend?.minHeight ?? {}) as Record<
      string,
      string
    >;
    expect(minH["row-comfortable"]).toBe("44px");
    expect(minH["row-compact"]).toBe("36px");
  });

  it("keeps both light and dark theme blocks in index.css", () => {
    expect(/:root,\s*\[data-theme="light"\]\s*\{/.test(indexCss)).toBe(true);
    expect(/\[data-theme="dark"\]\s*\{/.test(indexCss)).toBe(true);
  });
});
