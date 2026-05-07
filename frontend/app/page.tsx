import metadata from '@/public/data/metadata.json';

export default function HomePage() {
  return (
    <section className="flex flex-col items-center justify-center gap-6 py-24 text-center">
      <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
        QuantRank — coming soon
      </h1>
      <p className="max-w-xl text-base text-slate-600">
        A static, open-source US equity ranking app combining 60+ fundamental,
        technical, factor, sentiment, and ML signals into a single 0–100 score.
      </p>
      <dl className="grid grid-cols-2 gap-x-8 gap-y-2 rounded-lg border border-slate-200 bg-white px-6 py-4 text-sm">
        <dt className="text-slate-500">Schema version</dt>
        <dd className="font-mono">{metadata.version}</dd>
        <dt className="text-slate-500">Universe</dt>
        <dd className="font-mono">{metadata.universe}</dd>
        <dt className="text-slate-500">Last update (UTC)</dt>
        <dd className="font-mono">{metadata.last_update_utc}</dd>
        <dt className="text-slate-500">Universe size</dt>
        <dd className="font-mono">{metadata.universe_size}</dd>
      </dl>
      <p className="text-xs text-slate-400">
        Phase 0 placeholder. Real rankings ship in Phase 1.
      </p>
    </section>
  );
}
