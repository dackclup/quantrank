import type { Metadata } from 'next';
import './globals.css';
import { AppShell } from '@/components/AppShell';
import { ThemeProvider } from '@/components/ThemeProvider';

// PR 4.5d follow-up — self-host all 3 fonts via @fontsource packages
// (SIL Open Font License). Previous `next/font/google` path failed
// CI on 2026-05-17 (PR #96 CI run #249, NextFontError: Failed to
// fetch IBM Plex Sans from Google Fonts) on a transient Google
// Fonts network blip. @fontsource bundles the woff2 files into
// node_modules so the build never touches an external host. CSS
// variables `--font-{ibm-plex-sans, jetbrains-mono, roboto-slab}`
// are now declared in globals.css instead of injected by `next/font`.

export const metadata: Metadata = {
  title: 'QuantRank',
  description:
    'Static-site US equity ranking — fundamental, technical, factor, sentiment, and ML signals combined into a 0–100 composite StockRank.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning` is required by next-themes — the
    // server renders without the `class="dark"` attr, the client
    // adds it before paint based on stored / system preference, so
    // the harmless attr mismatch on <html> needs to be suppressed.
    <html lang="en" suppressHydrationWarning>
      <body>
        {/* Pre-paint the collapsed sidebar (Bug A). The static export always
            bakes the EXPANDED rail into the HTML, so without this the rail
            flashes wide → narrow on refresh once React reads localStorage.
            Setting the class before the body paints lets globals.css render
            the collapsed width immediately. Mirrors next-themes' pre-paint
            dark-mode class; IIFE + try/catch, browser-only, never throws. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{if(localStorage.getItem('quantrank.sidebar.collapsed')==='1'){document.documentElement.classList.add('sidebar-collapsed')}}catch(e){}})()",
          }}
        />
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
