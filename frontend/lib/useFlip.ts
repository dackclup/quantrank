'use client';

import { useEffect, useLayoutEffect, useRef } from 'react';

// useLayoutEffect warns during SSR; the Next static export pre-renders client
// components at build time. Fall back to useEffect on the server (the effect is
// a no-op there anyway — no DOM to measure).
const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

// FLIP (First · Last · Invert · Play) for a reorderable list/table, FILTER-SCOPED
// ($impeccable overdrive). Any child carrying a `data-flip-key` that PERSISTED
// across a change (same key, moved position) animates from its old position to
// its new one via the Web Animations API — but ONLY when the change is a
// search / filter change (`filterKey`), NOT a column-sort or page change.
//
// Why filter-scoped (verified in-browser): on a paginated 502-row table a SORT
// turns over the entire visible page — the rows that would make the compelling
// slide are on other, unrendered pages — so a sort-triggered FLIP fires on <5%
// of rows and reads as broken (some slide, most snap). A FILTER change instead
// keeps the surviving rows in the DOM and slides them as the field narrows;
// partial animation there is SEMANTICALLY CORRECT (filtering inherently adds /
// removes rows), so it reads as "the field responded," not broken. This also
// satisfies the product-register rule "motion conveys state, not decoration":
// the reshuffle IS the visible answer to the filter the user just changed.
//
// Mechanics:
//  • `orderKey` (visible tickers in order) re-runs the effect on ANY order
//    change so positions stay measured; `filterKey` is what GATES the play.
//  • On a sort / page change the effect re-measures + stores positions silently
//    (no animation) so the next filter change has a correct baseline.
//  • transform-only (translateY) + `cubic-bezier(0.4,0,0.2,1)` (app ease-in-out),
//    300ms; reduced-motion → no animation; first render / entering rows → none.
//  • Zero-height rects are skipped, so the off-screen layout (desktop table on
//    mobile, or vice-versa) is a no-op — each call animates only its visible list.
//  • The visual overlap / gap between rows DURING the slide is intentional FLIP
//    behaviour — the vacated slot keeps its `space-y` margin while the row
//    translates from its old position. Do NOT "fix" it with `position:absolute`
//    or `will-change`; that breaks the layout. It settles cleanly at the end.
//  • WAAPI `fill` is left default ('none') ON PURPOSE: the row's DOM position IS
//    the authoritative end state, so the transform releases to `translateY(0)`
//    via layout, not a frozen fill. If you ever add an opacity fade ALONGSIDE the
//    translateY (e.g. for entering rows), that property would need `fill:'forwards'`.
export function useFlip<T extends HTMLElement = HTMLElement>(orderKey: string, filterKey: string) {
  const ref = useRef<T | null>(null);
  const prevPos = useRef<Map<string, number>>(new Map());
  const prevFilterKey = useRef(filterKey);

  useIsomorphicLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const play = prevFilterKey.current !== filterKey; // animate ONLY on a filter change
    prevFilterKey.current = filterKey;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const containerTop = el.getBoundingClientRect().top;
    const next = new Map<string, number>();
    el.querySelectorAll<HTMLElement>('[data-flip-key]').forEach((node) => {
      const key = node.dataset.flipKey;
      if (key == null) return;
      const rect = node.getBoundingClientRect();
      if (rect.height === 0) return; // hidden container at this viewport
      const top = rect.top - containerTop;
      next.set(key, top);
      if (!play || reduce) return;
      const old = prevPos.current.get(key);
      if (old != null && Math.abs(old - top) > 0.5) {
        // CSS transitions on the node (.hover-lift / .press) are overridden by
        // this WAAPI play for its 300ms — acceptable: the lift is 1px and the
        // beat is short; hover/press resume the instant it releases.
        node.animate(
          [{ transform: `translateY(${old - top}px)` }, { transform: 'translateY(0)' }],
          { duration: 300, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' },
        );
      }
    });
    prevPos.current = next;
  }, [orderKey, filterKey]);

  return ref;
}
