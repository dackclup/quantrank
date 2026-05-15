import type { Metadata } from 'next';
import { IBM_Plex_Sans, Instrument_Serif, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { Disclaimer } from '@/components/Disclaimer';

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-ibm-plex-sans',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
  variable: '--font-jetbrains-mono',
});

const instrumentSerif = Instrument_Serif({
  subsets: ['latin'],
  weight: ['400'],
  style: ['normal', 'italic'],
  display: 'swap',
  variable: '--font-instrument-serif',
});

export const metadata: Metadata = {
  title: 'QuantRank',
  description:
    'Static-site US equity ranking — fundamental, technical, factor, sentiment, and ML signals combined into a 0–100 composite StockRank.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ibmPlexSans.variable} ${jetbrainsMono.variable} ${instrumentSerif.variable}`}>
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
