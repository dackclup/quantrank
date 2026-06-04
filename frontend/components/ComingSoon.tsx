import Link from 'next/link';

// ComingSoon — shared placeholder body for routes that exist in the top nav but
// have no data model yet (Analysis, Portfolio). Pure presentational; stays
// within the design system (rounded card · shadow-subtle · slate/emerald
// tokens · 44px CTA). The emerald CTA uses `dark:bg-emerald-700` (NOT 600) per
// the soft-color override gotcha so the white label clears AA on the dark band.

export function ComingSoon({
  title,
  lead,
  detail,
}: {
  title: string;
  lead: string;
  detail: string;
}) {
  return (
    <section className="space-y-6">
      <header>
        <h1 className="font-slab text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
      </header>
      <div className="flex flex-col items-center rounded border border-slate-200 bg-white px-6 py-14 text-center shadow-subtle dark:border-slate-800 dark:bg-slate-900">
        <span
          className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
          aria-hidden="true"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15.5 14" />
          </svg>
        </span>
        <p className="text-base font-semibold text-slate-800 dark:text-slate-100">{lead}</p>
        <p className="mt-2 max-w-md text-sm text-slate-500 dark:text-slate-400">{detail}</p>
        <Link
          href="/ranking"
          className="mt-6 inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white press hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
        >
          Browse the ranking
        </Link>
      </div>
    </section>
  );
}
