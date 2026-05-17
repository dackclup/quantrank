import type { Metadata } from 'next';
import './globals.css';
import { Disclaimer } from '@/components/Disclaimer';

// PR 4.5d follow-up — self-host all 3 fonts via @fontsource packages
// (SIL Open Font License). Previous `next/font/google` path failed
// CI on 2026-05-17 (PR #96 CI run #249, NextFontError: Failed to
// fetch IBM Plex Sans from Google Fonts) on a transient Google
// Fonts network blip. @fontsource bundles the woff2 files into
// node_modules so the build never touches an external host. CSS
// variables `--font-{ibm-plex-sans, jetbrains-mono, instrument-serif}`
// are now declared in globals.css instead of injected by `next/font`.

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
              <a href="/" className="text-xl font-semibold tracking-tight">QuantRank</a>
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
        <Disclaimer />
        <main className="mx-auto max-w-6xl px-4 py-10">{children}</main>
        <footer className="border-t border-slate-200 bg-white">
          <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500">
            QuantRank · MIT licensed · Data refreshed every US trading day via GitHub Actions.
          </div>
        </footer>
      </body>
    </html>
  );
}
