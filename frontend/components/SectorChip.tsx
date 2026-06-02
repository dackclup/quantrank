import type { JSX } from 'react';
import { sectorStyle } from '@/lib/visual';
import { CHIP_BASE, CHIP_DOT } from '@/components/Chip';

// Colored sector chip — replaces the plain-text sector cell flagged
// by the design feedback. The dot left of the label gives a fast
// visual scan in the rankings table (11 distinct colors for 11 GICS
// sectors), while the tinted background + matching ring carry the
// rest of the chip styling.
//
// `size='xs'` is for the mobile card sector|price row where
// horizontal space is tight; `size='sm'` is the default for the
// desktop table cell.

export function SectorChip({
  sector,
  size = 'sm',
}: {
  sector: string;
  size?: 'xs' | 'sm';
}): JSX.Element {
  const s = sectorStyle(sector);
  // Composes the shared chip shell + dot by hand (not the `Chip` component):
  // the `xs` text-size is `text-[0.6875rem]` — a deliberate 1px-larger value
  // than the canonical `CHIP_SIZES.xs` (`text-[0.625rem]`) for the tight mobile
  // sector|price row — and the dot is an inline-rgb sector accent, so routing
  // through `size`/`dot` would emit a conflicting text/dot utility.
  const padX = size === 'xs' ? 'px-1.5 py-0' : 'px-2 py-0.5';
  const textSize = size === 'xs' ? 'text-[0.6875rem]' : 'text-xs';
  return (
    <span
      className={`${CHIP_BASE} gap-1.5 font-medium ${padX} ${textSize} ${s.bg} ${s.fg} ${s.ring}`}
    >
      <span
        aria-hidden="true"
        className={CHIP_DOT}
        style={{ backgroundColor: s.dot }}
      />
      <span className="truncate">{sector}</span>
    </span>
  );
}
