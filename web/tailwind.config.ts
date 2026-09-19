import type { Config } from "tailwindcss";

/**
 * Tailwind configuration for DealGate V2 design system.
 *
 * Colours are declared as CSS custom properties in `src/index.css` (one set
 * for light, one under `[data-theme="dark"]`). Tailwind references them via
 * `var(--token)` so `bg-primary`, `text-danger`, etc. resolve to the right
 * theme without a build-time swap.
 *
 * Every token here mirrors `docs/design/DealGate_Design_Tokens.json`. If you
 * add or remove one, update the JSON too — `tokens.test.ts` will fail if
 * they drift.
 */
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--dg-canvas)",
        surface: "var(--dg-surface)",
        navigation: "var(--dg-navigation)",
        text: "var(--dg-text)",
        "text-secondary": "var(--dg-text-secondary)",
        divider: "var(--dg-divider)",
        "input-border": "var(--dg-input-border)",
        primary: {
          DEFAULT: "var(--dg-primary)",
          fg: "var(--dg-on-primary)",
          subtle: "var(--dg-primary-subtle)",
        },
        success: {
          DEFAULT: "var(--dg-success)",
          surface: "var(--dg-success-surface)",
        },
        warning: {
          DEFAULT: "var(--dg-warning)",
          surface: "var(--dg-warning-surface)",
        },
        danger: {
          DEFAULT: "var(--dg-danger)",
          surface: "var(--dg-danger-surface)",
        },
        focus: "var(--dg-focus)",
        executive: {
          DEFAULT: "var(--dg-executive-banner)",
          fg: "var(--dg-executive-text)",
          muted: "var(--dg-executive-secondary)",
        },
        hero: {
          DEFAULT: "var(--dg-hero-action)",
          fg: "var(--dg-hero-action-text)",
        },
      },
      spacing: {
        "1": "4px",
        "2": "8px",
        "3": "12px",
        "4": "16px",
        "6": "24px",
        "8": "32px",
        "12": "48px",
        sidebar: "194px",
        "sidebar-collapsed": "64px",
        header: "70px",
        "page-x": "28px",
      },
      borderRadius: {
        control: "9px",
        panel: "16px",
        dialog: "18px",
        hero: "20px",
      },
      fontFamily: {
        sans: [
          "'Inter Variable'",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      fontSize: {
        body: ["14px", { lineHeight: "22px", fontWeight: "400" }],
        secondary: ["12px", { lineHeight: "18px", fontWeight: "400" }],
        section: ["16px", { lineHeight: "24px", fontWeight: "600" }],
        page: ["32px", { lineHeight: "38px", fontWeight: "600" }],
        "page-mobile": ["28px", { lineHeight: "34px", fontWeight: "600" }],
        metric: ["30px", { lineHeight: "36px", fontWeight: "600" }],
      },
      boxShadow: {
        menu: "0 6px 24px rgba(20, 18, 30, 0.10)",
        dialog: "0 24px 60px rgba(20, 18, 30, 0.28)",
      },
      transitionDuration: {
        motion: "150ms",
      },
      minHeight: {
        control: "40px",
        "row-comfortable": "52px",
        "row-compact": "40px",
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
      });
    },
  ],
};

export default config;
