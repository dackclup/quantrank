# QuantRank — Gotchas (code & domain invariants)

> Full detail for every invariant indexed in CLAUDE.md §Gotchas. CLAUDE.md keeps the
> one-line index (always-loaded); this file holds the detail (load on demand, before
> touching the file/area a gotcha names). Drained 2026-06-03 to shrink always-loaded context.

- **`compute/cache/` is gitignored.** Cold-cache compute runs hit SEC
  EDGAR live and can take 25-50 min depending on throttling. Warm-cache
  runs finish in under 5 min.
- **`shares_outstanding` is wrong for ~12 tickers** (issue #10) — Step
  7.5 sanity guard fires `data_quality_input_corruption` on the worst
  cases (issue #18 closed: this flag is a veto now). A separate
  **partial-extraction** failure mode — `shares_outstanding=None`
  despite company-level revenue + balance sheet being present (STZ
  2026-05-14 pattern, issue #176) — surfaces via the
  `share_count_extraction_missing` annotate (PR #181) AND has a live
  recovery path via `_fetch_shares_from_per_filing_xbrl` (PR #182).
  Root cause: SEC's `companyfacts` aggregate API filters out
  dimensional facts; STZ files share counts only with Class A /
  Class B dimensions. The fallback pulls per-filing XBRL
  (`Filing.xbrl().facts.get_facts_by_concept`) for the most recent
  10-K / 10-Q and sums the dimensional `dei:EntityCommonStockSharesOutstanding`
  contexts. Triggered ONLY when the primary extraction returns
  ``None`` AND `revenue > 0` AND `total_assets > 0` (PR-#181
  signature). **Cron-#3 silent-failure gap closed on this PR**:
  PR #182's outer `except: return None` was bare — when the fallback
  failed under cron load (2026-05-23 STZ regression: worked in
  2026-05-21 live probe, returned None two days later under SEC 429),
  the operator had no log line distinguishing transient 429 from
  structural XBRL drift. This PR threads `ticker` into
  `_fetch_shares_from_per_filing_xbrl` and emits `logger.warning(...
  shares_outstanding fallback FAILED ...)` on the outer except;
  inner exceptions log at `DEBUG`. Annotate
  `share_count_extraction_missing` keeps firing as the safety net.
- **Dual-class `shares_outstanding` = COMPANY-TOTAL across all classes
  (ASC 260 / RATIFY-B, issue #374, 2026-06-11) — NOT the listed line's
  per-class float.** Distinct from the ~12-ticker partial-extraction (`=None`)
  mode above: this is a multi-class *convention* bug. Six S&P 500 tickers are
  two listed classes of one issuer sharing one SEC CIK — Alphabet GOOG (Class C)
  / GOOGL (Class A) + the unlisted Class B, Fox FOX/FOXA, News Corp NWS/NWSA
  (`MULTI_CLASS_OVERCOUNT_ALLOWLIST` in `compute/config.py`). The fundamentals
  parquet cache is keyed by CIK (`compute/cache/fundamentals/<CIK>.parquet`), so
  **both tickers of a pair share one cache file**. PR #269 made Branch 3 of
  `_build_snapshot` (`compute/ingest/fundamentals.py`) OVERWRITE
  `shares_outstanding` with the listed line's *per-class* count — which (a) is a
  category error for the per-share chain (company-level NI ÷ one class's count
  overstates EPS ~2.2×: GOOGL showed EPS 29.46 vs Alphabet's own filed
  ≈13.2 = NI/12.088B; P/E 12.3 vs the ~27 the market prices), and (b) on warm
  crons the CIK-shared parquet served whichever ticker wrote last (last-writer
  race → 9/11 cron commits served GOOG's Class C count to *both* lines).
  **RATIFY-B fix**: `shares_outstanding` reverts to the SEC companyfacts
  COMPANY-TOTAL aggregate (the value before the #269 override) — which is
  *class-invariant*, so the CIK-keyed cache collision **can no longer corrupt
  it** (the structural close of #374, not just a re-pin). ASC 260: basic EPS
  divides company income by *total* weighted-avg shares across all classes; the
  two-class method triggers only on different *distribution* rights (voting
  differences never trigger it). The listed line's per-class count moves to the
  additive `RawMetrics.shares_outstanding_listed_class` (`schemas.py`) —
  checksum / detail-page display only, **no scoring/valuation consumer**, and
  populated cold-path-only (may be `None` on warm crons; harmless). All
  per-share + market-cap consumers (EPS/BVPS/TBVPS, P/E·P/B·P/S·EV-family,
  market_cap, NSI, Dechow issuance) read the company-total. Series-consistency
  SELF-HEALS: NSI (`_net_stock_issuance`) + the Dechow 1%-YoY issuance dummy
  (`_issuance_dummy`) read share-count *history* that is ALSO the companyfacts
  aggregate, so reverting does not fabricate a one-time ln(5.4B/12.1B)≈−0.80
  "dilution" spike (invariant comments added at both sites). Effect of the fix:
  GOOGL ~7% EPS/fair-price overstatement removed (rank 42→~85, GOOG converges
  adjacent — both honest, *artifact removal* not regression); NWS/NWSA/FOX/FOXA
  *unchanged* (their aggregate counts were accidentally ASC-260-correct, so the
  rejected RATIFY-A per-class alternative would have standardized the artifact
  onto four more lines). Scope: ratio-1 classes only — BRK-B (1500:1 economic
  ratio) stays deferred per the existing `config.py` caveat. **Deploy caveat:
  the source fix is latent on warm crons until a cache-key bump / cold backfill
  repopulates the 6 tickers' parquets** (PR #298 cache-v5 was the precedent
  workaround). Spun off **#455** (Phase 7.1 CIK-level Top-N dedup — once GOOG &
  GOOGL converge to adjacent ranks a Top-N portfolio can hold doubled
  single-issuer Alphabet exposure; inverse-vol won't dedupe ~0.99-correlated
  lines).
- **`eps_basic` / `eps_diluted` display fields now derive from
  `NI_TTM / shares_outstanding`** (DD cron-#3 fix) — `compute/main.py`
  `_build_raw_metrics` previously passed `snapshot.eps_diluted`
  (XBRL `EarningsPerShareDiluted` concept) raw to `RawMetrics`. That
  concept returns the **latest single-period value** per
  `fundamentals.py:114-117` — for a quarterly filer that's one
  quarter's EPS, NOT TTM. DD on the 2026-05-23 cron showed
  `eps_diluted=0.39` against `net_income=$7M / shares=410M = $0.017`
  (~23× off). The valuation chain (`pe_ratio_ttm`) was already on
  the NI/shares path since audit #6 / PR #49, so internal consistency
  held — but `/stock/DD` rendered the wrong EPS to users. This PR
  computes `ttm_eps = NI / shares` once and uses it for BOTH
  `eps_basic` and `eps_diluted` display fields (basic-vs-diluted
  spread on the S&P 500 is typically < 1-3%, within display
  precision). `pe_ratio_ttm` formula unchanged.
- **`_avg_3y_roe` fallback removed** (issue #11, 2026-05-21) — PR 4c
  earlier added the per-year stockholders_equity denominator path but
  kept a fallback to single-period equity when history was incomplete,
  preserving the original bug for ~30% of the universe. This PR drops
  the fallback (returns `None` instead) AND introduces a distinct
  `insufficient_history_for_roe` skip reason so the ensemble doesn't
  emit a spurious `value_trap_risk` warning when RIM is skipped for
  missing data. Tickers with < 3y of equity history lose RIM as an
  applicable method; the 5 other valuation methods still cover them.
- **Going-concern phrase scan FP rate dropped to 1.0%** on the
  2026-05-20 cron (within Mayew 2015 expected 1-3% band, down from
  10.8% pre-Phase-4h). Mechanism not yet code-confirmed — issue #16
  negation lookbehind may have been side-effect-fixed by the Tier-2
  8-K scan integration. Verify root cause + decide whether to close
  issue #16 at the Q3 cohort audit (2026-08-19).
- **`loss_avoidance_pattern` thresholds rescaled** (Phase 2.4,
  2026-05-21) — Burgstahler-Dichev 1997 cohort thresholds were
  rescaled 10× to S&P 500 scale (NI ≤ $50M / EPS ≤ $0.50) after
  Phase 4.5d's original $5M / $0.05 fired 0% on the universe.
  Annotate-only — composite rank unaffected. Phase 4b
  (2026-05-21) closed the size-invariance follow-up by adding the
  sibling annotate `loss_avoidance_pattern_size_invariant`
  (Roychowdhury 2006 *JAE* §5.2 suspect-firm:
  ``NI / TotalAssets ∈ [0, 0.005]`` for 3+ consecutive years).
  Both flags ship side-by-side annotate-only pending the Q3
  2026-08-19 quarterly-audit decision (retire one, keep both,
  or split weights vs `rem_suspect` which shares the Roychowdhury
  paper anchor but a different sub-trigger).
- **Hypothesis property-based tests** are the new defense line for
  data-shape bugs (issue #126). Pair each new shape assumption (port
  cardinality, pillar count, manifest partition) with a `@given`
  property in `tests/**/test_*_properties.py`. Don't use
  `@settings(deadline=None)` — a slow example is itself a signal.
- **CI escape-hatch env-var combo for simulate** (5 vars, all set
  together in `.github/workflows/pre-merge-prod-sim.yml`; NONE set in
  weekly cron `compute-rankings.yml`): `FORM4_FETCH_SKIP=1` (skip Form-4
  bulk fetch — read at `compute/main.py:959`; safe empty default),
  `QR_SKIP_TIER2=1` (skip Tier-2 10-K text + 8-K fetch — read at
  `compute/scoring/tier2.py:162`), `QR_SKIP_FUNDAMENTALS=1` (skip
  fundamentals freshness gate — read at `compute/ingest/fundamentals.py`
  in BOTH `fetch_fundamentals` + `fetch_fundamentals_history` BEFORE
  `_require_identity()`), `QR_SKIP_OSAP=1` (skip OSAP openassetpricing.com
  bulk download — read at `compute/ingest/osap.py:fetch_osap_returns`
  BEFORE the `_is_fresh` check), and `QR_SKIP_CROSS_SOURCE=1` (skip
  the 502-ticker yfinance.info cross-source validation loop — read at
  `compute/ingest/cross_source.py:fetch_yfinance_market_cap` at the
  TOP of the function; bypasses 24h cache TTL on stale-but-present
  entries; returns None on cache-miss). Each falls through to live
  fetch if no cached parquet exists, or to "no validation possible"
  in the cross-source case. Together they cover the FIVE independent
  external-data loops in `compute/main.py` — the four discovered by
  PR #230's iteration plus the 5th (cross_source yfinance.info)
  identified by PR #241's ci-triage-engineer session-6 root-cause.
  CI-only — never set in cron / local dev. Simulate workflow
  expected steady-state with all five skips active on a warm-cache
  restore: 8-15 min (vs the pre-fix 45-min cap breach across PRs
  #230 / #238 / #241).
- **The cron cache is split into TWO `actions/cache` steps (don't
  re-merge): fast (quarter-key) + slow-text (run-id key)** (2026-06-06,
  edgar-debugger root-cause). The original SINGLE 11-path bundle
  (~250-500 MB) was too large to save reliably in the post-job window
  once the job ran 100-180 min — the save truncated and the largest
  layers (`edgar_10k_text` ~50-150 MB, `edgar_8k`) never persisted, so
  the next run restored an older bundle WITHOUT them → Tier-2 ran COLD
  (~80 min full SEC re-fetch) → runtime climbed → next save failed
  again: a self-reinforcing cold-cache trap (cron #82 evidence:
  `fundamentals_latency_p95`=11.3s = warm, but `tier2_wall_clock`=4836s
  = 80.6 min = cold). Fix = two INDEPENDENT caches in
  `compute-rankings.yml`: (1) **fast** — `fundamentals` /
  `fundamentals_history` / `prices` / `universe` / `yfinance_info` /
  `edgar_form4`, key `cache-v6-fast-<quarter>-<os>` (bumped v5→v6
  2026-06-08 to invalidate the PERIOD-BLIND 5y price + fundamentals_history
  parquets when `PRICES_PERIOD`/`ANNUAL_HISTORY_YEARS` went 10y — the cache key
  carries no period, so a value change is invisible to it without a vN bump;
  fundamentals freshness via `_is_fresh()`); (2) **slow-text** —
  `edgar_10k_text` / `edgar_8k` / `edgar_amendments` /
  `edgar_late_filings` / `osap`, key `cache-v5-text-<os>-<run_id>` with
  `restore-keys: cache-v5-text-<os>-`. The run-id key is deliberate —
  a unique key per run means `actions/cache` never SKIPS the save on
  immutability, so this run's freshly-fetched text always persists, and
  the prefix `restore-keys` restores the most-recent prior good save.
  Do NOT collapse back to one bundle, and do NOT switch the text key to
  a static `cache-v5-text-<os>` (that freezes the cache → a 90-day
  cliff when the cached 10-K text ages past its TTL with no re-save).
  Paired with `EDGAR_8K_CACHE_TTL_SECONDS` 7→6 days (a 7-day TTL equals
  the weekly cron cadence → boundary re-fetch on drift). Bump `-fast-`
  vN per the schema/value-correctness taxonomy in the YAML comment;
  bump `-text-vN` only on a text-cache schema change.
- **GitHub-Actions-injected env-vars `GITHUB_RUN_ID` + `GITHUB_SHA`**
  — auto-provided by the GitHub Actions runner; read at
  `compute/main.py:2084-2085` via `os.environ.get(...)` with safe
  empty defaults; surface into `Metadata.compute_run_id` +
  `Metadata.git_commit` for downstream audit trail (verify-helper
  Section A reads both). Not operator-managed — no value to redact.
  Listed here so the env-var inventory of CLAUDE.md §Gotchas stays
  exhaustive (security-reviewer 2026-05-28 baseline flagged the doc
  gap as W1).
- **`IMPECCABLE_NO_UPDATE_CHECK` + `IMPECCABLE_UPDATE_HOST`** (vendored
  `impeccable` skill, 2026-06-01) — read by
  `.agents/skills/impeccable/scripts/context.mjs`, which makes a once-daily
  `GET https://impeccable.style/api/version` version check when the skill's
  Setup step runs in a dev agent session. The request sends NO repo content /
  paths / env / tokens (security-reviewer verified 2026-06-01) — only a version
  probe. `IMPECCABLE_NO_UPDATE_CHECK=1` disables the phone-home entirely;
  `IMPECCABLE_UPDATE_HOST` overrides the host (both fully offline-capable).
  These are NOT operator-managed in CI — the skill's `scripts/` NEVER run in CI
  / the Vercel static export / the compute cron (no `package.json`, no install
  hooks), so there is nothing to set or redact there. Separately, the skill's
  `live` "Apply" feature spawns a `claude` subprocess with `--permission-mode
  bypassPermissions` (writes source files without per-op prompts) — expected for
  that workflow, dev-session only. Full posture in
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) §pbakaus/impeccable.
- **`Metadata.*_wall_clock_seconds` ≠ `fundamentals_latency_p95_seconds`**
  (Issue #287 PR A, 0.10.9-phase4.6) — they look like sibling latency
  metrics but measure ORTHOGONAL things and BOTH are needed for cron
  diagnostics. `fundamentals_latency_p95_seconds` = p95 of per-ticker
  fetch times collected in the `fundamentals_latency` dict (tenacity-
  cascade detector — useful for spotting per-ticker slowness or SEC
  CIK-specific weirdness even when the loop wall-clock looks fine).
  `tier2_wall_clock_seconds` / `form4_wall_clock_seconds` /
  `osap_wall_clock_seconds` / `cross_source_wall_clock_seconds` = total
  elapsed wall-clock for the entire loop start-to-end via
  `time.monotonic()` (budget-overrun + cache-eviction detector). On a
  warm cache the wall-clock may be 5-10s while p95 is 15s+ (most
  tickers return instantly; a handful spike). On cold + throttled the
  wall-clock can be 30+ min while p95 only reaches 30s (slow tickers
  serialize through the thread pool). **None semantic varies per loop**:
  `FORM4_FETCH_SKIP=1` → `form4_wall_clock_seconds = None` (start marker
  is INSIDE the `else:` branch). `QR_SKIP_OSAP=1` → `osap_wall_clock_seconds`
  populates a SMALL FLOAT (~0.5-2s; only the freshness gate is bypassed,
  not the try block). `QR_SKIP_TIER2=1` → `tier2_wall_clock_seconds`
  populates a small float (each worker returns ~0ms). Outer-try failure
  on any loop → `None`. `cross_source_wall_clock_seconds` measures the
  ENTIRE Step 8 per-ticker loop (fair-price + manipulation + StockDetail
  write), not just the cross-source sub-calls — documented limitation;
  on cold the cross-source dominates, on warm the rest does.
- **Sub-agent `tools:` frontmatter does NOT auto-inherit MCP tools**
  — surfaced 2026-05-23 by the post-PR-#225 live-fire of
  `vercel-preview-auditor`. The Claude Code sub-agent runtime restricts
  each sub-agent's tool surface to what's listed explicitly in the
  agent file's `tools:` field; MCP tools must be enumerated by their
  full name (`mcp__<server>__<tool>`). The GitHub MCP server uses a
  stable `mcp__github__*` namespace, but OAuth connectors like Vercel /
  Supabase / Sentry register under an OAuth-connection UUID
  (`mcp__0addee55-...__list_deployments`) that is **install-specific**
  — a fresh clone by a different user would have a different UUID and
  the agent's pinned tool list would silently fail to match. Both
  affected agents (`vercel-preview-auditor` + `ci-triage-engineer`)
  now carry a hard-constraint bullet that requires explicit gap
  surfacing + main-agent escalation when the listed MCP tools aren't
  reachable in the sub-agent's context. The main agent retains full
  MCP access and can run the check inline OR re-spawn the sub-agent
  with the correct tool surface.
- **Release tags are mobile-only (locked 2026-05-27)** — the user
  operates GitHub from a phone only; no desktop, no `gh` CLI, no
  terminal. The sandbox itself **cannot push tag-refs** either
  (HTTP 403 from the git proxy — confirmed during the v1.3.0 +
  v1.4.0 cut on 2026-05-27). All release-tag + GitHub-Release-
  creation steps MUST be delivered as **pre-filled GitHub URLs the
  user taps once**, never as `git tag` / `git push origin <tag>` /
  `gh release create` shell commands. Pattern: build a single URL of
  the shape `https://github.com/dackclup/quantrank/releases/new?tag=<TAG>&target=<40-char-SHA>&title=<URL-ENC>&body=<URL-ENC>`
  with a **short body** (≤ 2 KB encoded) that links to the full
  release notes file already on `main` — the URL must stay under
  GitHub's 8 KB server-side limit. Multi-release ladder ordering:
  **publish newest FIRST with "Set as latest" ✅, retroactive/older
  LAST with "Set as latest" ❌** — avoids the auto-flag-latest
  footgun caught on 2026-05-27 (v1.3.0 retroactive accidentally
  became Latest until manually re-promoted via the edit URL).
  Codified in [`.claude/skills/release-tag/SKILL.md`](.claude/skills/release-tag/SKILL.md)
  §"Mobile-operator release workflow" + [`.claude/agents/release-captain.md`](.claude/agents/release-captain.md)
  Step 5.
- **Parallel-PR §Phase status collision pattern** (RESOLVED
  2026-05-24 via [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)
  side-file adoption) — historical record: every PR was required to
  add a §Phase status entry to CLAUDE.md + AGENTS.md per the
  §Conventions "ship with every PR" rule. The pre-2026-05-24
  structure inserted every "in flight" bullet at the SAME line
  (just before "**Next deliverables**"). Two PRs opened in parallel
  both targeted that line → second-to-rebase hit
  `mergeable_state: dirty` → the recurring
  "merge ไม่ได้ หลังแก้แล้วกลับมาเป็นอีก" pattern. PR #230
  (`docs(form4)+ci(simulate)`) hit this **3 times in one session**
  while iterating on the simulate-cap fix (vs PR #229, then PR
  #232 + #233, then PR #234 + #235 + #236). Structural fix landed
  in this PR: new in-flight entries go in `PHASE_STATUS_INFLIGHT.md`
  (append-only-per-PR; parallel PRs touch disjoint last-lines and
  `git merge` auto-resolves). CLAUDE.md §Conventions updated to
  point at the side-file as the canonical destination. The
  rebase-before-Mark-Ready discipline still applies for OTHER
  conflict surfaces (shared code edits, workflow YAML, schema
  bumps) but is no longer the recurring drag it used to be.
  Housekeeping workflow to drain merged entries from
  `PHASE_STATUS_INFLIGHT.md` into CLAUDE.md §Phase status proper
  deferred (manual cleanup is fine for the first few weeks while
  the pattern proves itself; `tools/housekeep_phase_status.py`
  may land later once volume + shape are known).
- **Lint the WHOLE repo before push, never per-file** (recorded
  2026-05-29 after PR #310 went CI-red on a self-inflicted lint
  miss). The §Commands verification ladder already says
  `ruff check .` — the trap is running `ruff check <changed-file>`
  instead, to "save time" on a focused diff. It silently passes
  while a DIFFERENT file fails. The PR #310 failure mode: commit 1
  changed two `compute/` files (I linted just those two — clean);
  commit 2 added a test file with two `UP037` redundant-quote
  annotations (`df: "pd.DataFrame"` under `from __future__ import
  annotations`) — never linted locally because it wasn't in my
  per-file list. CI runs `ruff check .` and caught it instantly.
  **Correct procedure**: run `ruff check .` (no path argument) as
  the LAST step before every `git push`, especially on a multi-
  commit branch where a later commit adds files the earlier
  per-file pass never saw. Per-file `ruff check <f>` is fine for
  fast inner-loop iteration, but it is NOT the pre-push gate — the
  pre-push gate is the full ladder verbatim. Same discipline for
  `pytest -m "not network"` (whole suite, not just the one test
  file you touched) — a verbatim-copy test helper or a cross-module
  import can fail elsewhere.
- **`html, body` are globally `overflow-x: clip`** (`frontend/app/globals.css`,
  PR #322). Keep `clip` — NOT `hidden`: both stop the page from widening, but
  `clip` creates NO scroll container, so the `position: sticky` header keeps working (`overflow: hidden` would break it). Consequence:
  page-level horizontal scroll is intentionally impossible — a genuinely wide
  surface must nest its OWN scroll container (`overflow-x-auto` on the inner
  element, as `RankingTable`'s desktop table does), never rely on the page
  scrolling. Why it exists: the price-chart `AreaChart` remount (crosshair
  re-park on release) transiently overflowed, and the `fixed inset-0` sidebar backdrop (the sidebar has since been removed) then sized itself to the widened layout viewport and SUSTAINED it
  as phantom right-side scroll (only reproducible under mobile emulation — a
  plain desktop viewport hid it). `overflow: clip` is Safari 16+ / Chrome 90+;
  pre-Safari-16 silently degrades to the prior behavior (not a regression,
  just unfixed on that old sliver).
- **Root font-size is FLUID** (`frontend/app/globals.css` `html { font-size:
  clamp(1rem, 0.89rem + 0.45vw, 1.125rem) }`, 2026-05-29). The whole app is
  rem-based (Tailwind `text-*` / spacing / gaps / chart `h-64` all in rem), so
  the root font-size scaling with the viewport scales EVERYTHING proportionally
  — ~16px on phones (≤~390px, the clamp floor) → ~18px on tablet+ (the ceiling
  engages ~835px; lowered from 20px per the 2026-05-29 layout-density audit). Consequences for future code: (a) use rem-based Tailwind text
  utilities (`text-sm`, `text-2xl`, …) so new text scales with the system —
  an arbitrary `text-[14px]` is a FIXED px that will NOT scale and will drift
  out of proportion on desktop; (b) do NOT add a second `font-size` on `html`
  / `:root` / `body` (a `font-size` on `body` would re-resolve `rem` against
  the already-fluid `html` and compound the scale); (c) the `rem` terms in the
  `clamp` (not pure `vw`) are intentional — they keep browser zoom / user
  font-size prefs working (pure-vw font-size breaks WCAG 1.4.4 resize). A few
  chart-internal SVG labels sized in raw px (Recharts `tick fontSize`) are a
  known minor holdout — they don't follow the rem scale.

- **Re-parking the price-chart crosshair MUST debounce the `<AreaChart>`
  remount ≥ ~300ms** (`frontend/components/PriceHistoryChart.tsx`, PR #326).
  Recharts 2.15 applies `defaultIndex` (latest-point park) only on MOUNT. A
  WIDTH change — window resize or device rotation — makes `ResponsiveContainer` re-measure over
  ~100-200ms. Bumping the `<AreaChart key>` remount key immediately re-parks
  against the OLD width → the crosshair lands at index 0 (far LEFT). A
  width-delta `ResizeObserver` debounced ~300ms lands the remount AFTER the
  re-measure so it re-parks at the latest point. Shorten / remove the debounce
  → the "crosshair jumps left on resize/rotation" regression returns. This
  ResizeObserver subsumes the old orientation-only `matchMedia` re-park
  (rotation changes width too).
- **App-wide motion uses ONE `ease-in-out` timing curve** (2026-05-30,
  PR #330). Every discrete move / entrance / slide / sweep accelerates out
  of the start and decelerates into the end — one calm, symmetric feel across
  the whole app. Concretely: `tailwind.config.ts` `animation` (`fade-in` /
  `rise-in` / `chip-pop` / `flag-pulse`), `globals.css` `.gauge-sweep` +
  `.hover-lift`, and the JS rAF easings in `PriceHistoryChart.tsx` (intro sweep)
  + `useMotion.ts` (`useCountUp`) all use `ease-in-out` — the CSS keyword /
  Tailwind `ease-in-out` class / `easeInOutCubic = t<0.5 ? 4t³ :
  1−(−2t+2)³/2` in JS. A NEW animated component MUST follow suit — do not
  introduce a one-off `ease-out` / `ease-in` / `cubic-bezier`. TWO deliberate
  carve-outs: (1) `shimmer` stays `linear infinite` — ease-in-out on a
  seamless background-position loop stutters at the wrap boundary (slow-end
  meets slow-start = a visible stall); (2) a bare Tailwind `transition-*`
  with no explicit `ease-*` already compiles to `cubic-bezier(0.4,0,0.2,1)`
  ≈ ease-in-out, so it needs no change. `chip-pop`'s overshoot (70% → 1.04)
  and `flag-pulse`'s settle (55% → 1.012) now live entirely in the keyframe
  %-stops, not the timing curve — the curve just eases into them. The
  `@media (prefers-reduced-motion: reduce)` guard in `globals.css` still
  neutralizes every one of these.

- **The stock-detail hero splits on a CSS CONTAINER QUERY, not a viewport
  breakpoint** (`frontend/app/stock/[ticker]/page.tsx` + `frontend/app/globals.css`
  `.hero-card` / `@container hero (min-width: 46rem)`, PR #332). The hero lays
  out name-block-left / stats-block-top-right when there's room and falls back
  to the vertical mobile-portrait stack when squeezed — but the decision is
  driven by the hero's OWN inline-size (`container: hero / inline-size` on the
  `<header>`), NOT `md:`/`lg:` viewport prefixes. **Why it must stay a container query**: the hero card's real available width depends on the surrounding layout — a viewport `md:`/`lg:` gate is brittle to future layout-chrome changes.
  The container query measures the space the hero actually has, so the row engages exactly when both columns fit. Consequences
  for future edits: (a) the JSX default classes are the STACKED `flex flex-col`
  (`hero-split` / `hero-left` / `hero-right`); the `@container` rule only ADDS
  the row behavior, so pre-2023 browsers without `@container` degrade to the
  safe stack — do NOT "simplify" the hooks back to `md:flex-row`; (b) the 46rem
  threshold ≈ left name block + the ~18rem stats block + gap headroom — retune it against the live layout, not just one viewport; (c) `@container` is
  raw CSS in `globals.css` (no `@tailwindcss/container-queries` plugin / no new
  dep — Tailwind compiles the raw rule through fine, verified in the built CSS).
- **MoS gauge arc direction is SIGN-AWARE** (`frontend/components/MoSBadge.tsx`,
  PR #332). The Margin-of-Safety donut shares `ScoreGauge`'s sweep + count-up
  motion, but unlike the score (0–100, always clockwise) MoS is signed:
  **MoS ≥ 0 sweeps clockwise** (same as the score gauge — upside reads like a
  high score); **MoS < 0 sweeps counter-clockwise** (overvalued visibly "runs
  the other way"). The reversal is a `-scale-x-100` on the gauge CONTAINER when
  `mos < 0` — it mirrors the rendered ring CW→CCW robustly, with no fragile
  `rotate ∘ scale` composition against the SVG's internal `-rotate-90`; the
  centered number `<span>` carries its OWN `-scale-x-100` so it un-mirrors back
  to readable (scaleX(-1)×scaleX(-1)=identity). 329/502 of the current universe
  is negative MoS, so the CCW path is the COMMON case, not an edge — keep both
  mirrors in lockstep if you touch either (drop the span's mirror and every
  negative-MoS number renders backwards). Accent stays emerald (≥0) / rose (<0).

- **Subagent model aliases float forward to the LATEST — guard the downgrade
  vector, not the agent files** (`.claude/agents/*.md` + `tools/check_model_pin.py`,
  2026-05-31). All 25 agents use bare `model: fable` / `model: sonnet` aliases
  (the 5 judgment-gate agents moved `opus` → `fable` 2026-06-10 when the main
  session moved to Fable 5; `fable` was added to the guard's allowed set).
  Per the Claude Code docs an alias resolves to the newest model in that family
  at runtime and floats forward automatically on a CLI update — so the project is
  "always latest" by design; **never pin a dated/numbered model ID** (e.g.
  `model: claude-opus-4-8`) in an agent, that's a future-dated downgrade the day
  a newer model ships. The real downgrade risk is NOT in the agent files — it's
  an **environment override**: a `CLAUDE_CODE_SUBAGENT_MODEL` or
  `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL` committed into
  `.claude/settings.json` pins every subagent to a specific (possibly older)
  version WITHOUT touching a single agent file — an invisible downgrade. CI
  enforces both halves: `tools/check_model_pin.py` (wired into `ci.yml` as the
  "Subagent model-pin guard" step) fails the build if committed settings carry
  any of those override vars (the one benign value is
  `CLAUDE_CODE_SUBAGENT_MODEL='inherit'`) OR if an agent frontmatter pins a
  non-alias model ID. `effort: max` is orthogonal and unaffected (it tunes
  reasoning depth, not which model). Per-user `.claude/settings.local.json` is
  gitignored so it's out of scope for the committed guard — a local operator
  can still self-downgrade their own machine, but it can't land on `main`.
  **Second out-of-scope vector** (security-reviewer 2026-05-31): the guard
  inspects committed files only, so a `CLAUDE_CODE_SUBAGENT_MODEL` /
  `ANTHROPIC_DEFAULT_*_MODEL` set as a **GitHub Actions repository secret** or
  in a workflow-level `env:` block in another `.github/workflows/` file would
  reach the runner without touching `settings.json` and bypass this check —
  don't add one (there's no legitimate reason to pin the subagent model in CI).

- **Agent teams (experimental) are NOT subagents — and they REUSE the subagent
  defs as teammate roles** (`.claude/agents/TEAMS.md`; flag
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`, 2026-06-08).
  The 22 files in `.claude/agents/` are *subagents*: the main agent spawns them,
  each runs in its own context, they report back to the main agent ONLY, and they
  never talk to each other — this works everywhere incl. Claude Code on the
  web/mobile and drains the paid Sonnet pool. The experimental **agent-teams**
  feature (Claude Code ≥ v2.1.32) is a DIFFERENT mechanism: a *lead* + *teammates*
  that are each a full Claude Code session, share a task list, and **message each
  other directly**; higher token cost; live control is **desktop-terminal only**
  (in-process / tmux / iTerm2 — not drivable interactively from web/mobile). The
  bridge: when you spawn a teammate you reference a subagent type by name and
  Claude honors its `tools` + `model` (the def body is appended to the teammate's
  system prompt), so the same `.md` file is BOTH a subagent and a teammate role —
  **turning a subagent off would also remove it from any team** (so "move work
  from subagents to teams by deleting subagents" is a category error). Caveats:
  teammates do NOT apply a def's `skills` / `mcpServers` frontmatter (they load
  those from project/user settings like a normal session); no nested teams; one
  team per lead; the lead is fixed; `/resume` doesn't restore in-process
  teammates. The 2 write-capable **Tier-5 builders** (`compute-builder` owns
  `compute/**`, `frontend-builder` owns `frontend/**`) exist for the cross-layer
  **Feature Squad** team — they own DISJOINT file sets so teammates never
  overwrite each other; they are NOT on-edit auto-spawns (code review stays with
  the reviewer agents). Every recipe in `TEAMS.md` ships a **subagent fallback** so
  the same flow runs on web/mobile today. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
  is NOT a model-override var, so `tools/check_model_pin.py` ignores it (verified).

- **`RiskSummaryCard` merges rank-gates + manipulation-index into ONE card
  but the two sub-sections are SEMANTICALLY DISTINCT — never flatten them
  into a single list** (`frontend/components/RiskSummaryCard.tsx`, PR #337;
  replaced the former `RiskFlagsCard` + `ManipulationRiskCard`). The card
  renders TWO sub-sections: **RANK GATES** (`risk_flags[]` — Rule-16 Top-5
  disqualifiers; `altman_distress` + `data_quality_input_corruption` also
  force a cautious recommendation) and **MANIPULATION INDEX** (the 0-100
  rollup — INFORMATIONAL soft penalty, rank uses raw composite). They share
  some flag NAMES but the overlap is asymmetric BOTH directions:
  `altman_distress` / `data_quality_input_corruption` /
  `net_issuance_top_decile` / `stale_filing_hard` are rank gates NOT in the
  manipulation index; the annotate-only flags (`accruals_momentum_high`,
  `beneish_high`, `restatement_history`, `rem_suspect`, …) are in the index
  but NEVER in `risk_flags`. A flat merge under one "Manipulation Risk"
  header would mislabel `altman_distress` (financial distress, not earnings
  manipulation) — that is the footgun. **De-dup contract** (load-bearing):
  a flag that is BOTH a rank gate AND a fired manipulation component shows
  ONLY in RANK GATES; the manipulation sub-section lists only the
  annotate-only SURPLUS via `alsoFired = firedComponents − gateSet` under
  the "Also fired — not rank-gating" label. Drop the set-difference and the
  shared flags (sloan / beneish_veto / …) render TWICE again — the exact
  on-screen duplication this card was built to fix (82/502 of the current
  universe carry both a gate and a manipulation component). Outer ring =
  worst-case (rose if any rank gate, else the manipulation band tone); the
  band chip (Low/Moderate/High) moves into the manipulation sub-header when
  gates own the outer-header count chip so it's never lost. Returns `null`
  only when BOTH halves are empty (no rank gates AND `manipulation_index`
  is `null` / `undefined` / `0` — `hasIndex` suppresses on a zero index,
  not just null). The two flag-label maps stay separate on
  purpose: `RANK_GATE_META` carries the academic-anchor detail line,
  `MANIPULATION_FLAG_LABELS` is label-only.

- **Background runs (`Agent run_in_background:true` / `Bash run_in_background:true`)
  default to SYNC — and if you go background, you OWN the teardown in the
  SAME session** (process hygiene, 2026-05-31, after a "chevron review"
  agent + an `npm install` bash showed as perpetually-"Running" in the
  Background-tasks panel across a `/compact`). Two distinct zombie classes,
  two distinct fixes:
  - **Background AGENT orphaned by `/compact`** — an async sub-agent spawned
    with `run_in_background:true` is tracked by an `agentId` the harness
    returns at spawn time. A `/compact` (or a context-window roll) drops that
    `agentId` from the live transcript, so the post-compact main agent has NO
    handle to `SendMessage`/stop it — it runs (or sits "Running") forever,
    still billing tokens, and `ps aux` CANNOT see it (it lives in the harness,
    not as an OS process in the container — do NOT "confirm it's dead" with
    `ps`/`pgrep`, that only sees Bash). **Prevention**: default to SYNCHRONOUS
    `Agent` calls (await the result in the one tool block) — that is the
    normal mode and it self-cleans. Reserve `run_in_background:true` for a
    genuinely long job whose completion you will collect in the SAME session,
    BEFORE any compact. If a long run must straddle a compact, tell the user
    so they can Stop it from the panel — the orphaned `agentId` is
    unrecoverable from the agent side.
  - **Background BASH left "Running"** — a `run_in_background:true` Bash with
    no natural exit (`next dev`, `tail -f`, `while true`, an `npm install`
    whose panel entry lingers) shows "Running" until killed. **Prevention**:
    background Bash must have a DETERMINISTIC exit (an `until grep -q …; do
    sleep 0.5; done` that ends in seconds, per the Monitor/Bash guidance) —
    never a server/`-f`/`while true` parked in the background. If you must
    serve (e.g. `next dev` for a Playwright pass), KILL it in the same turn
    you finish with it (`ps … | grep next | awk '{print $2}' | xargs kill`,
    NOT a broad `pkill` — a `pkill` that catches the harness's own shell
    returns a non-zero/144 and CANCELS the rest of your tool batch, which is
    how the parallel-batch nuke on 2026-05-31 happened). A finished
    background Bash that still shows in the panel is harmless (no tokens) —
    the user can Stop it; only flag it if `ps` shows a real live PID.

- **The fair-price detail pair is split INTERPRETATION vs REFERENCE on
  purpose — `FairPriceCard` does NOT repeat the per-method dollar values**
  (`frontend/components/FairPriceBarChart.tsx` + `FairPriceCard.tsx`, PR #339).
  Two adjacent cards both read the SAME `detail.fair_price` object but answer
  DIFFERENT questions, so they were de-duplicated rather than merged (unlike
  the RiskFlags+Manipulation merge — those asked the SAME question). **Card A
  `FairPriceBarChart` ("Fair price check", renders first)** owns the
  INTERPRETATION layer: every applicable method's dollar estimate + a
  cheap/fair/pricey/outlier verdict badge + plain-English narrative + the
  tally ("Of N methods: X cheap …"). **Card B `FairPriceCard` ("Fair price
  ensemble", renders second)** owns the REFERENCE/metadata layer: Median /
  MoS / Max-ex-outliers / Tangible-BVPS stat grid + the defense-flag warning
  chips + the methodology footnote. The former METHOD→VALUE table in Card B
  was REMOVED (PR #339) — it restated the exact dollar values Card A already
  shows per method, so it was pure on-screen duplication. **Do NOT re-add a
  per-method value table to Card B** — per-method dollars live in Card A only;
  Card B's footnote cross-references "the Fair price check above". **The two
  cards also carry DIFFERENT MoS formulas by design and the card boundary is
  what keeps them from looking contradictory**: Card B "Margin of safety" =
  schema `mos_pct = (median − price) / median` (vs FAIR VALUE — the
  Damodaran/Graham definition, the official scoring field, `ensemble.py`);
  Card A "−X% vs today" = `(median − price) / price` (vs MARKET PRICE,
  recomputed inline in `FairPriceBarChart.tsx`). For NVDA that's −175% (Card B,
  clamped "< −99%") vs −64% (Card A) — both correct for their own anchor. A
  future "merge these two cards" idea must FIRST resolve that two-formula
  clash (the reason they stay separate cards, not one).

- **Stock-detail section order is deliberate — score-explanation rides high,
  the warning group frames valuation, raw data sinks** (`frontend/app/stock/[ticker]/page.tsx`,
  PR #340; two-agent reading-order audit `frontend-design-reviewer` +
  `expert-user-explorer`). Top-to-bottom: back-link → hero (identity + Score
  donut + MoS donut + Fair-value/Target/Loss-chance) → Price chart →
  **`PillarRadarChart`** → `Tier2EventCard` → `RiskSummaryCard` →
  `FairPriceBarChart` ("Fair price check") → `FairPriceCard` ("Fair price
  ensemble") → `RawMetricsTable` → Data quality → methodology footnote.
  Load-bearing ordering rules: (1) **`PillarRadarChart` sits right after the
  price chart, NOT below the fair-price pair** — it answers "why is the
  composite score what it is?" (NVDA value-pillar 35 vs quality 91) while the
  hero's score donut is still fresh; moving it back down re-strands the score
  explanation ~1000px from the score. (2) **The warning group
  (`Tier2EventCard` + `RiskSummaryCard`) stays ABOVE the fair-price pair** so
  red flags frame the valuation read (a Beneish veto makes a $36 fair-value
  estimate suspect); both `null`-collapse on clean stocks so the clean-stock
  order is hero → price → pillars → fair-price → raw. The two-agent audit
  deliberately did NOT move the warning group above the price chart (the
  `frontend-design-reviewer` IA suggestion) — `expert-user-explorer` showed
  the current spot optimizes the risk-checker persona correctly. **A hero
  "N risk vetoes" chip was tried and REVERTED in the same PR** (user call,
  2026-05-31 — "ไม่เอา"): keep the hero visually quiet; the rank-gate detail
  lives in `RiskSummaryCard` below, the recommendation badge ("Hold" etc.)
  already carries the cautious signal, and the MoS donut conveys overvaluation.
  Do NOT re-add a hero flag chip without a fresh user request.

- **Price-chart resolution is PER-PERIOD — 5Y aggregates to monthly, the
  shorter windows stay daily** (`frontend/components/PriceHistoryChart.tsx`,
  PR #341). The on-disk history (`/data/stocks/history/<T>.json`) is and stays
  **daily OHLCV, ~1254 points over 5y** (`PRICES_PERIOD` is now `"10y"` for the
  decade-long AI-pick backtest, but `write_stock_history` tail-caps to
  `HISTORY_TAIL_DAYS`=1260 ≈ 5y, so the per-stock chart's payload is UNCHANGED;
  yfinance `1d`) — the per-period resolution is a pure FRONTEND render
  decision in the `chartData` memo: **5Y → `aggregateMonthly()`** (one point
  per calendar month = the close of that month's FIRST trading day, ~60 points
  over 5y); **1M / 6M / YTD / 1Y → daily**,
  then `downsample(…, 260)` as a render-cost cap (even-stride, keeps the exact
  last point so the latest price + flush-right crosshair stay correct). So 5Y
  no longer even-stride-downsamples daily points — it month-start-aggregates.
  `aggregateMonthly` assumes the series is ascending by `date` (it is, per
  `write_stock_history`), takes the FIRST trading day of each month, and ALWAYS
  appends the real latest daily point last (de-duped) so the chart's right edge
  + park-at-latest crosshair show the current price, not the weeks-stale
  1st-of-this-month close. **1D (1-min) / 5D (15-min) are
  still DISABLED** (`PriceTimePeriodSelector` `ENABLED_PERIODS`) — true intraday
  is a separate v1.3 feature requiring a NEW compute/ingest path (yfinance
  `1m`=7-day / `15m`=60-day caps) + a `StockHistory` schema-triple bump + cron
  volume + the static-site freshness caveat (cron is daily post-close, so 1D
  would be the last cron's session, not real-time). Do NOT wire 1D/5D from the
  existing daily file — there is no intraday data in it.

- **Hero metric values count-up; the recommendation badge is STATIC**
  (`frontend/components/HeroMetric.tsx` + `RecommendationBadge.tsx`, PR #342).
  Two coupled changes per user request 2026-05-31: (1) the `RecommendationBadge`
  chip-pop entrance was REMOVED — the badge no longer takes `animateOnce`, no
  longer imports `usePlayOnMount`, and dropped its `'use client'` (it's a pure
  server component again; the 502 ranking-table cells + the hero badge all
  static-render with no motion gate). The `chip-pop` keyframe stays defined in
  `tailwind.config.ts` + `globals.css` as a reusable utility but has ZERO
  consumers now (Tailwind purges it from the bundle) — don't "clean it up" by
  deleting the keyframe unless you also confirm no future surface wants it. (2)
  Fair value / Target / Loss chance in the hero now COUNT-UP on each visit via
  the new `HeroMetric` client leaf, which wraps
  `useCountUp(value, play, 300)` (easeInOutCubic — the SAME app-wide ease-in-out
  curve as the Score / MoS gauge sweep, but a SHORTER beat: `$impeccable quieter`
  2026-06-02 dropped it 800 → 300ms so it lands inside the design.md ≤320ms micro
  budget and the 800ms Score-gauge sweep stays the page's LONE >320ms signature —
  the prior 800ms made the score gauge + MoS gauge + all three of these count-ups
  race at 800ms on every detail load; do NOT bump back to 800). `page.tsx` stays a Server Component;
  `HeroMetric` is the small `'use client'` leaf that holds the hook (don't lift
  the hook into the page — that would force the whole detail page client-side).
  The loss-chance band (`{ tone, dot, label }`) is computed server-side in
  `page.tsx` (`lossBand`) and passed to `HeroMetric` as the value `tone` PLUS a
  `caption` (the band WORD — "Neutral" / "Moderate-high" — surfaced under the
  number so a bare "55%" isn't ambiguous; `$impeccable clarify` P2 2026-06-02,
  matching the mobile ranking card's dot+word treatment) so the band rubric
  stays in one place and matches `RankingTable` (NVDA 56% → Neutral slate, not
  red — the band is `<60`). The `caption` is static (it never animates with the
  count-up); price metrics (Fair value / Target) pass no caption.
  `useCountUp` inits at the target so SSR / no-JS / reduced-motion render the
  exact value (the count-up is progressive enhancement, never a visibility gate).
  `HeroMetric` also ADDS `dark:` variants the old inline hero metrics lacked
  (`dark:text-slate-100` value / `dark:text-slate-400` label / `dark:text-slate-600`
  em-dash + the dark band tones) — a dark-mode correctness fix (the old
  `text-slate-900` value was near-invisible on the `dark:bg-slate-900` hero
  card), WCAG-AA on the dark surface, not a regression.

- **`lucide-react` is the project's FIRST icon library — named imports ONLY**
  (`frontend/package.json` + `frontend/components/HeroAttributeTiles.tsx`,
  PR #344). Added for the hero attribute-tile grid. The whole library is
  ~28 MB on disk (1,962 icons as individual `.mjs`) but tree-shakes to
  ~1.5-2 KB gzipped IF you import by NAME — `import { Building2, Coins } from
  'lucide-react'`. **NEVER** `import * as Icons from 'lucide-react'` or
  `import Lucide from 'lucide-react'` — either pulls the full 224 KB barrel
  (dependency-auditor 2026-05-31). `sideEffects: false` + the ESM `module`
  field make webpack-5/Next-14 drop the unused icons; a dynamic
  `Icons[name]` access defeats it (forces the barrel) — so the icon set is
  STATIC per call site, not data-driven. Pinned `^1.17.0` (ISC license,
  React-18.3 peer, 0 transitive, 0 install-script, SLSA-attested — both
  dependency-auditor + security-reviewer SAFE). NOT in the dependabot
  ignore-list (normal minor/patch flow; a `2.0.0` major would get the usual
  migration-PR handling). Runtime npm deps aren't tracked in
  `THIRD_PARTY_NOTICES.md` (that file is vendored-source / skills only —
  next/react/recharts aren't listed either), so lucide isn't added there.

- **`country-flag-icons` flag SVGs — per-country STATIC imports ONLY**
  (`frontend/package.json` + `frontend/components/ListingChips.tsx`, PR-B).
  Added for the stock-detail hero country chip. Import per-country via the
  subpath — `import US from 'country-flag-icons/react/3x2/US'` (tree-shakes to
  ~2 KB gzipped). **NEVER** the barrel `import { US } from
  'country-flag-icons/react/3x2'` / `import * as Flags` / a dynamic
  `Flags[code]` — each pulls the full ~330 KB / 267-country monolith and
  defeats tree-shaking (same discipline as `lucide-react` above). The flag set
  is STATIC per call site via the `FLAG_BY_COUNTRY` lookup table; add a non-US
  country by importing its component + adding one row, never a dynamic import.
  Pinned `^1.6.17` (MIT, 0 transitive, 0 install-script, registry-signed; NO
  SLSA attestation — acceptable for a pure-SVG static lib; both
  dependency-auditor + security-reviewer SAFE 2026-06-01). NOT in the dependabot
  ignore-list (normal minor/patch flow). Runtime npm dep → NOT in
  `THIRD_PARTY_NOTICES.md` (like lucide / next / recharts).

- **Hero attribute tiles = the 4-box category grid, theme-reskinned, 2 data +
  2 reserved** (`frontend/components/HeroAttributeTiles.tsx`, PR #344). The
  QuantRank answer to "กรอบสี่เหลี่ยมสี่อันในภาพ" (a reference stock app's
  icon-over-label category tiles). Modeled on that STRUCTURE (lucide icon top,
  caption + value below, `grid grid-cols-2 sm:grid-cols-4`) but RESKINNED to
  the LedgerCraft theme — light = soft slate surface, dark = deep slate, NOT
  the reference app's black boxes (which break in light mode); `rounded` ≤4px,
  border-as-depth, paired `dark:`. Four FIXED tiles: (1) **Size** =
  market-cap tier (Mega ≥$200B / Large ≥$10B / Mid ≥$2B / Small) — DATA;
  (2) **Sector** = `detail.sector` — DATA; (3) **Dividend** + (4) **Type** =
  intentional PLACEHOLDERS rendered in a dashed-border "reserved" state with a
  "Coming soon" sub-line (per the user's "ช่องเปล่า + label บอกว่าจะมีอะไร" —
  the empty tile reads as reserved, not broken). The **Type** tile is reserved
  for a future security-type signal (Common stock / ADR / etc. — the analog of
  the reference app's "Common · หุ้นสามัญ" tile, user direction 2026-05-31);
  the **Dividend** tile mirrors the reference app's "จ่ายปันผล" tile. NEITHER
  field exists in the schema yet — when one lands, swap the tile's `value`
  from `null` to the real field and it auto-promotes out of the reserved state. A `null` value flips a tile to the reserved treatment via the
  `filled` flag. INFO tiles, NOT filters (single-stock detail page — nothing
  to filter). Pure server component. Lives in its own section directly under
  the hero `</header>`, above the Price chart. Distinct from the earlier
  inline-chip attempt (closed PR #343 — the user wanted the BOX grid, not a
  compact chip row).

- **`PillarRadarChart` row REFLOWS on mobile — bar drops to its own full-width
  line; the axis-tick row MUST mirror the same breakpoint** (`frontend/components/PillarRadarChart.tsx`,
  PR #345). The 8-pillar bar list was a fixed 3-column grid
  `grid-cols-[8rem_1fr_4.5rem]` (label · bar · value) at EVERY width — on
  mobile portrait the bar `1fr` got squeezed to ~56px (label 8rem + value
  4.5rem ate a 280px card). Fix: each `<li>` is now mobile
  `grid-cols-[1fr_auto] grid-rows-[auto_auto]` (row 1 = label-left + value-
  right; row 2 = the bar `col-span-2 order-last` full-width) → `sm:` collapses
  back to the single-row `grid-cols-[8rem_1fr_4.5rem]` (`sm:order-none
  sm:col-span-1 sm:grid-rows-1 sm:items-center`). The **`order-last` is
  load-bearing**: the bar is the 2nd DOM child (before the value), so without
  `order-last` the mobile auto-flow would place it at row1-col2 ON TOP of the
  value — `order-last` forces it to row 2; `sm:order-none` restores DOM order
  for the desktop single-row. **The axis-ticks row (0/30/50/70/100) reuses the
  IDENTICAL responsive grid** (`grid-cols-[1fr_auto] sm:grid-cols-[8rem_1fr_4.5rem]`
  + `col-span-2 sm:col-span-1` on the tick container + `hidden sm:block`
  spacers) so the ticks stay aligned under the bar in BOTH layouts — if you
  touch the row grid, touch the axis grid in lockstep or the ticks drift off
  the bar. Bar internals (30/50/70 lines, fill `calc(% - 8px)`, baseline
  notch) are all %-relative to the bar's own box, so they scale at any
  width untouched. Description is `line-clamp-1 sm:truncate` (it has room to
  breathe on the wider mobile line). `space-y-3 sm:space-y-2` on the `<ul>`
  (the 2-line mobile rows need a touch more separation).

- **`globals.css` soft-color overrides are an ALLOWLIST — `bg-rose-600` /
  `bg-emerald-700` are NOT remapped** (`frontend/app/globals.css`, 2026-06-01).
  The soft-OKLCH cascade (`--c-pos-*` / `--c-neg-*`) remaps only the SPECIFIC
  Tailwind utility classes enumerated in the `!important` override block (e.g.
  `.text-emerald-700`, `.bg-emerald-50`, `.bg-emerald-600`, `.bg-rose-50`,
  `.bg-rose-500`, `.ring-rose-200`, `.text-red-700`, `.bg-red-50`). A class
  OUTSIDE that list renders its RAW Tailwind value — notably `.bg-rose-600` is
  absent, so a `bg-rose-600` surface shows raw alarm-red, not the muted
  terracotta. That exact gap made the rankings mobile daily-change DOWN pill
  render alarm-red while the `bg-emerald-600` UP pill softened (fixed in the
  `$impeccable polish` PR by moving the pill to the chip family). Rule of the
  road: for any new positive/negative surface, use a class ALREADY in the
  override list OR (better) the shared outlined-light chip family
  (`bg-{tone}-50 text-{tone}-700 ring-{tone}-200`, fully covered in light + dark)
  — never reach for an un-listed shade expecting it to soften. Note the override
  remaps utility CLASSES only: inline `style` / svg `stroke` values (the score
  + MoS gauge accents via `scoreAccentColor` / `MoSBadge`) are never reached and
  stay raw mid-saturation rgb BY DESIGN (thin ring needs the saturation; the
  amber mid-band has no soft token anyway). **The one soft NEGATIVE dot token is
  `bg-rose-500`** (→ `--c-neg-dot`); the recommendation "Sell" + loss-chance
  Moderate-high/High dots (raw `bg-red-500/600`) + the `RiskSummaryCard` severity
  dots (raw `bg-rose-600`) were the last alarm-dots, all now `bg-rose-500`
  (a severity ramp can't carry two distinct SOFT red dots —
  only `--c-neg-dot` exists — so both high bands share it + distinguish via label
  + `text-red-700/900`). The `PillarRadarChart` bar fills + legend use raw
  inline rgb (a 5-step ramp echoing the score-gauge accent palette) BY DESIGN —
  do NOT re-flag them as a soft-color miss (a stale code comment wrongly claimed
  they were remapped by the override; corrected 2026-06-01). Post-P3 (2026-06-02)
  the ramp is keyed to the composite `TIERS` boundaries (25/40/55/70), not the
  old 30/50/70 — see the §Gotchas "PillarRadarChart shares the composite TIERS
  vocabulary" entry below.

- **Interactive controls carry a `min-h-[44px]` touch target; modals trap +
  restore focus; warning-card headings are severity-toned** (`frontend/components/*`,
  `$impeccable audit`+`critique` punch-down 2026-06-01). Three a11y standards
  landed across the UI: (1) every primary interactive control (TopNav links + brand link, RankingTable search / pagination, `PriceTimePeriodSelector`, the detail back-link, ThemeToggle) carries
  `min-h-[44px]` (often `min-w-[44px]` / `h-11 w-11`) so the tap target clears
  the mobile-first floor PRODUCT.md mandates — a NEW button/input/link MUST
  follow suit (never ship a `py-1`/`h-8` control as a touch target). (2)
  Any future slide-over/dialog must trap Tab/Shift+Tab within its root, move focus IN on open, and restore it to the trigger on close (WCAG 2.4.3) — not just body-scroll-lock + Esc. (3) Warning cards (`Tier2EventCard`
  / `RiskSummaryCard`) tone their `<h2>` by severity (rose veto / amber annotate,
  else neutral slate) so they outweigh the neutral data-section eyebrows — a
  deliberate break from the uniform `text-slate-600` header treatment, gated on
  the card actually carrying a warning. (Verified-false-positive, do NOT
  "re-fix": the dark loss-chance band is already soft — the `!important`
  `text-red-700` remap wins over `dark:text-red-300`; the period selector already
  uses the correct `role="radio"`+`aria-checked`, not `aria-pressed`.)

- **Secondary / muted text uses `text-slate-500 dark:text-slate-400` — NOT the
  inverted `text-slate-400 dark:text-slate-500`** (`$impeccable critique`
  follow-up 2026-06-01). The inverted token fails WCAG AA in BOTH modes
  (slate-400 `#94a3b8` on white ≈ 2.6:1 · slate-500 `#64748b` on slate-900
  `#0f172a` ≈ 3.75:1); the standard token clears both (≈ 4.8:1 light / ≈ 7:1
  dark). slate-* classes are NOT in the `globals.css` soft-override allowlist
  (entry above), so they render RAW Tailwind hex — check contrast against the
  raw value, not an OKLCH token. The inverted token was normalized app-wide
  across 16 components (pillar descriptions / footnotes / secondary counts /
  placeholders / "Coming soon" reserved tiles / chart-empty states).
  **Striped-table exception**: secondary text on `even:bg-slate-100` rows
  (`RawMetricsTable`) uses `text-slate-600` — `slate-500` is only 4.34:1 on the
  slate-100 stripe (vs 4.76:1 on white), so striped tables need one shade
  darker. Correctly LEFT faint (do NOT "re-fix"): DISABLED controls
  (`PriceTimePeriodSelector`
  disabled period buttons — WCAG 1.4.3 inactive exemption) and decorative
  `aria-hidden` icons. **Audit caveat**: a browser-tool "dark
  contrast" finding can mis-name the token (an agent reported `slate-400` @
  4.2:1; the real failing token was `slate-500` and the fail spanned BOTH
  modes) — verify the actual class + surface before fixing.

- **The stock-detail page splits into a DECISION zone and a collapsed
  "Supporting data" reference zone — don't re-flatten it** (`frontend/app/stock/[ticker]/page.tsx`,
  `$impeccable distill` P1, 2026-06-01). The page had 11 same-weight sections so
  the 14-row raw-fundamentals table + data-quality block read as loud as the
  decision signals (cognitive-load FAIL 5/8). Now everything through the
  fair-price pair is the DECISION zone (hero → attribute tiles → price →
  pillars → Tier-2 → Risk → Fair-price check → Fair-price ensemble); Raw
  fundamentals + Data quality are grouped into ONE collapsible **`<details>`
  "Supporting data"** card (recessed `bg-slate-50/60 dark:bg-slate-900/40`
  surface + a `font-slab` summary label that is deliberately a DIFFERENT
  register from the `uppercase tracking-[0.14em]` decision-section eyebrows),
  **collapsed by default** (progressive disclosure — the dense balance sheet is
  verification, one click away; cuts ~600px of mobile scroll before the
  methodology note). Native `<details>`/`<summary>` keeps the page a **Server
  Component** (no JS / no client leaf) and is keyboard + SR accessible; the
  chevron rotates via `group-open:rotate-180` (Tailwind 3.4 supports the
  `group-open` variant — confirmed in the compiled CSS). **A NEW
  reference/provenance section goes INSIDE this `<details>`, not as a 12th
  top-level section; a new DECISION signal goes above, before the fair-price
  pair.** The methodology footnote stays visible AFTER the details (short,
  frames the composite). Inner section `<h2>`s are kept (the summary is a styled
  span, not a heading) so the document outline stays intact.


- **Loss-chance (and any rounded-display band/tone) must derive from the
  ROUNDED integer, NOT the raw float** (`LossChanceBadge.tsx` +
  `RankingTable.tsx` mobile card + `app/stock/[ticker]/page.tsx` hero
  `lossBand`, `$impeccable clarify` P3 2026-06-01 + P2 2026-06-02). All three
  display `Math.round(pct)` (`HeroMetric` prints `${Math.round(v)}%`) but
  previously banded off the raw `pct` — so a 59.7 rendered "**60% · Neutral**"
  (the number reads as the start of the 60-79 Moderate-high band while the tone
  said <60 Neutral). Now all three band off `Math.round(pct)`. The 5-band rubric
  (`<25` Low / `<40` Moderate-low / `<60` Neutral / `<80` Moderate-high / else
  High) is DUPLICATED across those three sites (LossChanceBadge `BANDS` array ·
  the inline ternary in the mobile card · the `lossBand` object in the hero) —
  they move in lockstep, so a threshold change touches all three. The hero site
  was a 3-tone-only collapse until P2 (2026-06-02) promoted it to the full
  5-band `{ tone, dot, label }` object so the hero surfaces the band WORD as a
  caption (not just the number tone) — its five rows are now a verbatim copy of
  the mobile-card ternary, which is the lockstep contract. General rule for any
  new threshold chip whose value is shown rounded: band off the same rounded
  value you render.

- **`PillarRadarChart` shares the composite `TIERS` vocabulary + boundaries —
  do NOT reintroduce a separate pillar band rubric** (`frontend/components/PillarRadarChart.tsx`,
  `$impeccable clarify` P3 2026-06-02). The 8-pillar bar list previously banded
  with its OWN 4-word scheme (Strong / Decent / Weak / Poor) at 30/50/70 — which
  COLLIDED with the composite score's 5-tier `TIERS` words (Exceptional / Strong
  / Average / Weak / Poor at 25/40/55/70 in `lib/visual.ts`): "Strong" meant
  55-70 on the score gauge but ≥70 on a pillar (same word, two ranges;
  "Weak"/"Poor" also diverged). A 4-band scheme can NEVER be consistent with the
  5-tier scale (different boundary counts), so the pillar now derives its tier
  WORD from `TIERS.find(...)` (single source of truth) and its 5-step color ramp
  + gridline ticks + axis number ticks + legend are ALL keyed to the SAME
  25/40/55/70 boundaries — a pillar at 60 now reads identically to a composite
  score of 60. **Touch the rubric in `lib/visual.ts` and it flows to both
  surfaces; do NOT hardcode a second band table in the pillar.** Bar
  tier/number/color band off `Math.round(value)` (band-from-rounded, entry
  above) so a 54.6 doesn't render "55 Average" against the "Strong (55–70)"
  legend; only the continuous bar FILL width stays on the raw float.
  `scoreAccentColor` (the score-gauge ACCENT ring, 20/40/60/80) is intentionally
  left on its own heat-signal boundaries — it is NOT the tier-label rubric and
  was not touched.

- **MoS donut + pillar rows expose their data to SR (not just a mouse `title`);
  the hero MoS is anchored "vs fair value"; the hero shows "Data as of {date}"**
  (`MoSBadge.tsx` + `PillarRadarChart.tsx` + `app/stock/[ticker]/page.tsx`,
  `$impeccable` a11y/clarify minors 2026-06-02). (1) `MoSBadge` is now a single
  `role="img"` with a comprehensive `aria-label` ("Margin of safety versus fair
  value: −12%, Overvalued") built from the FINAL `mos` (never the count-up
  `shown`), with the donut `<svg>` `aria-hidden` — SR announces ONE clean string
  instead of the donut digit + the text column separately, and the basis reaches
  SR/keyboard (the old mouse-only `title` on the non-interactive `<div>` did
  not). (2) `MoSBadge` also shows a VISIBLE `(vs fair value)` anchor (mirrors
  `FairPriceCard`'s label) so the hero MoS is disambiguated in-page from
  `FairPriceBarChart`'s "vs today's price" (vs MARKET price) — each MoS formula
  now names its anchor on screen (the §Gotchas "fair-price detail pair" two-
  formula split). (3) Each `PillarRadarChart` row adds an `sr-only` span with the
  sector-median (`baseline.label` + rounded value), gated on the SAME
  `baselineValue !== null` as the visual notch — so the median that lived only in
  the mouse `title` + the bar notch now reaches SR/keyboard. (4) The detail hero
  shows a compact "Data as of {YYYY-MM-DD}" line from
  `getMetadata().last_update_utc` (the cron date the home page already shows) —
  freshness was previously only inside the collapsed Supporting-data drawer.
  NOTE: `MoSCell.tsx` is ORPHANED dead code (no importer — only stale comment
  refs in `page.tsx` / `LossChanceBadge.tsx` / `visual.ts`); not a live surface,
  so its `title` was out of scope.


- **The outlined-light chip is a PRIMITIVE now — `frontend/components/Chip.tsx`,
  not a copy-pasted className string** (`$impeccable extract` 2026-06-02). The
  design system's "one outlined-light chip pattern" (frontend-design-system
  SKILL.md Rule 2) was, until this PR, a COPY-PASTE convention: the shell
  (`inline-flex items-center rounded-sm font-medium ring-1 ring-inset` + the
  `h-1.5 w-1.5 rounded-full` dot + the `px-/text-` size scale) was re-typed
  inline in 7+ components, and the `SIZE_CLASSES` map was duplicated VERBATIM in
  `RecommendationBadge` + `LossChanceBadge`. Now: `<Chip tone={…} size="sm"
  dot={…} leading={…}>label</Chip>` owns the shell + conditional `gap-1.5` + dot,
  and the `CHIP_BASE` / `CHIP_DOT` / `CHIP_SIZES` exports cover bespoke surfaces
  that can't route through the canonical props because they'd emit a CONFLICTING
  Tailwind utility — `ScoreBadge`'s `font-semibold tabular-nums` numeric pill
  (the chip family is `font-medium`) and `SectorChip`'s inline-rgb sector dot +
  1px-larger `xs` text (`text-[0.6875rem]` vs the canonical `CHIP_SIZES.xs`
  `text-[0.625rem]`, a deliberate mobile-row deviation). **Rules of the road:**
  (a) a NEW metadata chip uses `<Chip>`, never a hand-typed shell; (b) a bespoke
  numeric/icon surface composes `CHIP_BASE` + `CHIP_DOT` (+ `CHIP_SIZES`) so the
  shell stays single-sourced; (c) tone classes pass through `Chip` VERBATIM (it
  is tone-agnostic) so the `globals.css` soft-OKLCH `!important` allowlist still
  remaps them — never pre-resolve a tone to hex inside the chip; (d) `Chip` is a
  pure presentational (no-`'use client'`) component so it renders in BOTH server
  callers (`SectorChip` / `RecommendationBadge` / `ListingChips`) and client
  callers (`LossChanceBadge` / `Tier2EventCard`). The follow-up `$impeccable
  polish` (PR after #388) extended the shell to `FairPriceCard`'s `<li>` warning
  chips (which also gained the chip-family `font-medium` — the documented
  holdout) + `FairPriceBarChart`'s tally pills (DRY'd 3 copies → one map) +
  verdict badges — all compose `CHIP_BASE` / `CHIP_DOT` BY HAND because they have
  non-standard padding (`px-2.5 py-1` / `px-1.5 py-0.5`) / uppercase / mono
  content that the canonical `size` prop can't emit without a conflicting
  utility. STILL bespoke by design: the `RankingTable` selection-state chips (the remaining interactive toggle surfaces that layer `press hover:opacity-75`) — interactive controls, not metadata chips. **Neutral chip ring is canonically `ring-slate-200`** (matches the
  sector / listing / MoS-fair neutral) — the `RecommendationBadge` "Hold" + `LossChanceBadge` "Neutral" (#389) AND the `RankingTable` active-filter chips (follow-up) were all normalized `ring-slate-300 → 200`, so EVERY neutral chip — static metadata AND interactive toggle — shares one ring shade. No `ring-slate-300` neutral outlier remains; the lone surviving
  `ring-slate-300` is `FairPriceBarChart`'s deliberately-muted `outlier` verdict
  tone (NOT a neutral chip — leave it).
- **Chip family carries `font-medium`; every large numeric display carries
  `font-mono`; annotate-amber bodies use `bg-amber-50`; negative-strong rings
  use the soft `-200` shade, never raw `-300`** (`$impeccable polish` pass
  2026-06-02 — corrected residual drift, codified here so it doesn't re-drift).
  Concretely: (1) ALL chips render `font-medium` (the `SectorChip` was the holdout at `font-normal`; `RecommendationBadge` was already correct). (2) ALL large
  numeric values use `font-mono tabular-nums` (the `RiskSummaryCard` manipulation
  index `text-3xl` + its `/100` denominator were rendering in the body font —
  every other big number, `ScoreGauge` / `MoSBadge` / `HeroMetric`, is mono). (3)
  `Tier2EventCard`'s annotate severity badge uses `bg-amber-50` (not `bg-amber-100`)
  to match the app's other amber-warning bodies (`FairPriceCard` chips, `TIERS`
  Average/Weak chip bodies) — amber has NO globals.css soft-remap, so the lighter
  shade is what keeps it visually beside the softened rose veto. (4) negative-
  strong ring shades are `ring-red-200` / `ring-rose-200` (in the globals.css
  soft-allowlist), never `ring-red-300` (raw, more saturated) — fixed on
  `RecommendationBadge` `cautious` (Sell) + `LossChanceBadge` High band; the
  positive-strong ring stays `ring-emerald-300` BY DESIGN (emerald isn't alarm,
  so the pos/neg-strong asymmetry is intentional per "no dopamine red"). (5)
  small-caps value sub-labels use `tracking-wider` (not `tracking-wide`) — the
  `FairPriceCard` stat-grid `dt`s were the holdout. Detail-page section spacing
  is owned by the `<article>` `space-y-4` DEFAULT (16px) plus two deliberate
  `!mt-8` zone-seams (§Gotchas "detail-page two-level spacing") — a section MUST
  NOT add its OWN ad-hoc `mb-*`/`mt-*` (the `PillarRadarChart` `mb-4` was
  creating a 32px double-gap; a plain `mt-*` is silently overridden by `space-y`
  anyway). And no
  "coming in v1.3" style stale version copy — use "coming soon" (the
  `PriceTimePeriodSelector` 1D/5D tooltips).

- **The price chart is lazy-loaded via `PriceHistoryChartLazy` so Recharts
  code-splits OUT of the stock-detail First Load JS — the Server Component page
  imports the LAZY wrapper, NEVER `PriceHistoryChart` directly** (`frontend/components/PriceHistoryChartLazy.tsx`
  + `app/stock/[ticker]/page.tsx`, `$impeccable optimize` 2026-06-02). Recharts
  is the ONLY Recharts consumer in the app (`PillarRadarChart` is a div-bar list,
  not Recharts) and was the dominant chunk: lazy-loading it via
  `dynamic(() => import('./PriceHistoryChart'), { ssr: false })` dropped the
  `/stock/[ticker]` First Load JS from **214 kB → 110 kB (−49%)** (page-specific
  code 115 kB → 11 kB), matching the home page. **Importing `PriceHistoryChart`
  directly into the server page would pull Recharts back into First Load** —
  always go through the lazy wrapper. Safe + zero-CLS because the chart was
  ALREADY a `'use client'` leaf that fetches its history JSON on mount and shows
  a shimmer skeleton until then (its header comment: "keeps these out of the SSR
  bundle"), so the static HTML already showed a skeleton, not the chart. The
  wrapper's `loading` skeleton is an EXACT copy of the chart's internal one (the
  `space-y-3` shimmer stack ending in `h-64 w-full animate-shimmer`), so the
  reserved height is identical → no layout shift, and the user sees one
  continuous skeleton (chunk-load → data-fetch → render). `next/dynamic` with
  `ssr: false` MUST live in a Client Component, which is why the wrapper exists
  (the page is a Server Component). If a SECOND Recharts surface is ever added,
  give it the same lazy-wrapper treatment.

- **The composite-score gauge + mobile caption tier WORD comes from the canonical
  `scoreTierLabel` (lib/visual.ts TIERS) — NOT a local rubric, and NOT the
  `scoreAccentColor` boundaries** (`ScoreGauge.tsx` + `ScoreBadge.tsx` +
  `lib/visual.ts`, `$impeccable` 2026-06-02; finishes the `clarify P3` TIERS
  consolidation that the pillar bars got in #363 but these two surfaces missed).
  Both components previously carried their OWN local `tierLabel()` on the wrong
  `80/60/40/20` accent boundaries (Exceptional ≥80 / Strong ≥60 / …), so the
  gauge labeled the tier by the COLOR boundaries instead of the TIERS
  (25/40/55/70) boundaries — **81 tickers showed the wrong word**, incl. the
  top-3 (NVDA/CF/HST at 71-73 said "Strong" not "Exceptional") and the 78-ticker
  55-60 band ("Average" not "Strong"), contradicting the pillar bars on the SAME
  page (`expert-user-explorer` catch). Now both call
  `scoreTierLabel(<displayed value>)` — `Math.round(score)` for the integer gauge
  (`ScoreGauge`), `Number(score.toFixed(1))` for the 1-decimal mobile caption
  (`ScoreBadge` md) — so the word bands off the SHOWN number (§Gotchas
  band-from-rounded). The `sm` table pill shows no tier word (just the number +
  dot). **`scoreAccentColor` (the gauge arc + dot COLOR) intentionally stays on
  its own 20/40/60/80 heat-signal boundaries** — it is NOT the tier-label rubric;
  the word↔color boundary split is the documented design (a 73 is "Exceptional"
  word in the ≥60 emerald, not the ≥80 deep-emerald). Add a NEW score-tier-word
  surface → call `scoreTierLabel`, never a fresh local copy.

- **Press feedback is the global `.press` utility — the PRESS tier of the
  app-wide motion system, NOT a per-component Tailwind `active:`**
  (`frontend/app/globals.css` + 23 control surfaces across 7 files,
  `$impeccable animate` 2026-06-02). The motion system already had hover
  (`.hover-lift` + slate bg), keyboard focus (`:focus-visible`), entrances
  (`rise-in` / `flag-pulse` / `gauge-sweep`) and loading (`shimmer`) — but ZERO
  press/tap acknowledgment (`active:` was 0 occurrences app-wide). On touch
  there is no hover, so the press-scale is the ONLY confirmation a tap
  registered → it finishes the 44px-touch-target a11y work. `.press` =
  `transition: transform 130ms + bg/border/color/opacity 150ms ease-in-out`
  (the app-wide curve) + `:active { transform: scale(0.97) }`, reduced-motion
  guarded in the SAME guard block as `.hover-lift`. **Why a global class, not
  `active:scale-[…]` Tailwind**: (a) ONE reduced-motion off-switch covers every
  press target — a bare Tailwind `active:scale` would still shrink under
  `prefers-reduced-motion` (it has no built-in guard); (b) the comprehensive
  transition list lets `.press` cleanly REPLACE a host's `transition-colors` /
  `transition-opacity` without snapping its hover fade. **Composition with
  `.hover-lift`** (the mobile ranking CARD carries both): `.press` is defined
  AFTER `.hover-lift` so its transition wins, while hover→lift (`:hover`
  translateY) and press→scale (`:active`) stay distinct states. **Scope =
  discrete controls only** — buttons · chips · toggles · TopNav links + brand link · back-links · pagination · `PriceTimePeriodSelector` ENABLED buttons (the
  disabled ones get none; `:active` can't fire on `disabled` anyway) · the
  mobile ranking card. **NOT** the desktop `<tr>` (`transform` on a table row is
  a known rendering footgun + it already has `hover-lift`) and **NOT** the
  sortable column headers (a column-wide scale reads wrong; they keep
  `:focus-visible` + the arrow-rotate). A NEW interactive control MUST add
  `press` to stay consistent — same discipline as "a new animated component uses
  ease-in-out".

- **The home-page header is a deliberate 4-TIER hierarchy — don't re-flatten it
  to a uniform gray run** (`frontend/app/page.tsx`, `$impeccable bolder`
  2026-06-02). It previously opened with a modest `text-2xl` headline over a
  single same-weight `text-slate-500` line where the universe COUNT (the fact the
  app is about) sat at the EXACT same visual weight as the dev-only schema version
  — flat hierarchy / "too safe". Now four tiers: (1) `text-3xl sm:text-4xl
  font-slab` headline (`text-balance`); (2) a `text-base` sub-headline whose
  universe-count number is the ONE figure given presence — `font-mono
  font-semibold` in **`text-emerald-800 dark:text-emerald-300`** (the `-700`
  shade soft-remaps to oklch 56% = 4.08:1 on the body bg, which FAILS AA for
  non-large text; `-800` → oklch 50% = 5.23:1 PASS, and reads more committed),
  the single deliberate brand accent on the otherwise all-slate front door
  (product-bolder =
  stronger hierarchy + weight contrast + ONE accent, NOT color drama / no metric-
  card / no gradient); (3) a `text-xs` muted PROVENANCE line (universe · updated ·
  schema) where the schema version is demoted by POSITION (last) — NOT by a
  fainter color (the inverted `text-slate-400 dark:text-slate-500` token fails AA
  per the §Gotcha above, so the whole line stays `text-slate-500
  dark:text-slate-400`); (4) the methodology fine print (content unchanged). A NEW
  header fact goes in the tier matching its importance — never re-merge tiers 2+3
  into one gray sentence, and don't promote the schema version out of tier 3.

- **The ranking-table "no matches" empty-state is the app's ONE warm delight
  moment — keep it helpful, not wacky** (`frontend/components/RankingTable.tsx`,
  `$impeccable delight` 2026-06-02). The REACHABLE over-filtered-to-zero state
  was a flat gray line + button; it now carries a muted decorative `SearchX`
  (lucide, `aria-hidden`) anchor glyph + a `font-medium text-slate-700` heading +
  an ACTIONABLE recovery nudge ("Try a wider score range, or clear a sector or
  two") + `animate-fade-in` (reduced-motion guarded via the shared motion
  system). Product-register delight = a SPECIFIC reached moment, warm +
  recovery-oriented — finance "reads the room": warm, never playful / confetti /
  Easter-egg. A NEW empty / error / pending state should follow the same shape
  (anchor glyph + human heading + how-to-recover line), NOT a bare "no data"
  string — but do NOT scatter delight onto non-empty surfaces (delight
  everywhere = noise; the high-frequency surfaces already carry the motion
  system). `SearchX` is a NAMED lucide import (tree-shakes per the lucide
  §Gotcha); RankingTable's other icons are legacy inline SVGs (don't bulk-convert
  them — only new glyphs use lucide).

- **The stock-detail `<article>` uses a TWO-LEVEL spacing rhythm — `space-y-4`
  default (16px) + two `!mt-8` zone-seams (32px); the warnings seam is GATED so
  it never strands a gap** (`frontend/app/stock/[ticker]/page.tsx`, `$impeccable
  layout` 2026-06-02; a squint-test confirmed the prior uniform 16px read as one
  undifferentiated stack, weakest on the long mobile scroll). The page's
  cognitive zones: identity+analysis (back-link → hero → attribute tiles → price
  → pillars) · **warnings** (Tier2EventCard + RiskSummaryCard) · **valuation**
  (FairPriceBarChart + FairPriceCard) · supporting (collapsed `<details>` +
  methodology). The two highest-value seams get 32px of air: **above warnings** +
  **above valuation**. Implementation keeps the diff small + clean-stock-safe:
  the article STAYS `space-y-4` (so the big identity/analysis flow + the
  supporting footer keep 16px with NO reindent of the hero / 80-line `<details>`),
  and ONLY the warnings + valuation pairs are wrapped in `<div className="space-y-4
  !mt-8">`. **`!mt-8` (important) is REQUIRED** — a plain `mt-8` on a child of
  `space-y-4` is silently overridden by space-y's higher-specificity `> * ~ *`
  margin-top (the same footgun behind the "no per-section mb-*" rule); `!important`
  is the deliberate documented override (verified present in the compiled CSS:
  `.\!mt-8{margin-top:2rem!important}` vs space-y-4's non-important margin). The
  **warnings wrapper is gated on a page-level `hasWarningZone`** = the EXACT union
  of the two cards' null-guards (Tier2 renders iff `tier2_events` present AND ≥1
  of `going_concern_disclosure`/`non_reliance_filing`/`auditor_change`; Risk
  renders iff `risk_flags` non-empty OR `manipulation_index > 0`) — because both
  cards null-collapse to NO DOM node on a clean stock, an always-rendered `!mt-8`
  wrapper would strand a 32px void. **Keep `hasWarningZone` in lockstep with those
  cards' null conditions.** The valuation wrapper is ungated (always present → on
  a clean stock its `!mt-8` is the single pillars→valuation seam; on a flagged
  stock it follows the warnings zone). Do NOT convert the article to `space-y-8`
  + wrap every group (reindents the hero + `<details>` for no gain).

- **`HeroAttributeTiles` reserved tiles share the FILLED tile SURFACE** — only a
  dashed border + dimmed content distinguish them (`frontend/components/HeroAttributeTiles.tsx`,
  `$impeccable layout` 2026-06-02). The reserved (Dividend / Type "Coming soon")
  tiles used a half-opacity `bg-slate-50/50` (light) / `bg-slate-900` (dark)
  surface that nearly matched the warm page bg `#F8F6F3` → the placeholders
  vanished and the 4-tile row "floated" at squint distance (esp. mobile). Now
  reserved tiles use the SAME `bg-slate-50 dark:bg-slate-800/40` surface as
  filled tiles, so the row reads as one cohesive band; the DASHED border + dimmed
  icon (`text-slate-300 dark:text-slate-600`) + "Coming soon" sub-line (NOT a
  fainter surface) carry the reserved signal so placeholders stay quiet without
  disappearing. Don't revert to a half-opacity reserved surface, and don't wrap
  the tile grid in an outer card (the tiles are mini-cards — that nests cards).

- **The ranking-table FLIP reshuffle is FILTER-SCOPED — never make it fire on a
  column-sort** (`frontend/lib/useFlip.ts` + `frontend/components/RankingTable.tsx`,
  `$impeccable overdrive` 2026-06-02). When a FILTER / SEARCH change reorders the
  visible rows, the surviving rows slide from their old position to the new one via
  a WAAPI `node.animate()` `translateY` (300ms, the app-wide `cubic-bezier(0.4,0,0.2,1)`
  ease-in-out, reduced-motion guarded; transform-only, so the mobile `<ul>` `space-y`
  and the desktop table's column layout are untouched — verified in-browser: 0 row
  overlaps / 0 stuck post-animation transforms / 0 column drift). `useFlip(orderKey,
  filterKey)` re-measures positions on ANY order change (`orderKey` = the visible
  tickers joined) but only PLAYS the slide when `filterKey` (the current search string) changed since the last render — on a
  sort/page change it silently re-baselines. **Why filter-scoped, not
  every-reorder**: the table is paginated (50 rows/page), so a column-SORT turns
  over the ENTIRE visible page — almost none of the new page's keys are in the
  prev-position map — so a sort-triggered FLIP animates a handful of rows while the
  rest snap, which reads as broken (browser-verified: sort fired **0** animate calls
  ×3 incl. reverse, while search fired 36 then 7). A FILTER
  keeps the survivors in the DOM and slides them as the field narrows, so partial
  animation there is SEMANTICALLY CORRECT ("the field responded to what you typed")
  and satisfies the product-register rule "motion conveys state, not decoration."
  **Contract**: every reorderable child needs `data-flip-key={stableId}` (here
  `row.ticker`); the hook SKIPS zero-height nodes, so the desktop `<tbody>` hook is a
  silent no-op on a mobile viewport (table hidden) and the mobile `<ul>` hook is a
  no-op on desktop — each animates only its own visible list. **Adding a NEW filter dimension to `RankingTable` means adding it to the `filterKey` JSON** — miss it and that dimension's changes won't trigger the slide. Do NOT switch the gate to
  `orderKey` alone or wire a `filterKey`-less `useFlip` onto a paginated list
  expecting sort to animate — that re-introduces the partial-fire-looks-broken bug.
  **Companion (entrance-stagger gate):** the row entrance cascade (`animate-rise-in`)
  is gated to play ONCE per mount — `firstRenderRef` (true on the initial SSR +
  hydration render, so no mismatch) is flipped false by an empty-dep mount effect
  that runs before any interaction, so `animateRows` is false on every later render.
  This (a) enforces design.md Motion Rule 2 "sort/filter must not re-stagger"
  uniformly (the prior `spendStagger` latch was wired only into `onSort`), and (b)
  keeps the FLIP the SOLE motion on a filter change (no entrance-fade competing on
  rows ENTERING the filtered set). Do NOT re-wire the entrance stagger to fire on
  an interaction — that revives the competition + the Rule-2 violation.

- **`exchange_coverage_pct` and `country_coverage_pct` look like siblings but
  DIVERGE on a raw passthrough code — `country_coverage_pct` is the strict
  canary** (`compute/ingest/cross_source.py` + `compute/main.py`, schema
  `0.10.13-phase4.6`, 2026-06-02 post-cron audit). `exchange_name(code)` passes
  an UNKNOWN venue code through verbatim (a non-null raw code → counts as
  "covered"), while `country_for_exchange(code)` resolves ONLY codes in
  `_US_EXCHANGE_CODES` (an unknown code → `None` → uncovered). So the two
  coverage metrics agree on known codes but diverge EXACTLY on an unknown
  passthrough: CBOE's `BTS` venue (Cboe Global Markets self-lists on Cboe BZX;
  `BTS` ≠ the already-mapped `BATS`) showed `exchange_coverage_pct = 100%`
  while country was 99.8% (CBOE country `null`). The original 0.10.12 schema
  docstring claimed "country tracks exchange 1:1 — no separate counter needed";
  that is FALSE for passthrough codes, which is precisely the blind spot
  `exchange_coverage_pct` structurally cannot see (it counts the raw code as
  covered). `country_coverage_pct` is therefore the durable canary — `main.py`
  emits a `logger.warning(...coverage divergence...)` when `country < exchange`,
  and the verify-helper can assert the gap. **Fix for a new divergence**: add
  the unknown code to `_EXCHANGE_NAME_BY_CODE` (one line fixes BOTH the exchange
  display AND the country tag, since `_US_EXCHANGE_CODES = frozenset(...keys())`
  derives from the dict). The `_coverage_pct` helper (renamed from
  `_exchange_coverage_pct`) is shared by both metrics — don't re-split it.
- **Whole-app polish conventions (`$impeccable polish "all app"`, 2026-06-03):
  empty-state CTA is DISABLED not just styled · a labeled chip inside an
  `aria-label`'d container is `aria-hidden` · `ring-rose-300` is never a chip
  ring · valuation sections own no `mb-*`** (audit by `frontend-design-reviewer`
  + `expert-user-explorer`, the latter built + drove the real app via Playwright).
  Four reusable rules surfaced/reinforced: (1) **An empty-state primary CTA must be `disabled` + de-emphasized when it would yield 0 results** — a bright emerald CTA must never invite a click toward a 0-result screen. Apply to any future modal/drawer CTA with a result count. (2) **A `RecommendationBadge`
  (or any labeled chip) embedded in a container that ALREADY carries its own
  `aria-label`** — the stock-detail `<h1>` (`aria-label="TICKER — Rec"`) — is
  wrapped in `<span aria-hidden="true">` so SR doesn't double-read "NVDASell"; it
  STAYS announced where it's the sole source (the ranking-table ticker cell — do
  NOT aria-hide it there). (3) **`ring-rose-300` is never a negative chip ring** —
  the `globals.css` soft-OKLCH allowlist only remaps `-200` (raw `-300` =
  alarm-pink); `RiskSummaryCard` (band / outer-ring / gate-chip) + `FairPriceBarChart`
  "Heavily overvalued" headline were the last holdouts, now `-200` (extends the
  "negative-strong rings use soft -200" rule; `FairPriceBarChart`'s `outlier`
  verdict keeps `ring-slate-300` BY DESIGN — a muted tone, not a negative ring).
  (4) **Detail-page valuation sections own NO `mb-*`** — the `<article>`
  `space-y-4 !mt-8` wrapper owns the gaps; `FairPriceBarChart`'s outer `mb-4` was
  a 32px double-gap holdout (same fix as the `PillarRadarChart mb-4`). Also folded
  in (one-offs): `FairPriceCard` stat grid is now a real `<dl>` (was a `<div>` with
  orphaned `<dt>/<dd>` — invalid HTML on every stock); `Tier2EventCard` severity
  chip dropped its bogus `role="status"` live region (static content); `HeroAttributeTiles` `aria-labelledby` (kill double-announce); `CurrentPriceLine` negative `text-rose-600 → -700` (allowlist);
  `ScoreBadge` md `font-bold → -semibold` (numeric family).
  DEFERRED at the time: a P3 cross-stock compare view was scoped then removed (PR #412). The `FairPriceCard` raw flag humanization was RESOLVED in the follow-up — see the footer build-version gotcha below.

- **Footer build-version chip = build-time `NEXT_PUBLIC_APP_VERSION`, never a
  hardcoded version** (`frontend/next.config.js` + `frontend/components/AppShell.tsx`
  footer — relocated there 2026-06-04 when the Sidebar was removed; was the Sidebar
  footer originally, 2026-06-03; resolves the #392-deferred stale `v1.4.0`). A hardcoded version
  string goes stale the instant `main` moves past the release tag — the chip read
  `v1.4.0` for 30+ PRs while the deployed site was well ahead. `next.config.js`
  now computes `NEXT_PUBLIC_APP_VERSION` at build via an `env:` block: explicit
  env override → `git describe --tags --always --dirty` (reformatted
  `TAG-N-gSHA` → `TAG+N`, so local dev with tags shows e.g. `v1.4.0-phase4.6+30`)
  → `VERCEL_GIT_COMMIT_SHA` / `GITHUB_SHA` short (shallow CI/Vercel clones have NO
  tags, so production shows the 7-char commit SHA — an honest build id) → `'dev'`.
  The `AppShell` footer reads `process.env.NEXT_PUBLIC_APP_VERSION` (inlined at build
  by the `env:` config) — do NOT re-hardcode a version literal. Companion change in
  the same PR: `FairPriceCard` valuation-warning humanization `w.replace(/_/g,' ')`
  → a `VALUATION_WARNING_LABELS` map (Title-Case fallback for unknown flags) so a
  valuation warning reads the same labelled way the `RiskSummaryCard` flags do.
  (That map was later CENTRALIZED into `lib/flag-labels.ts` as `flagLabel`, which is still used by `FairPriceCard` / `PillarRadarChart` / `RiskSummaryCard`.)

- **`globals.css` soft-color override is LITERAL-class-keyed — it never reaches
  `dark:`-prefixed utilities.** The soft-color layer (which gives the muted sage /
  terracotta look without touching component class strings) is a set of plain
  `!important` rules keyed on the bare utility: `.bg-emerald-600 { background-color:
  var(--c-pos-medium) }`, `.text-emerald-700 { … }`, `.bg-rose-500 { … }`, etc.
  Tailwind compiles a `dark:` variant to a SEPARATE class token (`dark:bg-emerald-600`,
  selector `.dark .dark\:bg-emerald-600`) whose name the `.bg-emerald-600` rule does
  NOT match — so in dark mode a `dark:bg-emerald-*` / `dark:bg-rose-*` SOLID-fill
  renders RAW Tailwind, bypassing the soft remap entirely. The bite (filter theme
  audit, PRs #398 / #400 / #401): the dark "View N stocks" + "Compare N" CTAs used
  `dark:bg-emerald-600` → raw `#059669`, white label **3.77:1** (under the 4.5:1 AA
  floor for 14px text), while light `bg-emerald-700` (no `-700` override exists) was
  already a safe **5.48:1**. Fix pattern: for a dark solid-fill CTA or brand mark use
  `dark:bg-emerald-700` (Tailwind `emerald-700` = `#047857`, white 5.48:1) or drive
  the background from a `--c-*` token directly — NEVER `dark:bg-emerald-600` expecting
  the soft remap. Swept surfaces at the time: RankingTable CTAs (#401), AppShell "Q" brand mark (the deferred-items follow-up PR). (FilterDrawer and Sidebar have since been removed.) Note the `--c-*` CSS
  variables themselves DO flip per theme (`:root` vs `.dark`), so LIGHT surfaces using
  the literal classes (`bg-emerald-50`, `text-emerald-700`, …) are unaffected — this
  gotcha is dark-variant-only. The decorative `aria-hidden` Q-mark was contrast-exempt
  but swept anyway for brand consistency (it should read as the brand primary, not the
  lighter emerald-600, in both themes).

- **Build-time, server-component stats — never `import lib/data.ts` into a `'use client'`
  component** (`frontend/app/page.tsx`, `frontend/app/ranking/page.tsx`, 2026-06-04). The home
  dashboard (top-ranked / movers-today / top-sectors preview cards) + the ranking page are
  plain **Server Components** that derive EVERY value at build time from the
  already-build-imported `rankings.json` + `metadata.json` (`getRankings()` / `getMetadata()`),
  with no per-stock fetch and no loading waterfall. QuantRank is a **weekly static export**, so
  these numbers are "as of" the last compute cron — NOT a live/intra-week feed; the
  `metadata.last_update_utc` "Updated" stamp is the honesty anchor and the mover deltas are
  real `price_change_1d_pct` from that run, not streaming. Do NOT wire a genuinely live or
  intra-week market feed (or net-new index/commodity data) in as a "tweak" — that is a
  separate **observability-before-wiring** PR (new external data source, new
  `Metadata.*_coverage_pct` diagnostic, schema triple). The data layer (`lib/data.ts`, which
  imports `fs` + the JSON) must never enter the client bundle: if a `'use client'` shell needs
  server-derived content, resolve it on the server and pass the node in as a prop/child (the
  canonical "RSC-into-client-shell" pattern, same as `children`) — never `import lib/data.ts`
  (or any `fs`-touching module) into a `'use client'` component. Touch-target floor: linked
  stat/stock rows carry `min-h-[44px]` (the project interactive floor) — keep it on any new
  linked row. (History: the Seeking-Alpha-style top `MarketStatsBar` strip +
  `frontend/lib/market-stats.ts` + the `AppShell` `topBar?: React.ReactNode` slot that first
  carried this RSC-into-client-shell pattern, AND the standalone `/sectors` + `/movers` routes,
  were all REMOVED 2026-06-04 at user request; the build-time server-component rule lives on via
  the home + ranking pages.)

## `data/sp500_membership_historical.csv` is the survivorship ledger — keep it ADD/REMOVE-balanced + run the verifier

`compute/ingest/historical_universe.members_at(as_of, current_universe)` reconstructs S&P 500
membership on any past date by REVERSING the ADD/REMOVE events in
`data/sp500_membership_historical.csv` from today's anchor universe. Correctness depends on the
ledger being COMPLETE and BALANCED across the backtest window: every index change is a pair
(1 ADD entrant + 1 REMOVE leaver on the same effective date), plus a handful of genuine 1-sided
spinoff adds / market-cap removals that net out over time. A MISSING add leaves a later-joiner in
the historical universe (forward-looking leak); a MISSING remove drops a genuinely-present name
(residual survivorship). Both directions corrupt the backtest — this is the methodology-scientist
BLOCKING gate for the Phase 7.0 portfolio-backtest epic.

**After ANY edit to the CSV, run `python scripts/verify_membership_ledger.py`.** It reverse-walks
`members_at` from the live `rankings.json` universe across every month of the 2016-06 -> present
window and FAILS on (a) the reconstructed size leaving the S&P 500 band (498-506), or (b) any
ticker removed-in-window-but-still-in-universe / added-in-window-but-absent. A drift localizes the
missing/extra event to the month it appears. CAVEAT: the size-band check is net-zero-blind — it
canNOT distinguish a true rename (REMOVE+ADD, net 0) from a balanced-but-WRONG swap; rename
correctness rests on the snapshot-diff source + manual/methodology cross-check.

Conventions baked in by the Phase 7.0 PR-0 rebuild:
- **Effective date, not announcement date** (S&P announces ~1 week ahead). SVB Financial =
  ticker **SIVB**, removed effective **2023-03-15** (not the 03-13 announcement the prior ledger
  used).
- **Real tickers** — SIVB not "SVB"; **BX** = Blackstone, **BLK** = BlackRock (never confuse).
- **Per-row `source_url` = the Wikipedia change-history table** (stable + resolves). Do NOT
  hand-author `press.spglobal.com/<date>-<title>` deep links — that URL shape 404s.
- **Rename-aware (Track B 10Y rebuild — REPLACED the prior "one ticker, skip RENAME" rule):**
  a symbol change is a REMOVE-old + ADD-new pair on the rename date (e.g. Ceridian CDAY ->
  Dayforce DAY, 2024-02-01; Fiserv FISV->FI->FISV), so `members_at` returns the correct
  historical ticker for as-of data fetch. The snapshot-diff source (fja05680) is rename-aware by
  construction. The `_ACTION_RENAME` branch in `historical_universe.py` is now effectively dead
  (renames are encoded as REMOVE+ADD, not RENAME rows).
- **Events up to the cron universe anchor ARE included.** The 2026-06-02 EPAM -> FDXF (FedEx
  Freight) swap IS in the ledger — the anchor (`rankings.json` "as of" 2026-06-03) postdates the
  2026-06-02 effective date, and it fixed the latent gap behind the #429 EPAM orphan. Defer ONLY
  an event that postdates the anchor (else the reversal anchor and the ledger disagree).

History: the prior ledger had been silently feeding the Phase 4.6 survivorship harness ~30 errors
+ ~110 missing events (BLK mislabeled "Blackstone", a bogus 2024-08-30 BLL removal that was really
a 2022 BLL->BALL rename, KDP/UA/UAA date contradictions, a missing SBNY 2023-failure removal, a
scrambled 2020-06-22 add trio). PR-0 rebuilt it triangulated across S&P DJI releases + the
fja05680/sp500 maintained CSV + Wikipedia (214 events 2020-04..2026, ADD/REMOVE balanced 107/107)
and added the verifier as the gate. **Track B 10Y rebuild** then full-rebuilt it from the fja05680
snapshot-diff back to **2016-01-04 (485 events, ADD/REMOVE 243/242)** + extended `EARLIEST_EVENT_DATE`
and the verifier `WINDOW_START` 2020 -> 2016, to enable a real 10-year backtest; verifier CLEAN
across the full 10y (band 498-506, 0 months out).

## The home page IS the AI-pick portfolio (Phase 7.0 PR-4)

`frontend/app/page.tsx` was rebuilt from a rankings-preview into the AI-pick portfolio. It
consumes the point-in-time backtest artifact `frontend/public/data/portfolio/backtest_pit.json`
(produced by the `backfill-portfolio.yml` `workflow_dispatch`, NOT the weekly cron). Several
load-bearing rules:

- **Read via `fs`, never a static `import`.** `lib/data.ts` `getBacktestPIT()` uses
  `fs.readFileSync` (like `getStockDetail`), NOT `import backtestPitJson from '@/public/...'`. The
  artifact is ~1.3 MB; a static JSON `import` would (a) make `tsc` infer a giant literal type and
  (b) bundle the blob into the server build. `fs` sidesteps both and degrades gracefully (file
  absent → `null`).
- **Trim + round before it reaches the client.** `getAiPickData()` (build-time server) converts the
  full artifact into a small view model — the **net** NAV line per holding count, the four benchmark
  lines, the per-count final gross/net/conservative values, and ONLY the latest rebalance's holdings
  — all rounded to 2 dp. This is what ships in the page payload; the raw 1.3 MB (all 20 rebalances +
  full-precision floats + gross/conservative full series) never does. `null` from `getAiPickData()`
  renders a "backtest pending" state.
- **Build-time-data boundary holds.** The server `page.tsx` calls `getAiPickData()` and passes the
  result as a PROP to the `'use client'` `AiPickPortfolio`. No client component imports `lib/data.ts`
  (it pulls `fs`). Same rule as the rest of the home/ranking build-time-data surface.
- **The ADAPTIVE book is the headline; the 1-20 slider is legacy-fallback-only.** When the artifact
  carries `nav.adaptive` + `meta.adaptive_rule` (+ `rebalances[*].adaptive_count`), the AI sizes its
  own basket each rebalance — every HC-gated pick with `composite_score >= adaptive_rule.composite_min`
  (65), floor `min_picks` (5), no cap (`max_picks: null` — uncapped 2026-06-11; A2-S spike tripwire raw ≥ 25 guards the open ceiling) — and the UI shows THE one adaptive
  book with NO count slider. The adaptive book at a rebalance is the PREFIX
  `holdings[:adaptive_count]` (holdings are composite-desc) and its weights are exactly
  `weights_by_count[String(adaptive_count)]` — never recompute them. The `nav.by_count[N]` series
  remain in the artifact for analytics/experiments, and the OLD slider UI renders only when
  `nav.adaptive` is absent (an artifact generated before the adaptive rule landed) so the deploy is
  safe across the regeneration boundary. The ADAPTIVE_* constants live in ONE place
  (`scripts/backfill_portfolio_pit.py`) per methodology-scientist RATIFY 2026-06-11 (gates A1/A2/A2-S/B/C on issue #130).
- **`benchmarks.json` is NOT read by the frontend.** The chart uses `nav.benchmark` (already aligned
  to `nav.dates` + rebased at backfill time). `benchmarks.json` is the weekly-cron-owned raw close
  series (a diagnostic input to the backfill), not a frontend dependency.
- **Recharts colors** in `NavCompareChart` use hex literals (the design-system Rule 0 exception for
  Recharts adapters), sourced from the soft palette (emerald/indigo/slate) and swapped via
  `next-themes`. `SegmentedSelector` (benchmark + timeframe pickers) mirrors `PriceTimePeriodSelector`
  (the outlined-light radiogroup), so the controls read as one family with the price chart's toggle.

## Per-stock JSON for dropped tickers is auto-pruned — don't glob `stocks/` for param-gen

When a ticker leaves the ranked universe, its `frontend/public/data/stocks/{T}.json` +
`stocks/history/{T}.json` would linger forever: the weekly cron rewrites the files of every CURRENT
constituent and runs `git add frontend/public/data/`, but `git add <pathspec>` only *stages* a
deletion if the file is actually gone from the working tree — and nothing was removing the files of
tickers compute simply stopped writing. Two real cases produced orphans (the count drifted to 503
detail / 504 history vs 502 ranked, which trips production-output verification and bloats the
deploy):

- **De-listing** — `EPAM` left the S&P 500. Both `stocks/EPAM.json` and `stocks/history/EPAM.json`
  stayed behind.
- **Ticker rename** — Bank of New York Mellon changed `BK` → `BNY`. The live `BNY.*` files are
  written each run; the stale `stocks/history/BK.json` (no detail counterpart) lingered.

Fix (the chore(output) prune PR): `prune_orphan_stock_files(keep_tickers, data_dir)` in
`compute/output/writer.py`, called in `compute/main.py` **right after `write_rankings_json`**, removes
detail + history for any ticker not in the just-written rankings. The cron's existing
`git add frontend/public/data/` then stages the deletions (git ≥ 2.0 records removals under a
directory pathspec), so **no `compute-rankings.yml` change is needed**.

Load-bearing details:

- **Safety floor.** `_PRUNE_SAFETY_FLOOR = 50`: if the keep set is smaller than 50 (empty / truncated
  rankings on a degraded run) the prune is SKIPPED entirely and logs a warning — a bad run can never
  wipe `stocks/`. The live universe is ~502, and `run_weekly_compute` already aborts before the write
  step if too few tickers priced, so a healthy run is never near the floor.
- **Per-file resilience.** Each `unlink()` is wrapped so one un-removable file doesn't abort the
  whole prune; the function returns the sorted list of pruned tickers for the log line / audit.
- **History-only orphans are handled.** The prune walks BOTH `stocks/*.json` and
  `stocks/history/*.json` (non-recursive globs on each dir), so the `BK`-style case (history present,
  detail already gone) is caught.
- **The orphan never rendered a page.** `frontend/app/stock/[ticker]/page.tsx` sets
  `dynamicParams = false` and `generateStaticParams()` maps over `listTickersForStaticBuild()`, which
  reads `rankings.json` — so `/stock/<dropped>` already 404'd. This is deploy-size + verify-count
  hygiene, NOT a user-visible-page fix. **Do not "fix" param-gen by globbing the `stocks/` directory**
  — that would resurrect the orphan as a live (stale-data) page. Param-gen reads `rankings.json` by
  design; the prune keeps the data directory in lockstep with it.

## The home's annual-returns table + CAGR are DERIVED in-browser — and are the RAW signal, not the live product

The Jitta-style backtest view on the AI-pick home is built entirely from the NAV series the home
already ships — there is **no schema / compute / `backtest_pit.json` change** behind it:

- **`NavCompareChart` `money` mode** — `AiPickPortfolio` rebases each chart point to a notional
  `CHART_BASE = 10_000` (both lines start at $10,000 at the window start) and passes
  `money + baseline={CHART_BASE}`. The chart then formats axis / tooltip in USD and draws an
  **end-of-line $ value label** via a Recharts `<LabelList>` `content` renderer that returns `null`
  for every index except the last (`right` margin is widened to 60px in money mode to fit it). The
  non-money path (rebased-to-100) is unchanged and still works.
- **`AnnualReturnsTable`** — derives, per calendar year, `NAV(year-end) / NAV(prev-year-end) - 1`
  for the selected count's net line vs the chosen benchmark, plus a CAGR footer
  (`(NAV_last / NAV_first)^(1/elapsed_years) - 1`). `year-end` = the last finite NAV whose date falls
  in that year (dates are chronological). The first year is flagged `*` (partial — return since
  inception, not a full Jan-Dec year) when the window starts mid-year. Reactive to the count slider +
  benchmark picker (the parent passes the FULL `netByCount[count]` + `benchmark[bench]` series, not
  the chart's period-trimmed view).

**The honesty caveat is load-bearing — do not remove it.** The headline numbers are
WINDOW-DEPENDENT and refresh with every cron: the original 5y (2021-2026) artifact underperformed
the S&P 500 at every holding count, while the #440 10y (2016-2026) artifact has N≥3 beating SPY
full-window (N=5 net ≈ 16.6% vs SPY 15.0%; N=9 ≈ 22.4%) with the excess concentrated in 2020-2021
and 2025 lost at every N — NEVER quote either result as timeless; read the live artifact. The
in-app disclaimer is result-dependent (PR #419) so the UI self-corrects. Veto-replay state: PR #451
(Phase 7.0c) replays **6 of the 7** active vetoes point-in-time (`meta.veto_layer_replayed=True`,
`non_reliance_filing` disclosed-excluded in `meta.vetoes_not_replayed`); artifacts generated BEFORE
its first post-merge refresh still carry `veto_layer_replayed=False`. The CAGR-row caveat and the
AiPickPortfolio footnote are DATA-DRIVEN on that flag (both generations stay honest) — keep them
branching on the artifact, never hardcode either state. Even at `True`, the backtest is still not
the full live product (one veto un-replayed; annual-10-K PIT vs live TTM) — never describe the
backtest CAGR as the live product's track record.

- **`pillarColor` → `lib/visual` + `flagLabel` → `lib/flag-labels` are SHARED
  tokens — don't re-inline them** (index entry detail; moved here 2026-06-11).
  Both were introduced by the now-REMOVED compare/filter feature but remain
  load-bearing: `pillarColor` (per-pillar hue mapping) is consumed by
  `PillarRadarChart`, and `flagLabel` (risk-flag → human label map,
  centralized in `lib/flag-labels.ts`) is consumed by `FairPriceCard` /
  `PillarRadarChart` / `RiskSummaryCard`. When adding a new pillar hue or a
  new risk-flag label, extend the shared module — re-inlining a private copy
  in a component re-creates the divergence the centralization fixed.

- **edgartools `Company("")` resolves to an ARBITRARY company — no raise**
  (found 2026-06-12 by the Phase-8 scout, PR #467). With an EDGAR identity
  set, `Company("")` constructs successfully and resolves to a seemingly
  random CIK (observed: 1816125) instead of raising — any downstream
  history/filing fetch then silently returns the WRONG COMPANY's data;
  without an identity it raises immediately. Discipline: never pass a
  possibly-empty CIK to `Company(...)` / `fetch_fundamentals_history(...)`;
  resolve first via the fundamentals snapshot's `.cik`, falling back to
  `str(Company(ticker).cik).zfill(10)`. Related semantics: production
  `fetch_fundamentals(ticker, cik="")` survives because `_build_snapshot`
  does `Company(cik or ticker)`, BUT an empty CIK keys the snapshot-cache
  read AND write on `""` — every such call is a live EDGAR round-trip
  (cache bypassed both directions) and the returned snapshot carries
  `.cik = ""`. Any non-S&P-500 ingest caller (scout, Phase-8 pilot) must
  resolve the CIK explicitly before history fetches; the in-universe
  production path is unaffected (universe.py supplies real CIKs). Guard
  idea for the Phase-8 pilot PR: assert non-empty CIK at the
  `_build_annual_history` boundary.

- **Backtest PIT data is parquet-gated + graceful-degrading; `meta.validation`
  is the OOS-honesty surface** (added 2026-06-13, the backtest-honesty
  hardening sprint). Two committed data artifacts close the backtest's
  disclosed PIT proxies, both LOAD-BEARING on graceful degradation —
  **with either parquet absent the backtest output is BYTE-IDENTICAL** to
  the pre-data state, so the wiring is inert until the data is present and
  a `backfill-portfolio.yml` rerun runs:
  - `data/historical_sector.parquet` (Wikipedia revision history via
    `scripts/backfill_historical_sector.py`; sector NAMES only — CC BY-SA /
    Feist 1991, NOT the proprietary GICS code taxonomy) — `sector_at(ticker,
    as_of)` (`compute/ingest/historical_sector.py`) gives the PIT GICS
    sector; absent OR ticker/date-miss → falls back to today's universe
    sector. Drives `meta.sector_from_today` DYNAMICALLY (False only when
    present + used).
  - `data/pit_item402_history.parquet` (SEC EFTS via
    `scripts/backfill_item402_history.py`; SEC public domain) —
    `item402_filings_for(ticker, before_date)` (`compute/ingest/historical_8k.py`)
    gives the PIT 8-K Item 4.02 slice (`filing_date <= T`); feeds
    `check_non_reliance` so the 7th veto (`non_reliance_filing`) replays
    only when present. Drives `meta.vetoes_replayed` / `vetoes_not_replayed`
    DYNAMICALLY.
  - **Both parquets are whitelisted past the global `*.parquet` gitignore
    rule** (`!data/historical_sector.parquet` / `!data/pit_item402_history.parquet`),
    tracked alongside `data/sp500_membership_historical.csv`. They are
    small deterministic artifacts (~31 KB / ~3.5 KB), regenerated by the
    backfill scripts — do NOT hand-edit.
  - **EFTS gotcha:** the SEC full-text-search `_source` object uses
    `ciks` (LIST of 10-digit zero-padded CIK strings), `adsh` (the
    accession number), `items` (the 8-K item codes the filing actually
    contains), and `file_date` — there is NO `entity_id` or `file_num`
    accession field. Reading the wrong keys silently drops EVERY hit (a
    real 68-hits→0-rows bug, fixed 2026-06-13). Confirm Item 4.02 via the
    `items` field (authoritative, EFTS-indexed) rather than an HTML fetch;
    retry `_fetch_efts_page` on 5xx (EFTS returns sporadic 500s), not just
    429.
  - **`meta.validation`** (the OOS-validation block, emitted by
    `compute/validation/basket_rule_validation.py` via a Rule-18
    try/except → null on failure): **DSR** (Deflated Sharpe, Bailey-López
    de Prado 2014, `n_trials=15` = the 12-config grid + uncap + 2
    hold-band sweeps) is the PRIMARY gate — Φ(DSR) ≥ 0.95 lets the
    in-sample-optimized adaptive number lead the headline. **PBO** (CSCV
    over the score-once 12-config grid, `n_partitions=16`) and the
    **purged-embargo holdout** (`train[0,30)` / `purge{30}` / `test[31,40)`)
    are confirmatory. The holdout is the ONE block with `in_sample=false`
    — DSR + `walk_forward_sharpe_stability` stay `in_sample=true`; never
    relabel them OOS. The grid is emitted score-ONCE (the `by_count`
    ladder pattern generalized to 2-D: scoring is config-independent, so
    12 thresholds fork from one scoring pass — <2 min added, not a 12×
    rebuild). PBO carries a `config_correlation_note` (the 12 columns
    share thresholds → correlated → a low PBO must not be over-read).
