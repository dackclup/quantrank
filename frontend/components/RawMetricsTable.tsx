import type { RawMetrics } from '@/lib/types';

function formatLargeNumber(n: number | null): string {
  if (n == null || Number.isNaN(n)) return 'N/A';
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(2);
}

function formatCurrency(n: number | null): string {
  if (n == null || Number.isNaN(n)) return 'N/A';
  return `$${formatLargeNumber(n)}`;
}

function formatPerShare(n: number | null): string {
  if (n == null || Number.isNaN(n)) return 'N/A';
  return `$${n.toFixed(2)}`;
}

function formatRatio(n: number | null): string {
  if (n == null || Number.isNaN(n)) return 'N/A';
  return n.toFixed(2);
}

const ROWS: Array<{
  key: keyof RawMetrics;
  label: string;
  fmt: (n: number | null) => string;
  hint?: string;
}> = [
  { key: 'market_cap', label: 'Market cap', fmt: formatCurrency },
  { key: 'revenue', label: 'Revenue (TTM)', fmt: formatCurrency },
  { key: 'net_income', label: 'Net income (TTM)', fmt: formatCurrency },
  { key: 'operating_cash_flow', label: 'Operating cash flow (TTM)', fmt: formatCurrency },
  { key: 'capex', label: 'CapEx (TTM)', fmt: formatCurrency },
  { key: 'free_cash_flow', label: 'Free cash flow (TTM)', fmt: formatCurrency, hint: 'CFO − CapEx' },
  { key: 'total_assets', label: 'Total assets', fmt: formatCurrency },
  { key: 'total_liabilities', label: 'Total liabilities', fmt: formatCurrency },
  { key: 'stockholders_equity', label: "Stockholders' equity", fmt: formatCurrency },
  { key: 'cash', label: 'Cash & equivalents', fmt: formatCurrency },
  { key: 'shares_outstanding', label: 'Shares outstanding', fmt: formatLargeNumber },
  { key: 'eps_basic', label: 'EPS (basic)', fmt: formatPerShare },
  { key: 'eps_diluted', label: 'EPS (diluted)', fmt: formatPerShare },
  { key: 'pe_ratio_ttm', label: 'P/E ratio (TTM)', fmt: formatRatio },
];

export default function RawMetricsTable({ metrics }: { metrics: RawMetrics }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Metric</th>
            <th className="px-3 py-2 text-right font-medium">Value</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {ROWS.map(({ key, label, fmt, hint }) => {
            const v = metrics[key];
            const isMissing = v == null;
            return (
              <tr key={key} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-700">
                  {label}
                  {hint && <span className="ml-1 text-xs text-slate-400">{hint}</span>}
                </td>
                <td
                  className={
                    isMissing
                      ? 'px-3 py-2 text-right italic text-slate-400'
                      : 'px-3 py-2 text-right tabular-nums text-slate-900'
                  }
                >
                  {fmt(v as number | null)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
