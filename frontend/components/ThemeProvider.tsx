'use client';

import { ThemeProvider as NextThemesProvider } from 'next-themes';

// LedgerCraft Phase 3b — wraps `next-themes` for class-strategy dark
// mode. `attribute="class"` flips `<html>` between `class=""` and
// `class="dark"` so Tailwind's `darkMode: 'class'` variants activate.
// `defaultTheme="system"` respects the OS preference until the user
// makes an explicit choice; `disableTransitionOnChange` prevents the
// global color-property animation from "skipping" colors during the
// toggle (avoids the brief mid-color flash on every surface).

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
