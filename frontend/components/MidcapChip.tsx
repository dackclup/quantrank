import { Chip } from '@/components/Chip';
import { STEEL_TONE } from '@/components/ListingChips';

// Mid-cap membership chip — renders for stocks where index_membership === 'sp400'
// (S&P 400 MidCap constituents in the sp900 universe expansion pilot).
//
// Design-system compliance (LedgerCraft outlined-light family):
//   - Uses the shared `Chip` primitive, never a hand-rolled shell.
//   - Neutral-steel tone (bg-slate-100 / text-slate-600 / ring-slate-200 +
//     paired dark: variants) — the same surface `SectorChip` and `ListingChips`
//     use for supporting metadata. No new color or ring width.
//   - No leading dot: the label "Mid-cap" is self-explanatory; a dot without a
//     sector-specific color would add noise rather than meaning.
//   - Renders nothing for sp500 rows (the current 502-name dataset) — invisible
//     today, lights up when sp900 data lands after the cron flip.
//
// Placement: caller-controlled; follow Rule 8 ("what existing slot does this most
// resemble?") — sit beside the SectorChip in table rows and mobile cards.

/** Renders a "Mid-cap" chip iff `indexMembership === 'sp400'`, else null. */
export function MidcapChip({
  indexMembership,
  size = 'xs',
}: {
  indexMembership: string;
  /** 'xs' (default) for table rows / mobile cards; 'sm' for detail hero. */
  size?: 'xs' | 'sm';
}) {
  if (indexMembership !== 'sp400') return null;
  return (
    <Chip
      tone={STEEL_TONE}
      size={size}
      title="S&P 400 MidCap constituent"
      aria-label="S&P 400 Mid-cap"
    >
      Mid-cap
    </Chip>
  );
}
