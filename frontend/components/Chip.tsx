import type { AriaRole, ReactNode } from 'react';

// Outlined-light chip — the QuantRank design system's ONE metadata-indicator
// surface (`.claude/skills/frontend-design-system/SKILL.md` Rule 2). Before
// this primitive existed, the shell + dot + size scale were copy-pasted inline
// across SectorChip / RecommendationBadge / LossChanceBadge / ListingChips /
// Tier2EventCard / …, and the `SIZE_CLASSES` map was duplicated verbatim in two
// of them. The pattern is now a single component (+ the exported `CHIP_BASE` /
// `CHIP_DOT` / `CHIP_SIZES` constants for the few bespoke surfaces that compose
// the shell by hand — ScoreBadge's semibold-numeric pill and SectorChip's
// inline-rgb sector dot, which deviate on font-weight / text-size and so can't
// route through the canonical `size` prop without emitting a conflicting
// utility).
//
// Tone classes are passed through VERBATIM (e.g. `bg-emerald-50 text-emerald-700
// ring-emerald-200 dark:…`) so the `globals.css` soft-OKLCH `!important` override
// (an allowlist keyed on the literal Tailwind utility classes) still applies —
// never pre-resolve a tone to a hex here (Rule 0 / The Tailwind-Class Rule).
// Light + dark pairing lives in the caller's tone string (Rule 4); this
// primitive is tone-agnostic.
//
// Pure presentational component (no hooks, no server-only APIs) so it renders in
// BOTH server callers (SectorChip / RecommendationBadge / ListingChips, used by
// the Server-Component detail page) and client callers (LossChanceBadge /
// Tier2EventCard, which are `'use client'`).

export type ChipSize = 'xs' | 'sm' | 'md' | 'lg';

// Canonical chip size scale (padding + text-size). The single source for the
// scale RecommendationBadge + LossChanceBadge previously duplicated verbatim.
// xs = ultra-tight mobile rows; sm = default; lg = detail-hero badge.
export const CHIP_SIZES: Record<ChipSize, string> = {
  xs: 'px-1.5 py-0 text-[0.625rem]',
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-0.5 text-sm',
  lg: 'px-3 py-1 text-base',
};

// Chip shell — layout + 2px radius + 1px inset ring ONLY. Deliberately omits
// font-weight AND gap so a bespoke caller (ScoreBadge: `font-semibold
// tabular-nums`) can compose it without emitting a conflicting utility; the
// `Chip` component below adds `font-medium` + a conditional `gap-1.5` itself.
export const CHIP_BASE = 'inline-flex items-center rounded-sm ring-1 ring-inset';

// The status-dot / leading-swatch shape shared by every chip (6px round).
export const CHIP_DOT = 'inline-block h-1.5 w-1.5 rounded-full';

export function Chip({
  tone,
  size = 'sm',
  dot,
  leading,
  className = '',
  title,
  role,
  'aria-label': ariaLabel,
  children,
}: {
  /** Outlined-light tone classes, e.g. `bg-emerald-50 text-emerald-700 ring-emerald-200 dark:…`. */
  tone: string;
  size?: ChipSize;
  /** Class-based status dot, e.g. `bg-emerald-500 dark:bg-emerald-400`. Rendered before children. */
  dot?: string;
  /** Leading element (a flag / icon) rendered before children — gets the same gap as a dot. */
  leading?: ReactNode;
  className?: string;
  title?: string;
  role?: AriaRole;
  'aria-label'?: string;
  children: ReactNode;
}) {
  const hasLeading = Boolean(dot || leading);
  return (
    <span
      className={`${CHIP_BASE} font-medium ${hasLeading ? 'gap-1.5 ' : ''}${CHIP_SIZES[size]} ${tone} ${className}`}
      title={title}
      role={role}
      aria-label={ariaLabel}
    >
      {dot && <span className={`${CHIP_DOT} ${dot}`} aria-hidden="true" />}
      {leading}
      {children}
    </span>
  );
}
