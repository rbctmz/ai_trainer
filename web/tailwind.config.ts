import type { Config } from "tailwindcss";

// Tokens mirror docs/redesign_guide design system + dashboard-visual-v2.
//
// Colors are wrapped in rgb(var(...) / <alpha-value>) — Tailwind's documented
// pattern for CSS-variable-based colors that must support opacity modifiers
// (bg-tone-neutral/80 etc). The variables themselves (globals.css) must be
// space-separated "R G B" triplets, not hex strings, or this breaks silently
// (invalid CSS, background renders fully transparent).
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        tone: {
          danger:  "rgb(var(--color-tone-danger) / <alpha-value>)",
          warning: "rgb(var(--color-tone-warning) / <alpha-value>)",
          success: "rgb(var(--color-tone-success) / <alpha-value>)",
          neutral: "rgb(var(--color-tone-neutral) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          soft:    "rgb(var(--color-ink-soft) / <alpha-value>)",
          faint:   "rgb(var(--color-ink-faint) / <alpha-value>)",
        },
        surface: {
          DEFAULT: "rgb(var(--color-surface) / <alpha-value>)",
          muted:   "rgb(var(--color-surface-muted) / <alpha-value>)",
          border:  "rgb(var(--color-surface-border) / <alpha-value>)",
        },
        accent: {
          DEFAULT:    "rgb(var(--color-accent) / <alpha-value>)",
          foreground: "rgb(var(--color-accent-foreground) / <alpha-value>)",
        },
      },
      borderRadius: {
        card: "16px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
