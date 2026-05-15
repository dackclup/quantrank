"""Pydantic models for JSON output. Mirrors ``frontend/lib/types.ts`` exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Recommendation = Literal["bullish", "lean_bullish", "neutral", "cautious"]
"""4-tier recommendation per PR 4d (Option B locked 2026-05-14 — neutral
terminology, no FINRA/SEC-regulated sell-side labels). Derived
deterministically from composite + risk_flags + valuation_warnings +
fair_price MoS by `compute.scoring.recommendation.derive_recommendation`.
None on legacy data pre-PR-4d.
"""


class PillarScores(BaseModel):
    """Per-pillar 0-100 scores. Phase 3 introduces ``technical`` and
    ``profitability`` (additive — defaults to None for older data)."""

    model_config = ConfigDict(extra="forbid")

    quality: float | None = None
    value: float | None = None
    growth: float | None = None
    momentum: float | None = None
    health: float | None = None
    profitability: float | None = None
    technical: float | None = None
    risk: float | None = None
    sentiment: float | None = None
    ml: float | None = None


class PillarBaseline(BaseModel):
    """Sector-median overlay for the per-stock pillar bars (#34).

    Rendered as a vertical notch on each pillar bar + a header label
    (``"Information Technology median (n=72)"``) on the stock-detail
    page. The component (``frontend/components/PillarRadarChart.tsx``)
    keys ``values`` by the **display label** (``Quality``, ``Value``,
    ...), not the snake_case PillarScores field name, so the compute
    layer converts during aggregation.

    Sectors with fewer than ``PILLAR_BASELINE_MIN_PEERS`` (10) skip
    the overlay entirely — too few peers for a meaningful median.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    values: dict[str, float | None]


class StockSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    ticker: str
    name: str
    sector: str
    composite_score: float
    current_price: float
    fair_price: float | None = None
    max_fair_price: float | None = None
    margin_of_safety_pct: float | None = None
    pillar_scores: PillarScores = Field(default_factory=PillarScores)
    risk_flags: list[str] = Field(default_factory=list)
    valuation_warnings: list[str] = Field(default_factory=list)
    recommendation: Recommendation | None = None
    loss_chance_pct: float | None = None
    price_change_1d_pct: float | None = None
    entered_top5: bool = False
    exited_top5: bool = False


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    last_update_utc: str
    next_update_utc: str
    universe: str
    universe_size: int
    compute_run_id: str
    git_commit: str
    mos_trailing_ic_smoke: float | None = None
    tier2_coverage_pct: float | None = None
    fundamentals_coverage_pct: float | None = None
    fundamentals_latency_p50_seconds: float | None = None
    fundamentals_latency_p95_seconds: float | None = None


class RawMetrics(BaseModel):
    """Latest fundamentals — TTM for flow items, point-in-time for balance items."""

    model_config = ConfigDict(extra="forbid")

    revenue: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None
    cash: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    shares_outstanding: float | None = None
    market_cap: float | None = None
    pe_ratio_ttm: float | None = None
    goodwill: float | None = None


class DataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_metrics: list[str] = Field(default_factory=list)
    imputed_metrics: list[str] = Field(default_factory=list)
    filing_lag_days: int | None = None
    latest_period_end: str | None = None
    latest_filed_date: str | None = None


class StockDetail(BaseModel):
    """Full per-stock JSON written to ``frontend/public/data/stocks/{TICKER}.json``."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sector: str
    industry: str | None = None
    market_cap: float | None = None
    current_price: float
    rank: int
    composite_score: float
    pillar_scores: PillarScores = Field(default_factory=PillarScores)
    raw_metrics: RawMetrics = Field(default_factory=RawMetrics)
    fair_price: dict | None = None
    top5_factors: list = Field(default_factory=list)
    score_history: list = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    risk_flags: list[str] = Field(default_factory=list)
    valuation_warnings: list[str] = Field(default_factory=list)
    has_history: bool = False
    tangible_book_value: float | None = None
    tier2_events: dict | None = None
    pillar_baseline: PillarBaseline | None = None
    beneish_m_score: float | None = None
    dechow_f_score: float | None = None
    recommendation: Recommendation | None = None
    loss_chance_pct: float | None = None
    price_change_1d_pct: float | None = None
    entered_top5: bool = False
    exited_top5: bool = False
