import fs from 'fs';
import path from 'path';

import rankingsJson from '@/public/data/rankings.json';
import metadataJson from '@/public/data/metadata.json';

import type {
  AiPickAdaptive,
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

const HISTORY_DIR = path.join(STOCKS_DIR, 'history');

type PriceHistoryFile = { dates: string[]; closes: (number | null)[] };

function readPriceHistory(ticker: string): PriceHistoryFile | null {
  const file = path.join(HISTORY_DIR, `${ticker}.json`);
  if (!fs.existsSync(file)) return null;
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf-8')) as PriceHistoryFile;
    if (!Array.isArray(raw.dates) || !Array.isArray(raw.closes)) return null;
    return raw;
  } catch {
    return null;
  }
}

// Close on the first trading day >= `date`, within a 7-day grace window so a
// rebalance dated on a holiday/weekend still resolves; null when the price
// history doesn't cover the date (file starts later than `date`).
function closeOnOrAfter(hist: PriceHistoryFile, date: string): number | null {
  for (let i = 0; i < hist.dates.length; i += 1) {
    if (hist.dates[i] >= date) {
      const limit = new Date(`${date}T00:00:00Z`);
      limit.setUTCDate(limit.getUTCDate() + 7);
      if (hist.dates[i] > limit.toISOString().slice(0, 10)) return null;
      return round2(hist.closes[i]);
    }
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

  // P/L-since-entry support: adjusted close at every rebalance date (index-
  // aligned with `timeline`) + the latest close, for the CURRENTLY-held tickers
  // only. Sourced from the per-ticker price-history files the stock-detail
  // chart already ships (yfinance auto-adjusted closes → split + dividend
  // adjusted, i.e. total-return basis, same as the NAV lines).
  const rebalanceDates = rebalances.map((r) => r.date);
  const entryCloses: Record<string, (number | null)[]> = {};
  const lastCloses: Record<string, number | null> = {};
  for (const h of last.holdings) {
    const hist = readPriceHistory(h.ticker);
    entryCloses[h.ticker] = hist
      ? rebalanceDates.map((d) => closeOnOrAfter(hist, d))
      : rebalanceDates.map(() => null);
    lastCloses[h.ticker] = hist ? round2(lastFinite(hist.closes)) : null;
  }

  // Phase 7.0 ADAPTIVE — resolve when the artifact carries nav.adaptive AND
  // the latest rebalance has adaptive_count. Build-time only; never fs-imports
  // into a 'use client' component (the build-time-data rule). Null-safe: when
  // the artifact predates the contract the component falls back to slider UI.
  let adaptive: AiPickAdaptive | null = null;
  if (
    nav.adaptive &&
    meta.adaptive_rule &&
    typeof last.adaptive_count === 'number'
  ) {
    const adaptiveSeries = nav.adaptive;
    const adaptiveCount = last.adaptive_count;
    const adaptiveCountKey = String(adaptiveCount);
    const adaptiveWeights = last.weights_by_count[adaptiveCountKey] ?? {};

    // The adaptive basket is the PREFIX holdings[:adaptiveCount], sorted by
    // weight descending to match the "Current picks" card display order.
    const adaptiveHoldings = last.holdings
      .slice(0, adaptiveCount)
      .sort((a, b) => (adaptiveWeights[b.ticker] ?? 0) - (adaptiveWeights[a.ticker] ?? 0))
      .map((h) => ({
        ticker: h.ticker,
        sector: h.sector,
        composite_score: round2(h.composite_score) ?? h.composite_score,
        weight: round2(adaptiveWeights[h.ticker] ?? null) ?? 0,
      }));

    adaptive = {
      rule: meta.adaptive_rule,
      net: adaptiveSeries.net.map(round2),
      gross: adaptiveSeries.gross.map(round2),
      conservative: adaptiveSeries.net_conservative.map(round2),
      finals: {
        gross: round2(lastFinite(adaptiveSeries.gross)),
        net: round2(lastFinite(adaptiveSeries.net)),
        conservative: round2(lastFinite(adaptiveSeries.net_conservative)),
      },
      latestCount: adaptiveCount,
      latestHoldings: adaptiveHoldings,
    };
  }

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
    entryCloses,
    lastCloses,
    // Caption-branching fields — forwarded from meta so sub-components
    // (AnnualReturnsTable / AiPickPortfolio) don't receive the full meta
    // object. Names-only from vetoes_not_replayed; reason is artifact-only.
    vetoLayerReplayed: meta.veto_layer_replayed,
    vetoesNotReplayed: meta.vetoes_not_replayed
      ? meta.vetoes_not_replayed.map((v) => ({ name: v.name }))
      : undefined,
    adaptive,
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
