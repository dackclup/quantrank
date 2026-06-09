import fs from 'fs';
import path from 'path';

import rankingsJson from '@/public/data/rankings.json';
import metadataJson from '@/public/data/metadata.json';

import type {
  AiPickData,
  AiPickFinals,
  BacktestPIT,
  Metadata,
  StockDetail,
  StockSummary,
} from './types';

const STOCKS_DIR = path.join(process.cwd(), 'public', 'data', 'stocks');

export function getRankings(): StockSummary[] {
  return rankingsJson as StockSummary[];
}

export function getMetadata(): Metadata {
  return metadataJson as Metadata;
}

const BACKTEST_PATH = path.join(process.cwd(), 'public', 'data', 'portfolio', 'backtest_pit.json');

// Read via fs (like getStockDetail) rather than a static import — the artifact is
// ~1.3 MB, so a JSON `import` would make tsc infer a giant literal type AND bundle
// it into the server build; fs.readFileSync sidesteps both and degrades gracefully
// when the backfill hasn't produced the file yet.
export function getBacktestPIT(): BacktestPIT | null {
  if (!fs.existsSync(BACKTEST_PATH)) return null;
  try {
    return JSON.parse(fs.readFileSync(BACKTEST_PATH, 'utf-8')) as BacktestPIT;
  } catch {
    return null;
  }
}

function round2(v: number | null | undefined): number | null {
  if (v === null || v === undefined || Number.isNaN(v)) return null;
  return Math.round(v * 100) / 100;
}

function lastFinite(arr: (number | null)[]): number | null {
  for (let i = arr.length - 1; i >= 0; i -= 1) {
    const v = arr[i];
    if (v !== null && v !== undefined && !Number.isNaN(v)) return v;
  }
  return null;
}

/**
 * Trim + round the 1.3 MB point-in-time backtest artifact into the small view
 * model the AI-pick home page ships to the client (the net line per count + the
 * benchmark lines + per-count finals + the latest rebalance + the trimmed
 * rotation timeline). Returns null when no backtest has been produced yet (empty
 * `nav`/`rebalances`) so the page can render a "backtest pending" state instead
 * of crashing. Build-time only.
 */
export function getAiPickData(): AiPickData | null {
  const bt = getBacktestPIT();
  if (
    !bt ||
    !bt.nav ||
    !bt.nav.dates ||
    bt.nav.dates.length === 0 ||
    !bt.rebalances ||
    bt.rebalances.length === 0
  ) {
    return null;
  }
  const { meta, nav, rebalances } = bt;

  const netByCount: Record<string, (number | null)[]> = {};
  const grossByCount: Record<string, (number | null)[]> = {};
  const conservativeByCount: Record<string, (number | null)[]> = {};
  const finalsByCount: Record<string, AiPickFinals> = {};
  for (const [count, series] of Object.entries(nav.by_count)) {
    netByCount[count] = series.net.map(round2);
    grossByCount[count] = series.gross.map(round2);
    conservativeByCount[count] = series.net_conservative.map(round2);
    finalsByCount[count] = {
      gross: round2(lastFinite(series.gross)),
      net: round2(lastFinite(series.net)),
      conservative: round2(lastFinite(series.net_conservative)),
    };
  }

  const benchmark: Record<string, (number | null)[]> = {};
  for (const [sym, series] of Object.entries(nav.benchmark)) {
    benchmark[sym] = series.map(round2);
  }

  const last = rebalances[rebalances.length - 1];
  return {
    meta,
    dates: nav.dates,
    netByCount,
    grossByCount,
    conservativeByCount,
    benchmark,
    finalsByCount,
    latest: {
      date: last.date,
      holdings: last.holdings,
      weightsByCount: last.weights_by_count,
    },
    // Every rebalance, trimmed to ticker + sector (oldest → newest). The full
    // holdings/weights stay in the raw artifact; the timeline only needs the
    // composite-ordered ticker list per quarter to render the rotation.
    timeline: rebalances.map((r) => ({
      date: r.date,
      holdings: r.holdings.map((h) => ({ ticker: h.ticker, sector: h.sector })),
    })),
  };
}

export function listAvailableTickers(): string[] {
  if (!fs.existsSync(STOCKS_DIR)) return [];
  return fs
    .readdirSync(STOCKS_DIR)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''));
}

/**
 * All tickers Next.js should pre-render at build time. Drawn from rankings.json
 * so the static export covers every stock in the universe — even if its
 * per-stock detail JSON hasn't been written yet (Phase 2 compute populates
 * those after merge). Pages without detail data fall back to a "pending"
 * placeholder; ``output: 'export'`` requires a non-empty list here.
 *
 * We always include ``"_PLACEHOLDER"`` so the build succeeds on a fresh repo
 * where rankings.json is the empty Phase 0 stub.
 */
export function listTickersForStaticBuild(): string[] {
  const tickers = (rankingsJson as StockSummary[]).map((s) => s.ticker);
  return tickers.length > 0 ? tickers : ['_PLACEHOLDER'];
}

export function getStockDetail(ticker: string): StockDetail | null {
  const file = path.join(STOCKS_DIR, `${ticker}.json`);
  if (!fs.existsSync(file)) return null;
  try {
    const raw = fs.readFileSync(file, 'utf-8');
    return JSON.parse(raw) as StockDetail;
  } catch {
    return null;
  }
}
