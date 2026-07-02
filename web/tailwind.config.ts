import type { Config } from "tailwindcss";

// Tokens mirror docs/redesign_guide design system + dashboard-visual-v2.
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
          danger:  "var(--color-tone-danger)",
          warning: "var(--color-tone-warning)",
          success: "var(--color-tone-success)",
          neutral: "var(--color-tone-neutral)",
        },
        ink: {
          DEFAULT: "var(--color-ink)",
          soft:    "var(--color-ink-soft)",
          faint:   "var(--color-ink-faint)",
        },
        surface: {
          DEFAULT: "var(--color-surface)",
          muted:   "var(--color-surface-muted)",
          border:  "var(--color-surface-border)",
        },
        accent: {
          DEFAULT:    "var(--color-accent)",
          foreground: "var(--color-accent-foreground)",
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
