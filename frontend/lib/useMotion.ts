'use client';

// Tasteful-motion hooks (2026-05-29). Three small client hooks powering
// the entrance + signature animations. All three respect
// `prefers-reduced-motion` and degrade to the static end-state — never
// gate content visibility on JS, so the page is fully usable if a hook
// no-ops. See docs/design.md §Motion.

import { useEffect, useRef, useState } from 'react';

/** True when the user has asked the OS to reduce motion. SSR-safe
 *  (returns false during prerender; updates on mount). */
function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Count a number up from 0 → `target` over `durationMs`, but only after
 * `start` flips true (wire it to usePlayOnMount so the count runs on each
 * visit). Returns the live
 * value to render. Under reduced-motion (or when start is false) it
 * returns the target immediately — the number is always correct, the
 * animation is the only thing gated.
 *
 * Uses requestAnimationFrame with an ease-out curve so the tail decelerates
 * into the final value (matches the gauge-arc easing). Cancels cleanly on
 * unmount or if the target changes mid-flight.
 */
export function useCountUp(
  target: number,
  start: boolean,
  durationMs = 800,
): number {
  // Initialize at the TARGET so SSR / pre-hydration / no-JS / reduced-
  // motion all render the correct number. The count-up is a progressive
  // enhancement: only when `start` flips true (and motion is allowed) do
  // we reset to 0 and animate up. This guarantees the prerendered static
  // HTML never shows a wrong "0.0".
  const [value, setValue] = useState(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!start || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    const from = 0;
    const delta = target - from;
    setValue(from); // dip to 0, then animate up (client-only, first view)
    const t0 = performance.now();
    // easeOutCubic — fast out of the gate, calm settle into the value.
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);

    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / durationMs);
      setValue(from + delta * ease(p));
      if (p < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(target); // pin the exact target (no float drift)
      }
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, start, durationMs]);

  return value;
}

/**
 * Returns true after mount on EVERY visit (each page navigation / load),
 * so entrance animations replay every time the user arrives at a surface —
 * not just once per session. (Renamed from the earlier `usePlayedOnce`
 * once-per-session gate per the 2026-05-29 "play every time" direction.)
 *
 * Two invariants are preserved from the session-gated version:
 *  • Reduced-motion: returns false → no consumer adds an animate class and
 *    no JS cycle fires (Rule 3 holds end-to-end, not just visually).
 *  • Client-only: returns false on SSR + first paint, flips true one frame
 *    after mount — so the animate class is NEVER in the static prerender
 *    (Rule 5: baking it in would hydration-mismatch + double-play). The
 *    one-frame delay is imperceptible and flicker-free (the entrance starts
 *    from opacity 0 / empty arc, which is the natural "not yet arrived"
 *    state).
 *
 * The `key` argument is kept for call-site clarity / future per-key logic
 * but no longer gates anything (every mount animates).
 */
export function usePlayOnMount(_key?: string): boolean {
  const [play, setPlay] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setPlay(false);
      return;
    }
    setPlay(true);
  }, []);

  return play;
}
