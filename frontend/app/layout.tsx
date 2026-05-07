import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'QuantRank',
  description:
    'Static-site US equity ranking — fundamental, technical, factor, sentiment, and ML signals combined into a 0–100 composite StockRank.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
            <div className="flex items-baseline gap-3">
              <span className="text-xl font-semibold tracking-tight">QuantRank</span>
              <span className="text-sm text-slate-500">US equity stock ranking</span>
            </div>
            <nav className="text-sm text-slate-600">
              <a
                href="https://github.com/dackclup/quantrank"
                className="hover:text-slate-900"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <div
          role="alert"
          className="border-b border-amber-200 bg-amber-50 text-amber-900"
        >
          <div className="mx-auto max-w-6xl px-4 py-3 text-sm">
            <strong>Disclaimer:</strong> QuantRank is for educational and research
            purposes only. Nothing here is investment advice, a recommendation, or
            an offer to buy or sell securities. Do not use these scores for
            real-money trading decisions. Past performance does not predict future
            results.
          </div>
        </div>
        <main className="mx-auto max-w-6xl px-4 py-10">{children}</main>
        <footer className="border-t border-slate-200 bg-white">
          <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500">
            QuantRank · MIT licensed · Data refreshed weekly via GitHub Actions.
          </div>
        </footer>
      </body>
    </html>
  );
}
