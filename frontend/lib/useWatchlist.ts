'use client';

import { useCallback, useEffect, useState } from 'react';

// Browser-local watchlist — an ordered list of tickers persisted to
// localStorage. The feature lives entirely in the browser: no account, no
// backend, nothing leaves the device (see /portfolio). Mirrors the
// `next-themes` / ThemeToggle `mounted` guard so SSR + the first client render
// are deterministic (empty) and the real saved set is read only AFTER
// hydration — otherwise the star-fill state would hydration-mismatch.
//
// Cross-tab sync: the native `storage` event keeps other tabs in step. It does
// NOT fire in the tab that made the change, so same-tab writes also dispatch a
// custom event that this hook listens to — every WatchlistButton on the page
// reflects a toggle immediately.

const STORAGE_KEY = 'quantrank:watchlist';
const UPDATE_EVENT = 'quantrank:watchlist-change';

function readStorage(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Defensive: de-dupe + drop any non-string / empty entries a hand-edited
    // localStorage value might contain.
    return Array.from(
      new Set(parsed.filter((t): t is string => typeof t === 'string' && t.length > 0)),
    );
  } catch {
    return [];
  }
}

function writeStorage(tickers: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tickers));
    // Native `storage` only fires in OTHER tabs — broadcast same-tab too.
    window.dispatchEvent(new Event(UPDATE_EVENT));
  } catch {
    /* quota exceeded / storage disabled (private mode) — degrade silently;
       the in-memory state still updates for this session. */
  }
}

export interface UseWatchlist {
  /** Saved tickers, newest-first (insertion order). Empty until `mounted`. */
  tickers: string[];
  /** True once the post-hydration localStorage read has run. */
  mounted: boolean;
  isSaved: (ticker: string) => boolean;
  /** Add if absent, remove if present. */
  toggle: (ticker: string) => void;
  remove: (ticker: string) => void;
  clear: () => void;
}

export function useWatchlist(): UseWatchlist {
  const [tickers, setTickers] = useState<string[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTickers(readStorage());

    const sync = () => setTickers(readStorage());
    window.addEventListener('storage', sync); // cross-tab
    window.addEventListener(UPDATE_EVENT, sync); // same-tab
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(UPDATE_EVENT, sync);
    };
  }, []);

  const toggle = useCallback((ticker: string) => {
    setTickers((prev) => {
      const next = prev.includes(ticker)
        ? prev.filter((t) => t !== ticker)
        : [ticker, ...prev];
      writeStorage(next);
      return next;
    });
  }, []);

  const remove = useCallback((ticker: string) => {
    setTickers((prev) => {
      if (!prev.includes(ticker)) return prev;
      const next = prev.filter((t) => t !== ticker);
      writeStorage(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setTickers([]);
    writeStorage([]);
  }, []);

  const isSaved = useCallback((ticker: string) => tickers.includes(ticker), [tickers]);

  return { tickers, mounted, isSaved, toggle, remove, clear };
}
