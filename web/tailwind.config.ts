import type { Config } from "tailwindcss";

/**
 * Tailwind configuration for DealGate V2.1 design system.
 *
 * Colours are declared as CSS custom properties in `src/index.css` (one set
 * for light, one under `[data-theme="dark"]`). Tailwind references them via
 * `var(--token)` so `bg-primary`, `text-danger`, etc. resolve to the right
 * theme without a build-time swap.
 *
 * Every token here mirrors `docs/design/DealGate_Design_Tokens_v2.1.json`.
 * If you add or remove one, update the JSON too — `tokens.test.ts` will
 * fail if they drift.
 *
 * Colour rules (see the tokens JSON `colorRules` array):
 *   1. `primary` is the only accent — main button, selected nav, links,
 *      in-progress state, focus ring.
 *   2. `lime` appears only inside the plum banner as the single hero action.
 *   3. `plum` is the executive banner / toast / tooltip surface. Never a
 *      page or card background.
 *   4. `success` / `warning` / `danger` are semantic, never decorative.
 *   5. Chart series is `chartSeries1` + `chartSeries2` in fixed order; a
 *      floor line is text-colored, never a third series colour.
 */
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    screens: {
      // The v2.1 breakpoints. Standard Tailwind sm/md/lg/xl/2xl are kept
      // as convenience aliases mapped near the spec values.
      sm: "640px",
      md: "820px",
      lg: "1024px",
      xl: "1180px",
      "2xl": "1560px",
      mobile: { max: "819px" },
      twoColumnCollapse: "1180px",
      sixLaneBoard: "1560px",
    },
    extend: {
      colors: {
        // Surfaces
        canvas: "var(--dg-canvas)",
        surface: "var(--dg-surface)",
        "surface-sunken": "var(--dg-surface-sunken)",
        surfaceSunken: "var(--dg-surface-sunken)",
        navigation: "var(--dg-navigation)",
        // Text
        text: "var(--dg-text)",
        "text-secondary": "var(--dg-text-secondary)",
        textSecondary: "var(--dg-text-secondary)",
        "text-muted": "var(--dg-text-muted)",
        textMuted: "var(--dg-text-muted)",
        // Borders — `divider` kept as alias for legacy classes.
        border: "var(--dg-border)",
        divider: "var(--dg-border)",
        "border-strong": "var(--dg-border-strong)",
        borderStrong: "var(--dg-border-strong)",
        "input-border": "var(--dg-input-border)",
        inputBorder: "var(--dg-input-border)",
        // Primary accent (the only accent)
        primary: {
          DEFAULT: "var(--dg-primary)",
          hover: "var(--dg-primary-hover)",
          text: "var(--dg-primary-text)",
          fg: "var(--dg-on-primary)",
          subtle: "var(--dg-primary-subtle)",
        },
        primaryHover: "var(--dg-primary-hover)",
        primaryText: "var(--dg-primary-text)",
        primarySubtle: "var(--dg-primary-subtle)",
        onPrimary: "var(--dg-on-primary)",
        // Plum executive surface. `executive` kept as an alias so pages
        // that used the v2.0 name keep rendering.
        plum: {
          DEFAULT: "var(--dg-plum)",
          raised: "var(--dg-plum-raised)",
          line: "var(--dg-plum-line)",
        },
        plumRaised: "var(--dg-plum-raised)",
        plumLine: "var(--dg-plum-line)",
        onPlum: "var(--dg-on-plum)",
        onPlumSecondary: "var(--dg-on-plum-secondary)",
        executive: {
          DEFAULT: "var(--dg-plum)",
          fg: "var(--dg-on-plum)",
          muted: "var(--dg-on-plum-secondary)",
        },
        // Lime hero (banner only)
        lime: {
          DEFAULT: "var(--dg-lime)",
        },
        onLime: "var(--dg-on-lime)",
        hero: {
          DEFAULT: "var(--dg-lime)",
          fg: "var(--dg-on-lime)",
        },
        // Semantic states
        success: {
          DEFAULT: "var(--dg-success)",
          surface: "var(--dg-success-surface)",
        },
        successSurface: "var(--dg-success-surface)",
        warning: {
          DEFAULT: "var(--dg-warning)",
          surface: "var(--dg-warning-surface)",
        },
        warningSurface: "var(--dg-warning-surface)",
        danger: {
          DEFAULT: "var(--dg-danger)",
          surface: "var(--dg-danger-surface)",
        },
        dangerSurface: "var(--dg-danger-surface)",
        focus: "var(--dg-focus)",
        // Charts
        chartSeries1: "var(--dg-chart-series-1)",
        chartSeries2: "var(--dg-chart-series-2)",
      },
      spacing: {
        "1": "4px",
        "2": "8px",
        "3": "12px",
        "4": "16px",
        "5": "20px",
        "6": "24px",
        "8": "32px",
        "12": "48px",
        sidebar: "224px",
        "sidebar-collapsed": "64px",
        header: "56px",
        "page-x": "24px",
        "page-x-mobile": "16px",
      },
      borderRadius: {
        control: "6px",
        chip: "4px",
        card: "12px",
        panel: "16px",
        hero: "16px",
        dialog: "16px",
        avatar: "9999px",
      },
      fontFamily: {
        sans: [
          "'Inter Variable'",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "'Segoe UI'",
          "sans-serif",
        ],
        display: [
          "Fraunces",
          "'Iowan Old Style'",
          "Georgia",
          "serif",
        ],
      },
      fontSize: {
        // Names line up with `tokens.typography.scale.*` in the JSON.
        bannerHeadline: [
          "40px",
          { lineHeight: "1.05", fontWeight: "500", letterSpacing: "-0.015em" },
        ],
        pageHeading: [
          "28px",
          { lineHeight: "1.15", fontWeight: "500" },
        ],
        metric: [
          "26px",
          { lineHeight: "1.1", fontWeight: "600", letterSpacing: "-0.02em" },
        ],
        section: [
          "15px",
          { lineHeight: "1.4", fontWeight: "600" },
        ],
        body: [
          "14px",
          { lineHeight: "1.45", fontWeight: "400" },
        ],
        table: [
          "13px",
          { lineHeight: "1.4", fontWeight: "400" },
        ],
        secondary: [
          "12px",
          { lineHeight: "1.5", fontWeight: "400" },
        ],
        label: [
          "11px",
          { lineHeight: "1.45", fontWeight: "600", letterSpacing: "0.06em" },
        ],
        // Kept for legacy page classes; both point at the same size the
        // v2.1 scale allows.
        page: [
          "28px",
          { lineHeight: "1.15", fontWeight: "500" },
        ],
        "page-mobile": [
          "28px",
          { lineHeight: "1.15", fontWeight: "500" },
        ],
      },
      boxShadow: {
        // Cards use borders only — shadows float.
        overlay: "0 8px 24px rgba(31,27,46,0.12)",
        menu: "0 8px 24px rgba(31,27,46,0.12)",
        dialog: "0 8px 24px rgba(31,27,46,0.12)",
      },
      transitionDuration: {
        motion: "150ms",
      },
      minHeight: {
        control: "36px",
        "control-compact": "30px",
        touch: "44px",
        "row-comfortable": "44px",
        "row-compact": "36px",
        "table-header": "36px",
      },
      height: {
        header: "56px",
      },
    },
  },
  plugins: [
    function tabularNums({
      addUtilities,
    }: {
      addUtilities: (utils: Record<string, Record<string, string>>) => void;
    }) {
      addUtilities({
        ".tnum": {
          "font-feature-settings": '"tnum" on, "cv11" on',
          "font-variant-numeric": "tabular-nums",
        },
        ".dg-tnum": {
          "font-feature-settings": '"tnum" on, "cv11" on',
          "font-variant-numeric": "tabular-nums",
        },
        ".font-display": {
          "font-family":
            "Fraunces, 'Iowan Old Style', Georgia, serif",
        },
      });
    },
  ],
};

export default config;
