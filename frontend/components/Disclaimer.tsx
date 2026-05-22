'use client';

import { useState } from 'react';

// Single-line subtle disclaimer with a "more / less" toggle. The
// previous bright-amber 3-line banner was the loudest element on
// the page; the design feedback flagged it as competing with the
// actual rankings for attention. Reduced to slate-50 + slate text
// with a small amber-tinted alert icon to preserve the signal
// without the visual cost.

export function Disclaimer() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div role="alert" className="border-b border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      <div className="mx-auto flex max-w-6xl items-start gap-2 px-4 py-2 text-xs">
        <svg
          aria-hidden="true"
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500 dark:text-amber-400"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          viewBox="0 0 24 24"
        >
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <div className="min-w-0 flex-1">
          <span className="font-medium text-slate-700 dark:text-slate-200">Educational use only.</span>
          <span className="ml-1">Not investment advice. Past performance does not predict future results.</span>
          {expanded && (
            <span className="ml-1 text-slate-500 dark:text-slate-400">
              Scores and &ldquo;fair prices&rdquo; are model outputs from public data — they can be wrong, stale, or misleading. Do not use for real-money trading decisions.
            </span>
          )}
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="ml-1 text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline dark:text-slate-400 dark:hover:text-slate-100"
          >
            {expanded ? 'less' : 'more'}
          </button>
        </div>
      </div>
    </div>
  );
}
