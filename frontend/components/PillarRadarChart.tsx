'use client';

import type { JSX } from 'react';
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts';

import type { PillarScores } from '@/lib/types';

// 8-pillar radar visualization (PR 3d Step 7).
//
// PillarScores has 10 keys but only 8 are active in PR 3b-3d:
// quality / value / growth / momentum / health / profitability /
// technical / risk. The remaining two (sentiment + ml) are
// permanently null until Phase 5+ — they're rendered as a
// footnote rather than empty radar axes.
//
// Null active-pillar handling: skipped from the radar entirely
// (no axis, no value point). The footer line names which pillars
// were dropped + why, so a degraded data-quality stock isn't
// silently shrunk to a 5-pillar radar without explanation.
//
// Hard floor: if fewer than 5 non-null active pillars remain, we
// return null. A 4-axis radar is degenerate (2 chord pairs) and
// less informative than not rendering — the existing pillar-scores
// table downstream still surfaces the raw values.

interface PillarRadarChartProps {
  pillars: PillarScores;
  ticker: string;
}

// Active pillars (8) + the always-null pair (sentiment + ml).
// Tuple-typed for the discriminated union below.
const ACTIVE_PILLARS = [
  ['quality', 'Quality'],
  ['value', 'Value'],
  ['growth', 'Growth'],
  ['momentum', 'Momentum'],
  ['health', 'Health'],
  ['profitability', 'Profitability'],
  ['technical', 'Technical'],
  ['risk', 'Risk'],
] as const satisfies ReadonlyArray<readonly [keyof PillarScores, string]>;

const PHASE5_PLUS_PILLARS: ReadonlyArray<keyof PillarScores> = ['sentiment', 'ml'];

const MIN_AXES_FOR_USEFUL_RADAR = 5;

interface RadarPoint {
  pillar: string;
  value: number;
  fullMark: 100;
}

export function PillarRadarChart({
  pillars,
  ticker,
}: PillarRadarChartProps): JSX.Element | null {
  if (pillars == null) {
    return null;
  }

  // Build the radar dataset from active pillars only; collect dropped
  // active-pillar labels so the footer can explain the gap when
  // data-quality issues null out an active pillar.
  const data: RadarPoint[] = [];
  const droppedActive: string[] = [];
  for (const [key, label] of ACTIVE_PILLARS) {
    const v = pillars[key];
    if (v === null || v === undefined || Number.isNaN(v)) {
      droppedActive.push(label);
      continue;
    }
    data.push({ pillar: label, value: v, fullMark: 100 });
  }

  if (data.length < MIN_AXES_FOR_USEFUL_RADAR) {
    return null;
  }

  const phase5Names = PHASE5_PLUS_PILLARS.map(
    (k) => k.charAt(0).toUpperCase() + k.slice(1),
  );

  const footerSegments: string[] = [];
  if (droppedActive.length > 0) {
    footerSegments.push(
      `${droppedActive.join(', ')} (data quality issue this run)`,
    );
  }
  // sentiment + ml are *always* null in Phase 3 — explain once with a
  // stable Phase-5+ caveat so the user understands why the radar has
  // 8 axes max, not 10.
  footerSegments.push(`${phase5Names.join(', ')} (Phase 5+)`);

  return (
    <section
      aria-label={`Pillar score breakdown for ${ticker}`}
      className="mb-4 rounded-lg border border-slate-200 bg-white p-4 sm:max-w-2xl"
    >
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
        Pillar breakdown
      </h2>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart
            data={data}
            cx="50%"
            cy="50%"
            outerRadius="70%"
            margin={{ top: 8, right: 24, bottom: 8, left: 24 }}
          >
            <PolarGrid stroke="rgb(226 232 240)" />
            <PolarAngleAxis
              dataKey="pillar"
              tick={{ fontSize: 12, fill: 'rgb(71 85 105)' }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: 'rgb(148 163 184)' }}
              tickCount={6}
            />
            <Radar
              name={ticker}
              dataKey="value"
              stroke="rgb(99 102 241)"
              fill="rgb(99 102 241)"
              fillOpacity={0.4}
              isAnimationActive={false}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 text-xs text-slate-400">
        Pillars not shown: {footerSegments.join('; ')}.
      </p>
    </section>
  );
}
