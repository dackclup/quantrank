import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      // LedgerCraft adoption (2026-05-22) — `font-slab` Tailwind class
      // maps to the Roboto Slab face loaded by globals.css. Use on
      // headline surfaces (h1/h2 in RankingTable / per-stock detail
      // pages / layout wordmark) for the "editorial finance" feel.
      fontFamily: {
        slab: ['var(--font-slab)', 'Roboto Slab', 'ui-serif', 'Georgia', 'serif'],
      },
      // LedgerCraft adoption — formal 4-tier elevation system. The
      // Subtle / Medium / Large / Overlay names mirror LedgerCraft's
      // documented elevation tokens so future component polish can
      // reach for `shadow-subtle` / `shadow-medium` / `shadow-large`
      // / `shadow-overlay` instead of ad-hoc `shadow-sm` / `shadow`
      // pairs. Values calibrated for a slate-on-white palette with
      // gentle vertical depth (no aggressive darkness).
      boxShadow: {
        // Hairline lift — table-row hover, badge surface.
        subtle: '0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 1px -1px rgb(15 23 42 / 0.02)',
        // Card resting state — RankingTable container, KPI grid cell.
        medium: '0 1px 3px 0 rgb(15 23 42 / 0.06), 0 1px 2px -1px rgb(15 23 42 / 0.04)',
        // Section emphasis — per-stock hero card, fair-price chart panel.
        large: '0 4px 8px -2px rgb(15 23 42 / 0.08), 0 2px 4px -2px rgb(15 23 42 / 0.04)',
        // Modal / drawer / dropdown — FilterDrawer, sort-menu popover.
        overlay: '0 12px 24px -6px rgb(15 23 42 / 0.12), 0 4px 8px -4px rgb(15 23 42 / 0.06)',
      },
    },
  },
  plugins: [],
};

export default config;
