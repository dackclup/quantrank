'use client';

import type { JSX } from 'react';

import type { Tier2Events } from '@/lib/types';

// Per PR 3d Step 6 spec, Tier-2 events are the *first* thing a user
// should see about a stock — they affect investability more than
// valuation. The card renders only when at least one of the three
// flags fired; otherwise it returns null and takes no layout space.
//
// Inline SVG icons (lucide-react is not in package.json and the spec
// forbids new deps). Stroke-based 24px icons matching lucide's
// visual style — currentColor inherits the row's text-* class.

interface Tier2EventCardProps {
  tier2_events: Tier2Events | null;
  ticker: string;
}

type Severity = 'veto' | 'annotate';

interface EventRow {
  key: 'non_reliance_filing' | 'going_concern_disclosure' | 'auditor_change';
  label: string;
  severity: Severity;
  severityLabel: string;
  url: string | null;
  icon: JSX.Element;
}

const ICON_CLASS = 'h-4 w-4 shrink-0';

const AlertOctagonIcon = (
  <svg
    aria-hidden="true"
    className={ICON_CLASS}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    viewBox="0 0 24 24"
  >
    <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const AlertTriangleIcon = (
  <svg
    aria-hidden="true"
    className={ICON_CLASS}
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
);

const UserMinusIcon = (
  <svg
    aria-hidden="true"
    className={ICON_CLASS}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    viewBox="0 0 24 24"
  >
    <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="8.5" cy="7" r="4" />
    <line x1="23" y1="11" x2="17" y2="11" />
  </svg>
);

const ExternalLinkIcon = (
  <svg
    aria-hidden="true"
    className="ml-1 inline h-3 w-3 shrink-0"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    viewBox="0 0 24 24"
  >
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

function severityClasses(severity: Severity): string {
  // Light-theme palette — matches the existing rankings-table pattern
  // (Score badge / filing-lag badge use the same ring-1 ring-inset
  // approach with rose/amber/emerald families).
  if (severity === 'veto') {
    return 'bg-rose-100 text-rose-800 ring-rose-200';
  }
  return 'bg-amber-100 text-amber-800 ring-amber-200';
}

function rowTextClasses(severity: Severity): string {
  return severity === 'veto' ? 'text-rose-700' : 'text-amber-700';
}

export function Tier2EventCard({
  tier2_events,
  ticker,
}: Tier2EventCardProps): JSX.Element | null {
  // Loose-equality null check — also catches `undefined`, which is
  // what runtime sees when reading a StockDetail JSON written under
  // a pre-PR-3d schema (the JSON file simply omits the key). The
  // TypeScript contract says `Tier2Events | null` but the on-disk
  // older schemas don't carry the field at all until Step 10's
  // compute run regenerates them.
  if (tier2_events == null) {
    return null;
  }
  const {
    going_concern_disclosure,
    non_reliance_filing,
    auditor_change,
    latest_8k_filing_date,
    latest_8k_filing_url,
  } = tier2_events;

  if (!going_concern_disclosure && !non_reliance_filing && !auditor_change) {
    return null;
  }

  const rows: EventRow[] = [];
  if (non_reliance_filing) {
    rows.push({
      key: 'non_reliance_filing',
      label: 'Non-reliance filing (8-K Item 4.02)',
      severity: 'veto',
      severityLabel: 'HARD VETO',
      url: latest_8k_filing_url,
      icon: AlertOctagonIcon,
    });
  }
  if (going_concern_disclosure) {
    rows.push({
      key: 'going_concern_disclosure',
      label: 'Going-concern disclosure (10-K)',
      severity: 'annotate',
      severityLabel: 'Annotate',
      // No 8-K URL applies — going-concern is a 10-K text scan.
      url: null,
      icon: AlertTriangleIcon,
    });
  }
  if (auditor_change) {
    rows.push({
      key: 'auditor_change',
      label: 'Auditor change (8-K Item 4.01)',
      severity: 'annotate',
      severityLabel: 'Annotate',
      url: latest_8k_filing_url,
      icon: UserMinusIcon,
    });
  }

  const showDateFooter =
    latest_8k_filing_date !== null && (non_reliance_filing || auditor_change);

  return (
    <section
      aria-label={`Regulatory events for ${ticker}`}
      className="rounded-lg border border-slate-200 bg-white p-4 sm:max-w-2xl"
    >
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
        Recent regulatory events
      </h2>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li
            key={row.key}
            className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:gap-3"
          >
            <span className={`flex items-center gap-2 ${rowTextClasses(row.severity)}`}>
              {row.icon}
              <span className="text-slate-700">{row.label}</span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${severityClasses(row.severity)}`}
                role="status"
              >
                {row.severityLabel}
              </span>
              {row.url && (
                <a
                  className="inline-flex items-center text-xs text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline"
                  href={row.url}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  View filing
                  {ExternalLinkIcon}
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
      {showDateFooter && (
        <p className="mt-3 text-xs text-slate-400">
          Latest 8-K: {latest_8k_filing_date}
        </p>
      )}
    </section>
  );
}
