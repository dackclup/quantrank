import type { JSX } from 'react';
import { sectorStyle } from '@/lib/visual';

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
  const padX = size === 'xs' ? 'px-1.5 py-0' : 'px-2 py-0.5';
  const textSize = size === 'xs' ? 'text-[11px]' : 'text-xs';
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm ring-1 ring-inset ${padX} ${textSize} ${s.bg} ${s.fg} ${s.ring}`}
    >
      <span
        aria-hidden="true"
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: s.dot }}
      />
      <span className="truncate">{sector}</span>
    </span>
  );
}
