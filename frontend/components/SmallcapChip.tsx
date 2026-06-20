import { Chip } from '@/components/Chip';

// Small-cap membership chip — renders for stocks where index_membership === 'sp600'
// (S&P 600 SmallCap constituents in the sp1500 universe expansion, Slice 6).
//
// Design-system compliance (LedgerCraft outlined-light family):
//   - Uses the shared `Chip` primitive, never a hand-rolled shell.
//   - Violet-info tone (bg-violet-50 / text-violet-700 / ring-violet-200 +
//     paired dark: variants) — DISTINCT from MidcapChip's neutral-steel slate
//     (bg-slate-100 / text-slate-600 / ring-slate-200), while staying in the
//     same outlined-light chip family and within the soft palette (Rule 1).
//     Violet is the "info" class per the design system palette (not emerald /
//     red / amber which carry semantic weight in scoring). No new pattern.
//   - No leading dot: "Small-cap" is self-explanatory; a dot without sector-
//     color meaning would add noise rather than signal.
//   - Renders nothing for sp500/sp400 rows (the current ~902-name dataset) —
//     invisible today, lights up when sp600 data lands after the Slice 7 cron
//     flip. Mirrors MidcapChip's data-driven dormancy exactly.
//
// Placement: caller-controlled; follow Rule 8 ("what existing slot does this
// most resemble?") — sit beside MidcapChip and SectorChip in table rows and
// mobile cards.

/** Outlined-light violet tone — distinct from MidcapChip's steel, same family. */
export const VIOLET_TONE =
  'bg-violet-50 text-violet-700 ring-violet-200 ' +
  'dark:bg-violet-900/30 dark:text-violet-300 dark:ring-violet-800';

/** Renders a "Small-cap" chip iff `indexMembership === 'sp600'`, else null. */
export function SmallcapChip({
  indexMembership,
  size = 'xs',
}: {
  indexMembership: string;
  /** 'xs' (default) for table rows / mobile cards; 'sm' for detail hero. */
  size?: 'xs' | 'sm';
}) {
  if (indexMembership !== 'sp600') return null;
  return (
    <Chip
      tone={VIOLET_TONE}
      size={size}
      title="S&P 600 SmallCap constituent"
      aria-label="S&P 600 Small-cap"
    >
      Small-cap
    </Chip>
  );
}
