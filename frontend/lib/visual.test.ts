/**
 * Contract tests for frontend/lib/visual.ts
 *
 * Guards the score-tier/MoS-bucket/sector/color helper functions against
 * regressions in boundary mapping, token vocabulary consistency, and
 * null-safety. These are the shared design-token functions consumed by
 * ScoreGauge, ScoreBadge, MoSCell, PillarRadarChart, SectorChip, and the
 * ranking table's sort/filter surfaces.
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import {
  TIERS,
  getTier,
  scoreTierLabel,
  MOS_BUCKETS,
  getMosBucket,
  sectorStyle,
  SECTOR_COLORS,
  scoreColorClasses,
  scoreAccentColor,
  pillarColor,
  mosVisualFraction,
  universeLabel,
  filingLagBadgeClasses,
  type ScoreTier,
} from './visual';

// ---------------------------------------------------------------------------
// TIERS vocabulary internal consistency
// ---------------------------------------------------------------------------

describe('TIERS — internal consistency', () => {
  it('has exactly 5 tiers', () => {
    expect(TIERS).toHaveLength(5);
  });

  it('each tier has a non-empty id, label, cls, and dot', () => {
    for (const t of TIERS) {
      expect(t.id.length, `tier "${t.id}" id`).toBeGreaterThan(0);
      expect(t.label.length, `tier "${t.id}" label`).toBeGreaterThan(0);
      expect(t.cls.length, `tier "${t.id}" cls`).toBeGreaterThan(0);
      expect(t.dot.length, `tier "${t.id}" dot`).toBeGreaterThan(0);
    }
  });

  it('every tier has a matching dark: variant in cls', () => {
    for (const t of TIERS) {
      expect(t.cls, `tier "${t.id}" cls must include a dark: variant`).toContain('dark:');
    }
  });

  it('every tier has a matching dark: variant in dot', () => {
    for (const t of TIERS) {
      expect(t.dot, `tier "${t.id}" dot must include a dark: variant`).toContain('dark:');
    }
  });

  it('tier ids match the canonical set', () => {
    const ids = TIERS.map((t) => t.id);
    expect(ids).toEqual(['exceptional', 'strong', 'average', 'weak', 'poor']);
  });

  it('tier min/max boundaries are contiguous (no gap, no overlap)', () => {
    // TIERS is ordered highest-tier-first (exceptional→strong→average→weak→poor).
    // Contiguity means each tier's MIN equals the next (lower) tier's MAX:
    //   exceptional.min(70) === strong.max(70)
    //   strong.min(55) === average.max(55) etc.
    for (let i = 0; i < TIERS.length - 1; i += 1) {
      expect(TIERS[i].min).toBe(TIERS[i + 1].max);
    }
  });

  it('the lowest tier starts at 0', () => {
    const poorTier = TIERS.find((t) => t.id === 'poor');
    expect(poorTier?.min).toBe(0);
  });

  it('the highest tier (exceptional) covers at least up to 100', () => {
    const excTier = TIERS.find((t) => t.id === 'exceptional');
    expect(excTier?.max).toBeGreaterThan(100);
  });
});

// ---------------------------------------------------------------------------
// getTier
// ---------------------------------------------------------------------------

describe('getTier — null / NaN / undefined inputs', () => {
  it('returns null for null', () => {
    expect(getTier(null)).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(getTier(undefined)).toBeNull();
  });

  it('returns null for NaN', () => {
    expect(getTier(NaN)).toBeNull();
  });
});

describe('getTier — score → tier mapping', () => {
  // Exceptional: 70 ≤ score < 101
  it('maps 70 → exceptional (min boundary)', () => {
    expect(getTier(70)).toBe('exceptional');
  });

  it('maps 100 → exceptional', () => {
    expect(getTier(100)).toBe('exceptional');
  });

  // Strong: 55 ≤ score < 70
  it('maps 55 → strong (min boundary)', () => {
    expect(getTier(55)).toBe('strong');
  });

  it('maps 69.9 → strong (just below exceptional)', () => {
    expect(getTier(69.9)).toBe('strong');
  });

  // Average: 40 ≤ score < 55
  it('maps 40 → average (min boundary)', () => {
    expect(getTier(40)).toBe('average');
  });

  it('maps 54.9 → average (just below strong)', () => {
    expect(getTier(54.9)).toBe('average');
  });

  // Weak: 25 ≤ score < 40
  it('maps 25 → weak (min boundary)', () => {
    expect(getTier(25)).toBe('weak');
  });

  it('maps 39.9 → weak (just below average)', () => {
    expect(getTier(39.9)).toBe('weak');
  });

  // Poor: 0 ≤ score < 25
  it('maps 0 → poor (min boundary)', () => {
    expect(getTier(0)).toBe('poor');
  });

  it('maps 24.9 → poor (just below weak)', () => {
    expect(getTier(24.9)).toBe('poor');
  });

  it('maps a midpoint in each tier correctly', () => {
    expect(getTier(85)).toBe('exceptional');
    expect(getTier(62)).toBe('strong');
    expect(getTier(47)).toBe('average');
    expect(getTier(33)).toBe('weak');
    expect(getTier(12)).toBe('poor');
  });
});

// ---------------------------------------------------------------------------
// scoreTierLabel
// ---------------------------------------------------------------------------

describe('scoreTierLabel — matches TIERS labels', () => {
  it('returns "Exceptional" for score in the exceptional range', () => {
    expect(scoreTierLabel(70)).toBe('Exceptional');
    expect(scoreTierLabel(85)).toBe('Exceptional');
  });

  it('returns "Strong" for score in the strong range', () => {
    expect(scoreTierLabel(55)).toBe('Strong');
    expect(scoreTierLabel(62)).toBe('Strong');
  });

  it('returns "Average" for score in the average range', () => {
    expect(scoreTierLabel(40)).toBe('Average');
    expect(scoreTierLabel(47)).toBe('Average');
  });

  it('returns "Weak" for score in the weak range', () => {
    expect(scoreTierLabel(25)).toBe('Weak');
    expect(scoreTierLabel(33)).toBe('Weak');
  });

  it('returns "Poor" for score in the poor range', () => {
    expect(scoreTierLabel(0)).toBe('Poor');
    expect(scoreTierLabel(12)).toBe('Poor');
  });

  it('falls back to "Poor" for a score that matches no tier (defensive)', () => {
    // A negative score hits no TIERS entry; the ?? 'Poor' fallback fires.
    expect(scoreTierLabel(-1)).toBe('Poor');
  });
});

// ---------------------------------------------------------------------------
// MOS_BUCKETS vocabulary internal consistency
// ---------------------------------------------------------------------------

describe('MOS_BUCKETS — internal consistency', () => {
  it('has exactly 3 buckets', () => {
    expect(MOS_BUCKETS).toHaveLength(3);
  });

  it('each bucket has a non-empty id, label, cls, and dot', () => {
    for (const b of MOS_BUCKETS) {
      expect(b.id.length).toBeGreaterThan(0);
      expect(b.label.length).toBeGreaterThan(0);
      expect(b.cls.length).toBeGreaterThan(0);
      expect(b.dot.length).toBeGreaterThan(0);
    }
  });

  it('bucket ids match the canonical set', () => {
    const ids = MOS_BUCKETS.map((b) => b.id);
    expect(ids).toEqual(['cheap', 'fair', 'over']);
  });

  it('every bucket cls has a dark: variant', () => {
    for (const b of MOS_BUCKETS) {
      expect(b.cls).toContain('dark:');
    }
  });
});

// ---------------------------------------------------------------------------
// getMosBucket
// ---------------------------------------------------------------------------

describe('getMosBucket — null / NaN / undefined inputs', () => {
  it('returns null for null', () => {
    expect(getMosBucket(null)).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(getMosBucket(undefined)).toBeNull();
  });

  it('returns null for NaN', () => {
    expect(getMosBucket(NaN)).toBeNull();
  });
});

describe('getMosBucket — MoS → bucket mapping', () => {
  // cheap: mos >= 10
  it('maps +10 → cheap (boundary)', () => {
    expect(getMosBucket(10)).toBe('cheap');
  });

  it('maps +50 → cheap', () => {
    expect(getMosBucket(50)).toBe('cheap');
  });

  it('maps +Infinity → null (range upper bound is exclusive: Infinity < Infinity is false)', () => {
    // MOS_BUCKETS uses Array.find with `mosPct >= b.range[0] && mosPct < b.range[1]`.
    // For the "cheap" bucket range[1] = Infinity: Infinity < Infinity = false, so no
    // bucket matches and getMosBucket returns null. This is the actual contract.
    expect(getMosBucket(Infinity)).toBeNull();
  });

  // fair: -10 <= mos < 10
  it('maps 0 → fair', () => {
    expect(getMosBucket(0)).toBe('fair');
  });

  it('maps +9.9 → fair (just below cheap)', () => {
    expect(getMosBucket(9.9)).toBe('fair');
  });

  it('maps −9.9 → fair (just above over)', () => {
    expect(getMosBucket(-9.9)).toBe('fair');
  });

  it('maps −10 → fair (lower range inclusive: range[0] = -10, mos >= -10)', () => {
    // The fair bucket range is [-10, 10]: mos >= -10 AND mos < 10.
    expect(getMosBucket(-10)).toBe('fair');
  });

  // over: mos < -10
  it('maps −10.1 → over (just below fair)', () => {
    expect(getMosBucket(-10.1)).toBe('over');
  });

  it('maps −50 → over', () => {
    expect(getMosBucket(-50)).toBe('over');
  });

  it('maps −Infinity → over', () => {
    expect(getMosBucket(-Infinity)).toBe('over');
  });
});

// ---------------------------------------------------------------------------
// sectorStyle
// ---------------------------------------------------------------------------

describe('sectorStyle — known sectors', () => {
  it('returns a non-empty dot for every GICS sector in SECTOR_COLORS', () => {
    for (const [sector, style] of Object.entries(SECTOR_COLORS)) {
      expect(style.dot.length, `sector "${sector}" dot`).toBeGreaterThan(0);
      expect(style.bg.length, `sector "${sector}" bg`).toBeGreaterThan(0);
      expect(style.fg.length, `sector "${sector}" fg`).toBeGreaterThan(0);
      expect(style.ring.length, `sector "${sector}" ring`).toBeGreaterThan(0);
    }
  });

  it('returns a style for "Information Technology"', () => {
    const s = sectorStyle('Information Technology');
    expect(s.dot).toContain('rgb(');
  });

  it('all 11 GICS sectors are present', () => {
    const expectedSectors = [
      'Information Technology',
      'Communication Services',
      'Consumer Discretionary',
      'Consumer Staples',
      'Energy',
      'Financials',
      'Health Care',
      'Industrials',
      'Materials',
      'Real Estate',
      'Utilities',
    ];
    for (const sector of expectedSectors) {
      expect(SECTOR_COLORS, `sector "${sector}" must be in SECTOR_COLORS`).toHaveProperty(sector);
    }
    expect(Object.keys(SECTOR_COLORS)).toHaveLength(11);
  });

  it('all sectors share the neutral chip body classes (LedgerCraft Phase 4 A1)', () => {
    for (const [sector, style] of Object.entries(SECTOR_COLORS)) {
      expect(style.bg, `sector "${sector}" bg`).toContain('bg-slate-100');
      expect(style.fg, `sector "${sector}" fg`).toContain('text-slate-600');
      expect(style.ring, `sector "${sector}" ring`).toContain('ring-slate-200');
    }
  });
});

describe('sectorStyle — unknown sector fallback', () => {
  it('returns a fallback slate-400 dot for an unknown sector', () => {
    const s = sectorStyle('Unknown Sector XYZ');
    expect(s.dot).toBe('rgb(148 163 184)');
  });

  it('fallback still has non-empty bg, fg, ring', () => {
    const s = sectorStyle('__nonexistent__');
    expect(s.bg.length).toBeGreaterThan(0);
    expect(s.fg.length).toBeGreaterThan(0);
    expect(s.ring.length).toBeGreaterThan(0);
  });

  it('fallback uses the same neutral chip body as known sectors', () => {
    const s = sectorStyle('__nonexistent__');
    expect(s.bg).toContain('bg-slate-100');
  });
});

// ---------------------------------------------------------------------------
// scoreColorClasses
// ---------------------------------------------------------------------------

describe('scoreColorClasses — tier mapping', () => {
  it('returns the solid-fill emerald for score >= 80', () => {
    const cls = scoreColorClasses(80);
    // Solid-fill is the exception for the top tier (legacy surface, pre-Rule-2).
    expect(cls).toContain('bg-emerald-600');
    expect(cls).toContain('text-white');
  });

  it('returns emerald outlined-light for 60 <= score < 80', () => {
    const cls = scoreColorClasses(60);
    expect(cls).toContain('bg-emerald-50');
    expect(cls).toContain('text-emerald-800');
  });

  it('returns amber for 40 <= score < 60', () => {
    const cls = scoreColorClasses(40);
    expect(cls).toContain('bg-amber-50');
    expect(cls).toContain('text-amber-800');
  });

  it('returns amber for 20 <= score < 40', () => {
    const cls = scoreColorClasses(20);
    expect(cls).toContain('bg-amber-50');
  });

  it('returns rose for score < 20', () => {
    const cls = scoreColorClasses(10);
    expect(cls).toContain('bg-rose-50');
    expect(cls).toContain('text-rose-800');
  });

  it('returns rose for score 0', () => {
    const cls = scoreColorClasses(0);
    expect(cls).toContain('bg-rose-50');
  });

  it('every output has a dark: variant (LedgerCraft paired rule)', () => {
    for (const score of [0, 20, 40, 60, 80, 100]) {
      const cls = scoreColorClasses(score);
      expect(cls, `scoreColorClasses(${score}) must contain dark:`).toContain('dark:');
    }
  });
});

// ---------------------------------------------------------------------------
// scoreAccentColor
// ---------------------------------------------------------------------------

describe('scoreAccentColor — returns an rgb() string', () => {
  const scores = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];

  it('always returns a non-empty rgb() string for in-range scores', () => {
    for (const s of scores) {
      const color = scoreAccentColor(s);
      expect(color, `scoreAccentColor(${s})`).toMatch(/^rgb\(/);
    }
  });

  it('returns the correct accent for score >= 80 (emerald strong)', () => {
    expect(scoreAccentColor(80)).toBe('rgb(5 150 105)');
    expect(scoreAccentColor(100)).toBe('rgb(5 150 105)');
  });

  it('returns emerald-ish for 60 <= score < 80', () => {
    expect(scoreAccentColor(60)).toBe('rgb(16 185 129)');
  });

  it('returns amber for 40 <= score < 60', () => {
    expect(scoreAccentColor(40)).toBe('rgb(245 158 11)');
  });

  it('returns orange for 20 <= score < 40', () => {
    expect(scoreAccentColor(20)).toBe('rgb(180 83 9)');
  });

  it('returns rose for score < 20', () => {
    expect(scoreAccentColor(0)).toBe('rgb(225 29 72)');
    expect(scoreAccentColor(19)).toBe('rgb(225 29 72)');
  });
});

// ---------------------------------------------------------------------------
// pillarColor — uses TIERS composite boundaries (70/55/40/25)
// ---------------------------------------------------------------------------

describe('pillarColor — composite-TIERS boundary alignment', () => {
  // pillarColor uses the same 70/55/40/25 boundaries as TIERS (the P3
  // consolidation invariant). Tests lock this alignment structurally.

  it('maps v >= 70 → same rgb as scoreAccentColor(80)', () => {
    // Both use emerald-600 territory (rgb(5 150 105)).
    expect(pillarColor(70)).toBe('rgb(5 150 105)');
    expect(pillarColor(100)).toBe('rgb(5 150 105)');
  });

  it('maps 55 <= v < 70 → lighter emerald', () => {
    expect(pillarColor(55)).toBe('rgb(16 185 129)');
    expect(pillarColor(65)).toBe('rgb(16 185 129)');
  });

  it('maps 40 <= v < 55 → amber', () => {
    expect(pillarColor(40)).toBe('rgb(245 158 11)');
    expect(pillarColor(47)).toBe('rgb(245 158 11)');
  });

  it('maps 25 <= v < 40 → dark amber / orange', () => {
    expect(pillarColor(25)).toBe('rgb(180 83 9)');
    expect(pillarColor(33)).toBe('rgb(180 83 9)');
  });

  it('maps v < 25 → rose', () => {
    expect(pillarColor(0)).toBe('rgb(225 29 72)');
    expect(pillarColor(24)).toBe('rgb(225 29 72)');
  });

  it('boundaries match getTier() vocabulary thresholds', () => {
    // Confirm that pillarColor boundaries are the same as TIERS min values,
    // locking the §Gotchas "PillarRadarChart shares the composite TIERS vocab" invariant.
    const tierMins = TIERS.map((t) => t.min).filter((m) => m > 0); // [70, 55, 40, 25]
    // Each min is the inflection point in pillarColor:
    expect(pillarColor(tierMins[0])).toBe('rgb(5 150 105)');   // 70 → exceptional rgb
    expect(pillarColor(tierMins[1])).toBe('rgb(16 185 129)');  // 55 → strong rgb
    expect(pillarColor(tierMins[2])).toBe('rgb(245 158 11)');  // 40 → average rgb
    expect(pillarColor(tierMins[3])).toBe('rgb(180 83 9)');    // 25 → weak rgb
  });
});

// ---------------------------------------------------------------------------
// mosVisualFraction
// ---------------------------------------------------------------------------

describe('mosVisualFraction — null / NaN / undefined inputs', () => {
  it('returns null for null', () => {
    expect(mosVisualFraction(null)).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(mosVisualFraction(undefined)).toBeNull();
  });

  it('returns null for NaN', () => {
    expect(mosVisualFraction(NaN)).toBeNull();
  });
});

describe('mosVisualFraction — mapping to [0, 1]', () => {
  it('maps 0 → 0.5 (center)', () => {
    expect(mosVisualFraction(0)).toBeCloseTo(0.5);
  });

  it('maps +100 → 1.0 (full positive)', () => {
    expect(mosVisualFraction(100)).toBeCloseTo(1.0);
  });

  it('maps −100 → 0.0 (full negative)', () => {
    expect(mosVisualFraction(-100)).toBeCloseTo(0.0);
  });

  it('clamps values > 100 to 1.0', () => {
    expect(mosVisualFraction(200)).toBeCloseTo(1.0);
    expect(mosVisualFraction(Infinity)).toBeCloseTo(1.0);
  });

  it('clamps values < −100 to 0.0', () => {
    expect(mosVisualFraction(-200)).toBeCloseTo(0.0);
    expect(mosVisualFraction(-Infinity)).toBeCloseTo(0.0);
  });

  it('maps +50 → 0.75', () => {
    expect(mosVisualFraction(50)).toBeCloseTo(0.75);
  });

  it('maps −50 → 0.25', () => {
    expect(mosVisualFraction(-50)).toBeCloseTo(0.25);
  });
});

// ---------------------------------------------------------------------------
// universeLabel
// ---------------------------------------------------------------------------

describe('universeLabel', () => {
  it('maps "SP500" → "S&P 500"', () => {
    expect(universeLabel('SP500')).toBe('S&P 500');
  });

  it('maps "SP900" → "All US stocks"', () => {
    expect(universeLabel('SP900')).toBe('All US stocks');
  });

  it('passes through an unknown code unchanged (forward-compat fallback)', () => {
    expect(universeLabel('SP400')).toBe('SP400');
    expect(universeLabel('CUSTOM')).toBe('CUSTOM');
  });
});

// ---------------------------------------------------------------------------
// filingLagBadgeClasses
// ---------------------------------------------------------------------------

describe('filingLagBadgeClasses — null input', () => {
  it('returns the neutral slate class for null days', () => {
    const cls = filingLagBadgeClasses(null);
    expect(cls).toContain('bg-slate-100');
    expect(cls).toContain('dark:');
  });
});

describe('filingLagBadgeClasses — tier mapping', () => {
  it('returns emerald for < 60 days (fresh filing)', () => {
    const cls = filingLagBadgeClasses(0);
    expect(cls).toContain('bg-emerald-50');
    const cls59 = filingLagBadgeClasses(59);
    expect(cls59).toContain('bg-emerald-50');
  });

  it('boundary at 60: 60 is NOT < 60, so amber applies (60 ≤ days < 180)', () => {
    const cls = filingLagBadgeClasses(60);
    expect(cls).toContain('bg-amber-50');
  });

  it('returns amber for 60 <= days < 180', () => {
    expect(filingLagBadgeClasses(90)).toContain('bg-amber-50');
    expect(filingLagBadgeClasses(179)).toContain('bg-amber-50');
  });

  it('returns red for days >= 180', () => {
    const cls = filingLagBadgeClasses(180);
    expect(cls).toContain('bg-red-50');
    expect(filingLagBadgeClasses(365)).toContain('bg-red-50');
  });

  it('every output has a dark: variant', () => {
    for (const days of [null, 0, 59, 60, 179, 180, 365]) {
      const cls = filingLagBadgeClasses(days);
      expect(cls, `filingLagBadgeClasses(${days}) must contain dark:`).toContain('dark:');
    }
  });
});
