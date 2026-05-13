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

const LOGO_PALETTE = [
  '#6366f1', '#8b5cf6', '#ec4899', '#14b8a6',
  '#f97316', '#0d9488', '#dc2626', '#64748b',
  '#b45309', '#0ea5e9', '#84cc16', '#d97706',
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
      borderRadius: '50%',
      backgroundColor: bg,
      color: '#fff',
      fontSize,
      fontWeight: 700,
      fontFamily: 'var(--font-mono)',
      flexShrink: 0,
      letterSpacing: '-0.02em',
      userSelect: 'none',
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
    borderRadius: '50%',
    objectFit: 'contain',
    flexShrink: 0,
    border: '1px solid rgb(226 232 240)',
    background: '#fff',
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
