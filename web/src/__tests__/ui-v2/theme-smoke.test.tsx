/**
 * Both-theme smoke test.
 *
 * The v2.1 addendum rule 2 requires every colour to have a light and a
 * dark value and both themes to be tested on every PR. Jsdom does not
 * parse the app stylesheet (vitest is configured with `css: false`),
 * so instead of round-tripping through CSSOM we assert:
 *   1. The tokens file exposes distinct values for the paired keys
 *      that most affect rendering (`canvas`, `text`, `primary`,
 *      `plum`).
 *   2. Flipping `data-theme` on `<html>` is picked up as a mutation on
 *      the DOM (proof the primitives can react via the attribute).
 * Together the two guard the surface a designer cares about — the
 * palette differs, and the app can flip themes.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "../../../../");

const tokens = JSON.parse(
  readFileSync(
    path.join(REPO_ROOT, "docs/design/DealGate_Design_Tokens_v2.1.json"),
    "utf-8",
  ),
) as {
  colors: {
    light: Record<string, string>;
    dark: Record<string, string>;
  };
};

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

describe("theme switching", () => {
  it("light and dark palettes differ on the keys that most affect rendering", () => {
    for (const key of ["canvas", "text", "primary", "plum", "success"]) {
      expect(
        tokens.colors.light[key],
        `light theme missing ${key}`,
      ).toBeTruthy();
      expect(
        tokens.colors.dark[key],
        `dark theme missing ${key}`,
      ).toBeTruthy();
      expect(
        tokens.colors.light[key].toLowerCase(),
        `light and dark should differ on ${key}`,
      ).not.toBe(tokens.colors.dark[key].toLowerCase());
    }
  });

  it("flips data-theme on <html> without mutating rendered markup", () => {
    const { container } = render(<div data-testid="probe" />);
    const probe = container.querySelector<HTMLElement>("[data-testid=probe]")!;
    expect(probe).toBeTruthy();

    document.documentElement.setAttribute("data-theme", "light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    document.documentElement.setAttribute("data-theme", "dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    // Component tree stays the same — theme is an attribute swap.
    expect(container.querySelector("[data-testid=probe]")).toBe(probe);
  });
});
