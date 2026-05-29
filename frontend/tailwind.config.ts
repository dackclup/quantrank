import type { Config } from 'tailwindcss';

const config: Config = {
  // LedgerCraft Phase 3b — class-strategy dark mode. `<html>` gains
  // a `dark` class when the user toggles via next-themes; all `dark:`
  // utility variants then activate. Class strategy chosen over `media`
  // so the user's explicit choice (light / dark / system) overrides
  // the OS preference.
  darkMode: 'class',
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
      // PR 3 animation polish (post-LedgerCraft) — skeleton shimmer for
      // async-loading data placeholders + fade-in for image / fallback
      // mount. Keyframe declarations live in `app/globals.css` so the
      // `.animate-shimmer` background gradient + dark-variant + reduced-
      // motion guard can co-locate with the keyframe. Tailwind registers
      // the utility class names here. Durations match the LedgerCraft
      // ≤ 200ms budget for functional transitions; shimmer runs at 1.5s
      // (loading-state convention — fast enough to feel "loading", slow
      // enough to be calming).
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        // Tasteful-motion vocabulary (2026-05-29). All transform/opacity
        // only — never width/height/top/left — so the GPU compositor
        // handles them and no layout reflow occurs. Every utility below
        // has a `prefers-reduced-motion` off-switch in globals.css that
        // snaps to the end state. LedgerCraft stays flat; motion is the
        // ENTRANCE, not a permanent visual flourish (plays once per
        // session via the usePlayedOnce hook). See docs/design.md §Motion.
        //
        // rise-in — the workhorse entrance: fade + 8px upward settle.
        // Used by cards, table rows (staggered), risk/flag list items.
        'rise-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        // chip-pop — recommendation / score-tier / sector chips land with
        // a tiny overshoot so the verdict feels "stamped on", not faded.
        'chip-pop': {
          '0%': { opacity: '0', transform: 'scale(0.85)' },
          '70%': { opacity: '1', transform: 'scale(1.04)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        // flag-pulse — risk-veto rows draw one slow attention pulse on
        // entrance (ring opacity), then rest. Communicates "look here"
        // without a permanent blink. Single iteration only.
        'flag-pulse': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '60%': { opacity: '1', transform: 'translateY(0)' },
          '78%': { boxShadow: '0 0 0 3px rgb(244 63 94 / 0.18)' },
          '100%': { boxShadow: '0 0 0 0 rgb(244 63 94 / 0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s linear infinite',
        'fade-in': 'fade-in 200ms ease-out',
        // Functional micro-entrances — within the LedgerCraft ≤ 200ms
        // budget for the fast ones; the gauge/signature sweep (≤ 800ms)
        // is driven by a CSS transition on stroke-dashoffset in the
        // component, not a keyframe, so it can ease from the live value.
        'rise-in': 'rise-in 320ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'chip-pop': 'chip-pop 260ms cubic-bezier(0.34, 1.56, 0.64, 1) both',
        'flag-pulse': 'flag-pulse 900ms ease-out both',
      },
    },
  },
  plugins: [],
};

export default config;
