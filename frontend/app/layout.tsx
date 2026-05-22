import type { Metadata } from 'next';
import './globals.css';
import { AppShell } from '@/components/AppShell';

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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
