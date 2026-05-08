import fs from 'fs';
import path from 'path';

import rankingsJson from '@/public/data/rankings.json';
import metadataJson from '@/public/data/metadata.json';

import type { Metadata, StockDetail, StockSummary } from './types';

const STOCKS_DIR = path.join(process.cwd(), 'public', 'data', 'stocks');

export function getRankings(): StockSummary[] {
  return rankingsJson as StockSummary[];
}

export function getMetadata(): Metadata {
  return metadataJson as Metadata;
}

export function listAvailableTickers(): string[] {
  if (!fs.existsSync(STOCKS_DIR)) return [];
  return fs
    .readdirSync(STOCKS_DIR)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''));
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
