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
 * `start` flips true (wire it to useInViewOnce so the count runs when the
 * element is first seen, not at mount-while-offscreen). Returns the live
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
 * Returns true the FIRST time a given `key` is seen this browser session,
 * false on every subsequent mount (sessionStorage-backed).
 *
 * Effect-based: returns false on SSR + first paint, then flips true after
 * mount if this is the first time the key is seen this session. Used for
 * BOTH the JS-driven gauge/count-up AND the CSS row-stagger — in all cases
 * the animate class/value must be ADDED client-side (never baked into the
 * static prerender), otherwise a static export would replay the animation
 * on every full page load and hydration-mismatch against the client gate.
 * The one-frame delay before animating is imperceptible and flicker-free.
 *
 * SSR-safe + degrades to "always play" (true) if sessionStorage is
 * unavailable — a harmless extra play beats a swallowed one.
 */
export function usePlayedOnce(key: string): boolean {
  const [firstTime, setFirstTime] = useState(false);

  useEffect(() => {
    // Reduced-motion: never report "first time" → no consumer adds an
    // animate class, no double-rAF cycle fires. The CSS guard already
    // neutralizes the visual, but this stops the JS-side cycle too so
    // Rule 3 holds end-to-end (not just visually). Don't even write the
    // sessionStorage key — a later non-reduced-motion session in the same
    // tab is vanishingly rare and a harmless extra play beats suppressing
    // a wanted one.
    if (prefersReducedMotion()) {
      setFirstTime(false);
      return;
    }
    try {
      const k = `qr-motion:${key}`;
      if (sessionStorage.getItem(k)) {
        setFirstTime(false);
      } else {
        sessionStorage.setItem(k, '1');
        setFirstTime(true);
      }
    } catch {
      setFirstTime(true); // storage blocked — let it play
    }
  }, [key]);

  return firstTime;
}
