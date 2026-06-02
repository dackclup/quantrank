'use client';

import { useCountUp, usePlayOnMount } from '@/lib/useMotion';

// Hero metric value with a count-up entrance (Fair value / Target / Loss
// chance in the stock-detail hero). Added 2026-05-31 per user request
// ("เพิ่ม animation ตัวเลขวิ่งให้ fair value target loss chance แบบ ease in
// and out"). The number eases 0 → value on each visit via `useCountUp`
// (easeInOutCubic — the app-wide motion curve, shared with the Score / MoS
// gauge sweep). Reduced-motion / SSR / no-JS all render the exact value
// immediately — the count-up is a progressive enhancement, never a
// visibility gate.
//
// `page.tsx` is a Server Component, so the hook call lives here in a small
// client leaf instead of converting the whole page. The label + the h-6
// value box + tabular-nums + tone are kept identical to the prior inline
// markup so the layout is pixel-stable; only the number animates.

type Format = 'price' | 'percent';

function formatValue(v: number, format: Format): string {
  if (format === 'percent') return `${Math.round(v)}%`;
  return v.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  });
}

export function HeroMetric({
  label,
  value,
  format,
  tone = 'text-slate-900 dark:text-slate-100',
  caption = null,
}: {
  label: string;
  // null → render an em-dash placeholder (no animation, nothing to count to).
  value: number | null;
  format: Format;
  // Tailwind text-color classes for the value (Loss chance passes a
  // band-driven tone; the price metrics use the default ink).
  tone?: string;
  // Optional plain-English band word under the value (Loss chance shows
  // "Neutral" / "Moderate-high" / … so a bare "55%" isn't ambiguous —
  // matches the mobile ranking card's dot + word treatment). Server-computed
  // and STATIC — it does not animate with the count-up. null on the price
  // metrics (Fair value / Target carry no band).
  caption?: { label: string; dot: string } | null;
}) {
  // Plays on every detail visit; reduced-motion → false (static value).
  const play = usePlayOnMount(`hero-metric:${label}`);
  // Hooks must run unconditionally, so always call useCountUp — fall back to
  // 0 as the target when the value is null (the null branch below renders the
  // em-dash and never reads `shown`).
  // 300ms (within the design.md ≤320ms micro budget) — deliberately NOT 800ms.
  // $impeccable quieter (2026-06-02): the secondary hero metrics settle fast so
  // the 800ms Score-gauge sweep stays the page's SINGLE >320ms signature. The
  // prior 800ms here made the score gauge + MoS gauge + all three of these
  // count-ups race at 800ms on every detail load — the "orchestrated page-load
  // sequence" the product register warns against. Do NOT bump back to 800 to
  // "match the gauge"; the gauge being the lone long beat is the point.
  const shown = useCountUp(value ?? 0, play && value != null, 300);

  return (
    <div className="flex flex-col items-center gap-1 text-center">
      <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {label}
      </span>
      {value == null ? (
        <span className="flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none text-slate-300 dark:text-slate-600">
          —
        </span>
      ) : (
        <span
          className={`flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none ${tone}`}
        >
          {formatValue(shown, format)}
        </span>
      )}
      {value != null && caption && (
        <span className="inline-flex items-center gap-1 text-[0.6875rem] text-slate-500 dark:text-slate-400">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${caption.dot}`}
            aria-hidden="true"
          />
          {caption.label}
        </span>
      )}
    </div>
  );
}
