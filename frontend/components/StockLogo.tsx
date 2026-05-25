'use client';

import type { CSSProperties, JSX } from 'react';
import { useState } from 'react';

// Per-stock logo from the design canvas handoff (chat2.md, 2026-05-13).
// Loads SVG from Parqet's public symbol service; on error falls back to
// a deterministic colored circle with the ticker's first character.
//
// Parqet is a free public source; we don't need auth or rate-limit
// handling — failures (404, network, CSP) just trip the onError →
// letter-avatar fallback. No PII flows in either direction (logo URL
// only contains the ticker symbol, which is public market data).

// 12-color avatar fallback palette built from the four-family design
// system (slate / indigo / rose / amber) using the 500/600/700 shade
// triplet per family. Keeps deterministic distinct-color hashing for
// ticker avatars while staying within the design-token discipline
// (`.claude/skills/frontend-design-system/SKILL.md` Rule 0). Pre-2026-05-21
// the palette included violet/pink/teal/orange/sky/lime/red entries
// outside the four-family — flagged by `frontend-design-reviewer`
// and remapped here.
const LOGO_PALETTE = [
  '#6366f1', // indigo-500
  '#4f46e5', // indigo-600
  '#4338ca', // indigo-700
  '#f43f5e', // rose-500
  '#e11d48', // rose-600
  '#be123c', // rose-700
  '#f59e0b', // amber-500
  '#d97706', // amber-600
  '#b45309', // amber-700
  '#64748b', // slate-500
  '#475569', // slate-600
  '#334155', // slate-700
];

function tickerColor(ticker: string): string {
  const code = ticker
    .split('')
    .reduce((a: number, c: string) => a + c.charCodeAt(0), 0);
  return LOGO_PALETTE[code % LOGO_PALETTE.length];
}

export function StockLogo({
  ticker,
  size = 20,
}: {
  ticker: string;
  size?: number;
}): JSX.Element {
  const [failed, setFailed] = useState(false);
  const bg = tickerColor(ticker);
  const fontSize = Math.round(size * 0.42);

  if (failed) {
    const fallbackStyle: CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: size,
      height: size,
      borderRadius: '4px',
      backgroundColor: bg,
      color: 'white',
      fontSize,
      fontWeight: 700,
      fontFamily: 'var(--font-mono)',
      flexShrink: 0,
      letterSpacing: '-0.02em',
      userSelect: 'none',
      // Fade-in on mount — smooths the fallback transition when the
      // Parqet img errors and the letter-avatar swaps in.
      animation: 'fade-in 200ms ease-out',
    };
    return (
      <span aria-hidden="true" style={fallbackStyle}>
        {ticker.charAt(0)}
      </span>
    );
  }

  const imgStyle: CSSProperties = {
    width: size,
    height: size,
    borderRadius: '4px',
    objectFit: 'contain',
    flexShrink: 0,
    border: '1px solid rgb(226 232 240)',
    background: 'white',
    // Fade-in on mount — smooths the logo reveal when the Parqet
    // SVG loads (typical case: cached, < 50ms). The 200ms easing
    // matches the LedgerCraft animation budget; reduced-motion
    // guard in globals.css disables the animation entirely.
    animation: 'fade-in 200ms ease-out',
  };
  return (
    <img
      src={`https://assets.parqet.com/logos/symbol/${ticker}?format=svg`}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      style={imgStyle}
      onError={() => setFailed(true)}
    />
  );
}
