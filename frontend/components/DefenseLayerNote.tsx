import { TriangleAlert } from 'lucide-react';

// Standing defense-layer caution callout — the honest-voice disclaimer the
// QuantRank design handoff renders below the forensic-screen card. It is
// DELIBERATELY a standing element, not gated on whether a stock fired a flag:
// the defense layer screens EVERY ranked stock, so the "flags mark elevated
// risk, never confirmed fraud" framing is true on a clean stock too (it tells
// the reader why an absence of flags is also a calibrated statement, not a
// guarantee). It therefore renders on every detail page, framing the whole
// scoring methodology rather than a single stock's risk zone.
//
// Brand idiom: amber soft band (caution, never alarm-red), a SINGLE 1px
// border + 4px radius (borders carry depth — no shadow, and no redundant
// inset ring doubling the same amber outline; this matches the page's own
// detail-pending amber fallback and the handoff Card, which border only),
// TriangleAlert lucide glyph at strokeWidth 1.75 (a hair lighter than the
// 1px chrome so it reads as content), paired light + dark variants. Copy is
// verbatim honest-voice register — it
// states the model's own limits (decay after publication, stated error rates)
// and never claims certainty. Covered by the global Disclaimer banner, so no
// per-element legal popover (design-system Rule 9).
//
// Pure presentational server component (no hooks, no client-only APIs) so the
// Server-Component detail page renders it without a 'use client' boundary.
export function DefenseLayerNote() {
  return (
    <section
      aria-label="Defense layer caution"
      className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/30"
    >
      <span className="text-amber-700 dark:text-amber-300" aria-hidden="true">
        <TriangleAlert className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
      </span>
      <p className="text-[0.8125rem] leading-relaxed text-amber-900 dark:text-amber-200">
        <span className="font-semibold">Defense layer.</span> Flags mark{' '}
        <em>elevated risk</em>, never confirmed fraud. This model cannot catch
        every manipulation and decays after publication — weigh it against its
        stated error rates.
      </p>
    </section>
  );
}
