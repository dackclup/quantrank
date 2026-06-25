import fs from 'fs';
import path from 'path';

import rankingsJson from '@/public/data/rankings.json';
import metadataJson from '@/public/data/metadata.json';
import decayReportJson from '@/public/data/decay_report.json';

import type {
  AiPickAdaptive,
  AiPickData,
  AiPickFinals,
  BacktestPIT,
  DecayReport,
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

// IC-decay monitor artifact — always emitted by the cron (or a safe stub when
// QR_SKIP_DECAY_MONITOR is set); a static import is appropriate because the file
// is small (10 pillars, fixed shape) and always present at build time. The cast
// is safe: DecayReport is a plain TS interface mirroring the dataclass output,
// NOT a Pydantic schema — this function is NOT part of the schema-snapshot triple.
export function getDecayReport(): DecayReport {
  return decayReportJson as DecayReport;
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

// Basket weights need finer precision than the 2dp money/price fields. The
// "Current picks" card apportions them to a 0.1%-resolution display that must
// sum to exactly 100%, so rounding a weight to 2dp here (0.207 -> 0.21) would
// pre-corrupt the basket sum to ~1.01 before the display layer ever sees it.
// 6dp keeps the raw inverse-vol weights summing to 1.0 for the apportionment.
function roundWeight(v: number | null | undefined): number | null {
  if (v === null || v === undefined || Number.isNaN(v)) return null;
  return Math.round(v * 1e6) / 1e6;
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
  // aligned with `timeline`) + the latest close. Covers both the CURRENTLY-held
  // tickers (last.holdings) AND the PRIOR rebalance's basket tickers so that
  // sold-row return (entry→sell-date) can be computed even when a ticker has
  // since dropped out of last.holdings. Sourced from the per-ticker price-history
  // files the stock-detail chart already ships (yfinance auto-adjusted closes →
  // split + dividend adjusted, i.e. total-return basis, same as the NAV lines).
  const rebalanceDates = rebalances.map((r) => r.date);
  const entryCloses: Record<string, (number | null)[]> = {};
  const lastCloses: Record<string, number | null> = {};

  // Derive the prior basket's tickers (mirrors the priorWeights block below).
  const priorBasketTickers: string[] = rebalances.length >= 2
    ? (() => {
        const prv = rebalances[rebalances.length - 2] as unknown as {
          band_weights?: Record<string, number>;
          weights_by_count?: Record<string, Record<string, number>>;
          adaptive_count?: number;
        };
        const pw = prv.band_weights
          ?? (prv.adaptive_count != null ? prv.weights_by_count?.[String(prv.adaptive_count)] : undefined)
          ?? {};
        return Object.keys(pw);
      })()
    : [];

  // Union of current holdings + prior basket tickers — additive; existing
  // held-ticker behavior is byte-identical.
  const priceTickerSet = new Set([
    ...last.holdings.map((h) => h.ticker),
    ...priorBasketTickers,
  ]);

  for (const ticker of priceTickerSet) {
    const hist = readPriceHistory(ticker);
    entryCloses[ticker] = hist
      ? rebalanceDates.map((d) => closeOnOrAfter(hist, d))
      : rebalanceDates.map(() => null);
    lastCloses[ticker] = hist ? round2(lastFinite(hist.closes)) : null;
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
        // Use null (not 0) when weight is missing so the display renders "—"
        // (em-dash) rather than "0.0%" — mirrors the slider branch's treatment.
        weight: roundWeight(adaptiveWeights[h.ticker] ?? null),
      }));

    // V55 HOLD-BAND (STATE 1) — detected when the latest rebalance carries
    // band_book + band_weights AND meta.adaptive_rule.hold_band_min is present.
    // The band book is NOT a prefix of holdings; it is the actual held set after
    // the hysteresis filter. Absent → STATE 2 (pre-band adaptive, unchanged).
    const hasBand =
      typeof meta.adaptive_rule.hold_band_min === 'number' &&
      Array.isArray(last.band_book) &&
      last.band_book.length > 0 &&
      last.band_weights != null;

    // Build a lookup of composite scores for all holdings so we can tag
    // carried names (composite < composite_min) in the band book.
    const compositeByTicker: Record<string, number> = {};
    for (const h of last.holdings) {
      compositeByTicker[h.ticker] = h.composite_score;
    }
    const sectorByTicker: Record<string, string> = {};
    for (const h of last.holdings) {
      sectorByTicker[h.ticker] = h.sector;
    }

    const bandFields: Partial<Pick<
      import('./types').AiPickAdaptive,
      'holdBandMin' | 'latestBandHoldings'
    >> = hasBand
      ? {
          holdBandMin: meta.adaptive_rule.hold_band_min as number,
          latestBandHoldings: (last.band_book as string[]).map((ticker) => {
            const bw = (last.band_weights as Record<string, number>)[ticker] ?? null;
            const score = compositeByTicker[ticker] ?? 0;
            const compositeMin = meta.adaptive_rule!.composite_min;
            const holdBandMin = meta.adaptive_rule!.hold_band_min as number;
            // Prefer the engine-exported band_carry_names list
            // when present — it is the authoritative source (the engine knows
            // exactly which names were carried vs freshly entered, whereas the
            // score-only inference can mislabel floor-padded thin legs).
            // Fallback gains the lower-bound guard (score >= holdBandMin) so
            // floor-pads (score < holdBandMin) are never false-positive carried.
            const carryNames = Array.isArray(last.band_carry_names)
              ? (last.band_carry_names as string[])
              : null;
            const carried = carryNames
              ? carryNames.includes(ticker)
              : score >= holdBandMin && score < compositeMin;
            return {
              ticker,
              sector: sectorByTicker[ticker] ?? '',
              composite_score: round2(score) ?? score,
              weight: roundWeight(bw),
              // A name is "carried" when its score is below composite_min but
              // still above hold_band_min — held for stability, not a new entry.
              carried,
            };
          }),
        }
      : {};

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
      ...bandFields,
    };
  }

  // Build a map of current composite scores from the latest rebalance's
  // full_ranked array — covers ALL ranked tickers (including sold names) so
  // the "Current picks" Sold rows can display the score the rotated-out stock
  // carries NOW, consistent with Held/New rows (which show composite_score
  // from last.holdings). Falls back to an empty map on pre-full_ranked artifacts.
  const latestScores: Record<string, number> = {};
  const fullRanked = (last as unknown as { full_ranked?: Array<{ ticker: string; composite_score: number }> }).full_ranked ?? [];
  for (const r of fullRanked) {
    latestScores[r.ticker] = r.composite_score;
  }

  // Build a map of the PRIOR rebalance's per-ticker basket weights — used by the
  // Current-picks "Change" column in the adaptive branch to show relative weight
  // deltas vs the previous quarter. Empty on the very first rebalance (no prior).
  const priorWeights: Record<string, number> = {};
  if (rebalances.length >= 2) {
    const prv = rebalances[rebalances.length - 2] as unknown as {
      band_weights?: Record<string, number>;
      weights_by_count?: Record<string, Record<string, number>>;
      adaptive_count?: number;
    };
    const pw = prv.band_weights
      ?? (prv.adaptive_count != null ? prv.weights_by_count?.[String(prv.adaptive_count)] : undefined)
      ?? {};
    for (const [t, w] of Object.entries(pw)) priorWeights[t] = w;
  }

  // ---------------------------------------------------------------------------
  // Build-time precompute: per-quarter weightByTicker + returnByTicker for the
  // Rotation history expandable drawer detail table. These are additive fields
  // on each AiPickTimelineEntry — the drawer degrades gracefully to '—' on
  // legacy artifacts that predate this contract.
  //
  // Natural held set mirrors HoldingsTimeline's per-entry slice logic so the
  // drawer's Status/held-set always agrees with the header summary row:
  //   • band_book present & non-empty → that exact array
  //   • else adaptive_count present   → holdings[:adaptive_count]
  //   • else band_held_count present  → holdings[:band_held_count]
  //   • else                          → all holdings tickers (slider mode)
  //
  // Returns: for held tickers: streak-start → this quarter's rebalance.
  //          for exited names: streak-start → exit rebalance (entry→exit).
  // ---------------------------------------------------------------------------

  // Helper: compute the natural held set for a raw rebalance.
  const naturalHeldTickers = (r: typeof rebalances[number]): string[] => {
    if (Array.isArray(r.band_book) && r.band_book.length > 0) {
      return r.band_book as string[];
    }
    const sc = r.band_held_count ?? r.adaptive_count;
    return sc !== undefined
      ? r.holdings.slice(0, sc).map((h) => h.ticker)
      : r.holdings.map((h) => h.ticker);
  };

  // Pre-derive held sets for every rebalance (avoids O(n^2) re-computation).
  const naturalHeldPerRebalance: string[][] = rebalances.map(naturalHeldTickers);

  // Build union of all tickers that ever appear in any held set or exit at any
  // rebalance — so we only need one fs read per ticker across the full history.
  const drawerTickerSet = new Set<string>();
  for (const held of naturalHeldPerRebalance) {
    held.forEach((t) => drawerTickerSet.add(t));
  }
  for (let i = 1; i < rebalances.length; i += 1) {
    const curSet = new Set(naturalHeldPerRebalance[i]);
    for (const t of naturalHeldPerRebalance[i - 1]) {
      if (!curSet.has(t)) drawerTickerSet.add(t);
    }
  }

  // Read price history once per drawer ticker (fs.readFileSync — build-time only).
  const drawerHistory: Record<string, PriceHistoryFile | null> = {};
  for (const ticker of drawerTickerSet) {
    drawerHistory[ticker] = readPriceHistory(ticker);
  }

  // Closes-at-rebalance for all drawer tickers, index-aligned with rebalances.
  const drawerClosesAtRebalance: Record<string, (number | null)[]> = {};
  for (const ticker of drawerTickerSet) {
    const hist = drawerHistory[ticker];
    drawerClosesAtRebalance[ticker] = hist
      ? rebalanceDates.map((d) => closeOnOrAfter(hist, d))
      : rebalanceDates.map(() => null);
  }

  // Pre-build Set-per-rebalance for O(1) membership check in the streak walk.
  const naturalHeldSets: Set<string>[] = naturalHeldPerRebalance.map(
    (tickers) => new Set(tickers),
  );

  // Per-rebalance drawer data: weightByTicker + returnByTicker.
  const drawerDataPerRebalance = rebalances.map((r, i) => {
    const heldTickers = naturalHeldPerRebalance[i];
    const heldSet = naturalHeldSets[i];
    const prevHeld = i > 0 ? naturalHeldPerRebalance[i - 1] : [];

    // Weights — mirror the priorWeights derivation: prefer band_weights, then
    // weights_by_count[adaptive_count], then empty (no weights available).
    const rRaw = r as unknown as {
      band_weights?: Record<string, number>;
      weights_by_count?: Record<string, Record<string, number>>;
      adaptive_count?: number;
    };
    const weights: Record<string, number> = rRaw.band_weights
      ?? (rRaw.adaptive_count != null
        ? rRaw.weights_by_count?.[String(rRaw.adaptive_count)]
        : undefined)
      ?? {};
    const weightByTicker: Record<string, number | null> = {};
    for (const t of heldTickers) {
      weightByTicker[t] = roundWeight(weights[t] ?? null);
    }
    // Exited names had weight in the prior quarter; record 0 here (out of basket).
    const exitedTickers = prevHeld.filter((t) => !heldSet.has(t));
    for (const t of exitedTickers) {
      weightByTicker[t] = 0;
    }

    // Returns — streak-start walk using the pre-built sets.
    const returnByTicker: Record<string, number | null> = {};
    for (const t of heldTickers) {
      let streakStart = i;
      while (streakStart > 0 && naturalHeldSets[streakStart - 1].has(t)) {
        streakStart -= 1;
      }
      const entryClose = drawerClosesAtRebalance[t]?.[streakStart] ?? null;
      const thisClose = drawerClosesAtRebalance[t]?.[i] ?? null;
      returnByTicker[t] =
        entryClose !== null && thisClose !== null && entryClose !== 0
          ? round2((thisClose / entryClose - 1) * 100)
          : null;
    }
    // Exited names — streak-start within the prior membership (i-1).
    for (const t of exitedTickers) {
      let streakStart = i - 1;
      while (streakStart > 0 && naturalHeldSets[streakStart - 1].has(t)) {
        streakStart -= 1;
      }
      const entryClose = drawerClosesAtRebalance[t]?.[streakStart] ?? null;
      const exitClose = drawerClosesAtRebalance[t]?.[i] ?? null;
      returnByTicker[t] =
        entryClose !== null && exitClose !== null && entryClose !== 0
          ? round2((exitClose / entryClose - 1) * 100)
          : null;
    }

    return { weightByTicker, returnByTicker };
  });

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
    // `adaptiveCount` is carried through when present so HoldingsTimeline can
    // slice each quarter to ITS OWN count (the adaptive basket varies 5-13)
    // rather than back-projecting today's count onto every historical quarter.
    // `bandHeldCount` is carried when the rebalance has the hold-band applied —
    // it reflects the true held count (may differ from adaptiveCount when
    // carries are present). HoldingsTimeline prefers bandHeldCount over
    // adaptiveCount when both are present.
    //
    // `bandBook` carries the EXACT held set for band rebalances (r.band_book
    // from the raw artifact). HoldingsTimeline uses it directly when present
    // instead of slicing holdings[:sliceCount]. Sectors from r.holdings.
    // `bandCarryNames` carries r.band_carry_names for carried-ticker tagging.
    //
    // `weightByTicker` / `returnByTicker` — build-time-precomputed per-quarter
    // data for the expandable drawer detail table (additive, absent on legacy).
    timeline: rebalances.map((r, i) => ({
      date: r.date,
      holdings: r.holdings.map((h) => ({ ticker: h.ticker, sector: h.sector })),
      ...(typeof r.adaptive_count === 'number' ? { adaptiveCount: r.adaptive_count } : {}),
      ...(typeof r.band_held_count === 'number' ? { bandHeldCount: r.band_held_count } : {}),
      ...(Array.isArray(r.band_book) && r.band_book.length > 0
        ? { bandBook: r.band_book as string[] }
        : {}),
      ...(Array.isArray(r.band_carry_names) && r.band_carry_names.length > 0
        ? { bandCarryNames: r.band_carry_names as string[] }
        : {}),
      ...drawerDataPerRebalance[i],
    })),
    entryCloses,
    lastCloses,
    latestScores,
    priorWeights,
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
