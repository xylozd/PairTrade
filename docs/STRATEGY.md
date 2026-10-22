# Strategy Specification — NSE Intraday Pair Trading

**Date:** 2026-10-22
**Companion to:** `project.md` (design), `MASTER-PLAN.md` (plan), `MCP-SERVERS-AND-SKILLS.md` (tooling)
**Version:** 2 — revised after technical research pass (see §0)

---

## 0. Research Findings That Changed This Document

A research pass against upstream sources (PyPI/npm registries, package source trees, live probes) produced findings that materially corrected version 1 of this spec. The important ones:

| Finding | Impact on this document |
|---------|------------------------|
| **yfinance caps 5-minute data at 60 days** (verified in `yfinance` 1.7.0 source — `min_lookbacks = {"30m","15m","5m","2m": timedelta(days=60)}`) | **The 1-year 5-minute backtest cannot be done on free data.** §6.2 and Phase 1 are rewritten. |
| **NSE's public JSON API returns 403 to plain HTTP clients** (Akamai Bot Manager — verified by direct probe) | Live quotes need a broker feed or headless browser, not the NSE website API. §3.1 |
| **STT is 0.08% on the sell side for equity delivery** (revised down from 0.1% in a recent Union Budget), and intraday equity in the cash segment is treated as delivery for STT | My original 0.025% figure was wrong. §5.3 costs roughly **tripled**. |
| **A two-leg pair round trip is 4 fills** | Round-trip cost is ~**0.25% of pair notional**, not 0.08–0.12%. This is the central viability constraint. §5.3 |
| **Cointegration is a daily-horizon concept**; at 5 minutes the spread's stationarity is mostly shared intraday beta and bid-ask bounce | §7 premise risk is elevated from "not settled" to "likely negative after costs." |
| **`aioredis` is dead** (last release Dec 2021); `redis.asyncio` inside redis-py 8.x is the replacement | §10 stack |
| **APScheduler 4.x is still pre-release alpha** ("do NOT use this release in production!") | Use 3.11.3, not 4.x |
| **Tailwind v4 moved to CSS-first config** — `tailwind.config.js` is no longer auto-loaded | Phase 0 task 0.9 |
| **`backtrader` is unmaintained** (last release April 2023); `backtesting.py` is single-asset only | Phase 2 uses a custom event-driven loop |
| **Point-in-time index membership is mandatory**; today's Nifty list is survivorship bias | §2 and §6.5 |
| **Corporate actions in one leg destroy cointegration** — a fake spread | §3.1 |

Version numbers below were verified against PyPI and the npm registry on 2026-10-22.

---

## 1. Strategy Summary

**Intraday statistical arbitrage via cointegration mean-reversion on NSE equities.**

Trade pairs of NSE-listed stocks sharing a stable long-run price relationship. When one drifts away from that relationship within a session, open a market-neutral position (long the cheap leg, short the expensive leg) expecting convergence before the close. All positions are squared off the same day.

**Honest framing:** this is better described as *intraday spread monitoring with a live paper-trading engine* than as a proven profitable strategy. The paper-trading phase is the primary experiment — it exists to **measure** whether the edge exists, not to merely validate a known-good strategy. See §7.

---

## 2. Universe Selection

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Universe** | Nifty 200 constituents, **point-in-time** | Nifty 50 → ~1,225 candidate pairs (too few); Nifty 500 → ~125k (too many to re-test). |
| **Point-in-time membership** | **Mandatory.** Reconstruct from daily bhavcopy symbol presence + index-change events | Using today's list is textbook survivorship bias — see §6.5. |
| **Snapshot discipline** | Persist a dated copy of **every** symbol list ever fetched, with a validity interval | Once fetched, the historical version is unrecoverable. Archive on first fetch. |
| **Liquidity filter** | 30-day median 5-min bar value ≥ ₹50 lakh; order size ≤ 5–10% of typical 5-min bar volume | Illiquid names show beautiful cointegration and untradeable fills. |
| **Data coverage** | ≥ 95% bar coverage in trailing 30 sessions | Gaps break the spread calculation. |
| **Corporate-action screen** | Exclude pairs where either leg had a split/bonus/dividend inside the lookback | A split in one leg creates a fake unit root in the spread. |
| **Circuit exclusion** | Exclude securities in a price band at screen time | A circuit on one leg leaves the pair unhedged — see §5.4. |
| **Re-screen cadence** | Weekly, Sunday 18:00 IST | Cointegration decays. |
| **Max concurrent pairs** | 10 | Bounds capital and blast radius. |

---

## 3. Data Layer

### 3.1 Provider reality (verified 2026-10-22)

| Provider | Intraday 5-min history | Verdict |
|----------|------------------------|---------|
| **yfinance 1.7.0** | **60 days max** (hard-coded in source) | Free prototype / rolling pilot only. **Cannot** do a 1-year backtest. |
| **nselib 2.5.1 / nsepython 2.101** | **None** — all 40+ endpoints are daily bhavcopy, corporate actions, block deals | Useful for symbol lists + daily data only. |
| **nsepy 0.8** | Last release **2020-03-07** | **Abandoned — do not use.** |
| **Dhan `dhanhq` 2.3.0** | 5-minute interval, **last 5 trading days** (`POST /charts/intraday`) | Best free-ish intraday source. Enough for live pilot, not for backtest. |
| **Upstox `upstox-python-sdk` 2.30.0** | Current trading day only | Live pilot only. |
| **Zerodha `kiteconnect` 5.2.2** | Intraday needs a **paid historical-data entitlement** | The realistic path to real history. |
| **Angel One `smartapi-python` 1.5.5** | `getCandleData` | Has a UAT base URL — the only sandbox hint found. |
| **IEX Cloud** | **Shut down (Aug 2024)** | Do not plan around it. |
| **Paid vendors** | TrueData, GDF, IEX, NSE paid products, Twelve Data, TradingView | The only route to a genuine 1-year 5-min dataset for a large universe. |

**Live quotes:** the official NSE JSON API (`/api/quote-equity`, `/api/chart-of-equity`) is **not reliably callable** — direct probes returned **403** (Akamai Bot Manager: `_abck` / `bm_sz` cookies + TLS fingerprinting) even with a browser UA, `Referer`, and warmed cookies. It is an undocumented scrape target with no rate limit or SLA.

**Therefore: live quotes come from a broker WebSocket feed, not from nseindia.com.** Verified SDK support for WebSocket: Angel One (`smartWebSocketV2.py` — binary protocol, best-5 + depth-20), Upstox (`websocket_api.py`), Zerodha (`connect.py`), Dhan (`_market_feed.py`, `fulldepth.py` — a 20-level depth feed).

### 3.2 Architectural consequence

Every provider sits behind **one `BarStore` interface**. The strategy engine never knows where bars came from. The backtester accepts whatever date range a provider can satisfy.

```python
class BarStore(Protocol):
    def bars(self, symbols, start, end, interval) -> pl.DataFrame: ...
    def symbol_master(self, as_of: date) -> pl.DataFrame: ...   # point-in-time
    def corporate_actions(self, symbols, start, end) -> pl.DataFrame: ...
```

**Never let a provider's lookback limit leak into the schema or strategy config.**

### 3.3 Storage

- **Bar store:** Parquet partitioned by `symbol`/`date`; queried with **DuckDB 2.0.0** (reads Parquet natively, pushes the screening join into SQL).
- **Wide panel:** **Polars 2.0.0** lazy API with rolling expressions over one column per symbol — dramatically faster than pandas for this shape.
- **Operational store:** **PostgreSQL** for users, signals, positions, trades, equity curve — **not** for bar analytics.
- **Redis 8.1.0** (`redis.asyncio`) for the live price cache and signal pub/sub.

---

## 4. Cointegration Engine

### 4.1 Pair screening (weekly, offline)

For each candidate pair $(i,j)$:

1. **Align** the last 60 sessions of 5-minute closes on timestamp.
2. **Adjust for corporate actions first** — a split in one leg creates a fake unit root and a guaranteed live loss.
3. **Log transform:** $\log P$. Makes the relationship multiplicative and stabilises variance.
4. **OLS hedge ratio:** $\log P_i = \alpha + \beta \log P_j + \epsilon$
5. **Spread:** $S_t = \log P_{i,t} - \alpha - \beta \log P_{j,t}$
6. **Engle-Granger:** ADF on $S_t$ — statistic < −2.86 (5%) **and** p-value < 0.05 → accept.
7. **Guards (all must pass):**
   - ADF stationary in **both** leg orderings (guards against spurious one-directional regression)
   - Half-life $\frac{\ln 2}{|\lambda|}$ where $\lambda$ is the AR(1) coefficient of $S_t$ → **≤ 30 bars** (2.5 hours). A longer half-life cannot complete intraday.
   - Spread volatility not in the bottom decile
   - Neither leg in a price band / circuit
   - **Edge-to-cost ratio ≥ 3×** — see §5.3. This is a hard gate, not a nicety.

### 4.2 Efficient screening over a large universe

Naive O(N²) over 500 names is ~125k pairs, and `statsmodels.coint` runs a Johansen eigen-decomposition per call (~ms). 125k pairs × rolling windows is hours. The approach:

1. **Pre-filter hard** — sector + market cap + liquidity → 50–150 tradeable names → ~1.2k–11k pairs. A 10–100× reduction for free.
2. **Vectorise the gate** — rolling correlation and rolling OLS on a (T × N) returns matrix are matrix ops.
3. **Call `statsmodels.coint` / `adfuller` only on survivors.**
4. **Numba 0.68.0** `@njit(parallel=True)` for the rolling regression and half-life kernels.
5. **DuckDB** to push the screening join into SQL over the Parquet dataset.

### 4.3 Live z-score (every 5 minutes, market hours)

Using the **frozen** coefficients $(\alpha,\beta)$ from the weekly screen — never refit intraday, since refitting on drifting data is a classic source of backtest/live divergence.

$$Z_t = \frac{S_t - \mu_S}{\sigma_S}$$

with $\mu_S, \sigma_S$ frozen from the 60-session screening window.

**Why frozen:** a rolling intraday window lets the z-score chase its own tail — the spread drifts out, the window recentres on the new level, and the signal never fires.

**Optional upgrade (Phase 2, behind a flag):** a fixed 2σ band is wrong intraday because volatility is **U-shaped across the session** (open spike, close spike). A conditional band — z-score against **time-of-day-normalised** $\sigma$, optionally with GARCH on the spread's variance (**`arch` 8.0.0**) — is more defensible. Fit GARCH **only on selected pairs**, never on the universe; it is expensive.

> `arch` is a **conditional-volatility** library (GARCH/EGARCH/DCC), **not** a cointegration engine. Cointegration comes from `statsmodels` (`coint`, `adfuller`, `coint_johansen`, `VECM`).

---

## 5. Signal Generation and Risk

### 5.1 Thresholds

| Parameter | Default | Notes |
|-----------|---------|-------|
| Entry | $\lvert Z_t \rvert > 2.0$ | Per-pair from screen output |
| Exit | $\lvert Z_t \rvert < 0.5$ | Mean reversion achieved |
| Stop-loss | $\lvert Z_t \rvert > 3.5$ | Thesis broken |
| Max hold | 45 bars (3h45m) | Intraday cap |
| Min hold | 3 bars (15 min) | Reduces churn |
| Hard entry cutoff | 14:45 IST | Leaves room to square off before the 15:20 auto-square-off |
| **Auto square-off** | **15:20 IST** | Broker/exchange enforced — confirm the exact per-broker time |

### 5.2 Entry logic

```
IF pair cointegrated AND enabled
AND |Z_t| > 2.0
AND no open position for this pair
AND now < 14:45 IST
AND daily_loss_limit NOT breached
AND capital_available >= required_notional
AND edge_to_cost_ratio(pair) >= 3.0
THEN:
    IF Z_t > +2.0:  SELL i (rich leg) ; BUY j (cheap leg), qty_j = qty_i * beta
    IF Z_t < -2.0:  BUY  i (cheap leg); SELL j (rich leg), qty_j = qty_i * beta
```

**Position sizing** — equal notional per leg, rounded down to whole shares:
$$q_i = \left\lfloor \frac{N}{P_i} \right\rfloor, \quad q_j = \left\lfloor \frac{q_i \beta}{P_j} \right\rfloor$$

### 5.3 Transaction costs — the central constraint ⚠️

**Per-fill rates (verify against your broker's current rate card before backtesting — these change):**

| Component | Approx. rate | Side |
|-----------|--------------|------|
| Brokerage | ₹20 per executed order (typical discount broker) | per order |
| **STT** | **0.08%** on equity delivery/intraday-equity | **sell only** |
| Exchange transaction (NSE) | ~0.00297% | both |
| SEBI turnover | ₹10 per crore (0.0001%) | both |
| IPST | ₹3 per crore (0.00003%) | both |
| **GST** | **18%** on (brokerage + exchange + SEBI + IPST) — **not** on STT or stamp duty | both |
| Stamp duty | ~0.003% intraday / 0.015% delivery | **buy only** |

**Per-leg round trip:** sell side ≈ 0.084%, buy side ≈ 0.007%, plus ₹40 brokerage.
**Two-leg pair round trip = 4 fills ≈ 0.18% of pair notional + ₹80 brokerage.**
At ₹1,00,000 notional: **~₹260 per pair trade, round trip.**

> ⚠️ **This is roughly 2.5× my original estimate and it changes the viability calculus.** A 2σ entry that reverts to 0.5σ must capture **>0.26%** just to break even. Many intraday mean-reversion spreads travel less than that. **Hence the hard gate: reject any pair whose expected gross edge per trade is < 3× modelled round-trip cost.** Build the cost model **first** and make it a first-class, dated, versioned parameter — not a blended bps fudge.

### 5.4 Risk limits and circuit breakers

| Limit | Value |
|-------|-------|
| Max notional per pair | ₹1,00,000 |
| Max total gross exposure | ₹5,00,000 |
| Max daily loss per user | ₹50,000 |
| Max loss per trade | ₹7,500 |
| Max concurrent open pairs | 10 |
| Max trades per user per day | 50 |
| Entry cutoff / square-off | 14:45 / 15:20 IST |

| Trigger | Action |
|---------|--------|
| Daily loss ≥ ₹50,000 | Halt session, square off all |
| 3 consecutive losses on one pair | Disable that pair for the session |
| Total drawdown > 20% | Global halt, admin re-enable required |
| Data feed stale > 90s | Suspend entries (keep monitoring positions) |
| **Circuit on one leg** | **Immediately flatten the other leg** — the pair is unhedged and the cointegration estimate is invalidated for the day |
| Market closed / holiday | No entries |

### 5.5 Fill realism

- **Signal on bar close, fill at next bar's open.** Never fill at the signal bar's close.
- **Second leg pays the spread and fills at the worse side.** Both legs cannot fill simultaneously; the illiquid leg is where the edge leaks. This assumption alone can flip a profitable backtest to a loss — keep it conservative.
- **Tick size ₹0.05** for most scrips (₹0.01 for some sub-₹250 instruments) — real quantization, material for low-priced stocks. Never build a pair whose expected profit is smaller than a few tick sizes.
- **The 5-minute bar's high/low is a range, not a spread.** Inferring execution price from bar extremes systematically overstates fills.

---

## 6. Backtest Specification

### 6.1 Method

**Custom event-driven, bar-by-bar loop.** Not `backtrader` (unmaintained, last release April 2023), not `backtesting.py` (maintained, but **single-asset, single-direction** — a poor fit for two-leg pairs without heavy customisation). `vectorbt` 1.2.0 is available if vectorised comparison is wanted, but note it is **fair-code** (Apache-2.0 + Commons Clause) with a paid PRO tier for the good features.

The rules here are genuinely stateful (entry, holding time, stop-loss, concurrent pairs, capital constraints, forced square-offs) — a stateful loop is the correct tool.

### 6.2 Data requirements

| Requirement | Detail |
|-------------|--------|
| Window | 1 year of 5-min OHLCV for the universe |
| Source | **Must be purchased or broker-entitled.** yfinance's 60-day cap makes free data impossible for this window. See §3.1. |
| Storage | Parquet + DuckDB; wide panel via Polars |
| Adjustments | Corporate-action-adjusted for screening; **raw prices for execution** |
| Universe | Point-in-time, archived snapshots |

**Budget for data before writing strategy code.** If no paid entitlement is available, the honest fallback is a **60-day rolling walk-forward** on yfinance — still a valid experiment, but a weaker claim, and it must be labelled as such.

### 6.3 Backtest loop

```
FOR each trading_day:
    FOR each bar_t (09:15 → 15:20 IST):
        # 1. Update Z-scores for all cointegrated pairs (frozen α, β, μ, σ)
        # 2. Manage OPEN positions, in priority order
        FOR each open_position:
            IF now >= 15:05:            close (session cutoff)
            ELIF holding_bars >= 45:    close (max hold)
            ELIF |Z| > 3.5:             close (stop-loss)
            ELIF |Z| < 0.5:             close (take-profit)
        # 3. Fill orders placed last bar at THIS bar's open
        # 4. Check portfolio circuit breakers (daily loss, drawdown, circuit hits)
        # 5. Generate NEW entries (cutoff 14:45)
        # 6. Mark to market; update equity curve
```

### 6.4 Metrics

| Metric | Target |
|--------|--------|
| **Sharpe (annualised, rf ≈ 6.5%)** | > 1.5 |
| **Deflated Sharpe ratio** | Report alongside — a raw Sharpe > 3 on 5-min NSE pairs is a bug until proven otherwise |
| Max drawdown | < 20% |
| Total P&L after costs | Positive |
| Win rate | > 55% |
| Profit factor | > 1.3 |
| Trades per day | 1–4 |
| Avg holding period | < 60 min |
| **Sharpe with vs. without costs** | **Gap < 30%** — if costs destroy the edge, there is no edge |
| **PBO (probability of backtest overfitting)** | Report — scanning thousands of pairs finds "significant" ones by construction |

### 6.5 Bias checks (verify, do not assume)

| Bias | Check |
|-------|-------|
| **Lookahead** | Signal on bar $t$, fill on bar $t{+}1$ open. Assert in a test that no fill uses the signal bar's close. |
| **Survivorship** | Point-in-time membership including delisted symbols, reconstructed from bhavcopy presence + index-change events. |
| **Selection** | **Walk-forward**: screen on weeks 1..T, trade week T+1, roll forward. Never screen on the full year then trade it. |
| **Multiple testing** | Deflated Sharpe + PBO across the pair universe. |
| **Corporate actions** | Adjust both legs before screening; a split in one leg manufactures a fake spread. |
| **Overfitting** | Held-out period never used for screening or threshold tuning. |
| **Costs** | Full per-leg model applied to every fill, including the worse-side second-leg assumption. |
| **Sessions** | Only 09:15–15:20. No filling on the 15:30 close bar. The 15:20–15:30 closing pre-open session has poor liquidity — do not assume a clean fill. |

---

## 7. Known Challenges — Stated Plainly

| Challenge | Reality |
|-----------|---------|
| **The premise is probably weak** ⚠️ | Cointegration is a **daily-horizon** concept. Classical pairs-trading results (Gatev et al.; Do & Faff on NSE) are overwhelmingly daily. At 5 minutes, spread stationarity is mostly (a) **shared intraday beta** and (b) **bid-ask bounce** — not a stable fundamental linkage. The economic logic (shared supply chain, common input, index membership) arbitrages away over weeks, not minutes. |
| **Reversal premium is a liquidity-provision payment** | The classic microstructure result (Hou–Hochschild–Scherbina 2011; Almgren–Chao 2000) is that short-horizon reversal profits are compensation for providing liquidity — **exactly offset by crossing the spread.** At ~0.25% per pair round trip, the premium is gone. |
| **Costs are the same order as the edge** | Gross capture per trade is a fraction of a percent; costs are ~0.25%. Costs can consume 50–100% of the edge. **This is the most likely reason a naive backtest shows profits and live trading shows nothing.** |
| **Non-stationarity is worse intraday** | Index reconstitution, earnings, and events can break the relationship *within one session* — and you cannot wait for reversion because the holding period is capped at ~5.5 hours. |
| **Multiple testing is severe** | Scanning thousands of pairs on 5-minute data with a rolling test finds "significant" pairs almost by construction. |
| **Intraday volatility is U-shaped** | A fixed 2σ band is wrong; the band should be time-of-day and volatility normalised. |
| **Half-life filter is restrictive** | Most cointegrated pairs have half-lives of days to weeks. Filtering to ≤ 30 bars leaves a small, more tradeable set. |
| **Correlation ≠ cointegration** | High-correlation screening produces many pairs that fail ADF. The ADF test on the spread is the real filter. |
| **Intraday shorting constraint** ⚠️ | Indian retail **delivery** accounts cannot short intraday. This needs the **MIS/intraday leverage** product, which permits intraday shorts and carries margin. If the account is delivery-only, the "short the rich leg" must be replaced by an ETF proxy — a materially different strategy. **Must be resolved before any real-money work.** |
| **Data access is the hardest engineering constraint** | No free source covers 1 year of 5-min data. See §3.1. |

### 7.1 Recommended framing change

Position the project as **"intraday spread monitoring with a live paper-trading engine"** — a legitimate and valuable product even if the raw P&L edge is thin — and let the paper-trading phase **measure** whether the edge exists rather than assume it.

Two options worth an explicit decision before Phase 2:

1. **Keep 5-minute bars** as specified. Higher cost burden, weaker premise, but it is what was asked for.
2. **Move to 15- or 30-minute bars within the session** — costs become a smaller fraction of the move, and the premise is somewhat more defensible. Still intraday.
3. **Move to daily bars with overnight holding** — by far the best-supported version of the strategy, but **violates the "purely intraday" requirement** and would need your explicit approval to change.

---

## 8. Phase Plan

Full file-level plan in `MASTER-PLAN.md`. Strategy-level gates:

| Phase | Deliverable | Exit gate |
|-------|-------------|-----------|
| **0 — Foundation** | Repo, venv, deps, config, Docker Compose, git init | Services start; `/health` responds |
| **1 — Data** | `BarStore` abstraction, `nse-data` MCP server, provider adapters, Parquet+DuckDB store, point-in-time symbol master, corporate-action adjustment | Target window stored and queryable; coverage ≥ 95% |
| **2 — Engine** | Cointegration screen, z-score, signals, risk, **cost model**, event-driven backtest, walk-forward, deflated Sharpe/PBO | ✅ Sharpe > 1.5 after costs, DD < 20%, no bias failures · ❌ **else stop and revisit the premise** |
| **3 — Backend** | FastAPI, JWT auth, RBAC, schema + Alembic, REST + WebSocket | Auth flow tested; every endpoint role-gated |
| **4 — Frontend** | React dashboard: login, pairs, charts, P&L, admin | Login works; live z-scores render |
| **5 — Paper trading** | `paper-broker` MCP server, order lifecycle, position management | Full unattended simulated session with correct square-off |
| **6 — Deployment** | Dockerfiles, Caddy + TLS, systemd, GitHub Actions CI/CD | Deployed; HTTPS valid; login works externally |
| **7 — Live broker** | Broker adapter behind the same interface | Sandbox validated; explicit go-live sign-off |

---

## 9. Success Criteria

| # | Criterion | Verified by |
|---|-----------|-------------|
| 1 | Weekly screen yields ≥ 15 tradable pairs, half-life ≤ 30 bars, edge-to-cost ≥ 3× | Screen output |
| 2 | Walk-forward backtest: Sharpe > 1.5 **after** full per-leg cost model | Backtest report |
| 3 | Max drawdown < 20% | Backtest report |
| 4 | Deflated Sharpe + PBO reported; no lookahead/survivorship/selection bias | Bias checklist (§6.5) |
| 5 | Sharpe with costs within 30% of Sharpe without | Backtest report |
| 6 | All endpoints reject unauthenticated and under-privileged requests | Auth test suite |
| 7 | Dashboard shows live z-scores within 5 min of bar close | Manual check |
| 8 | Risk limits enforced in code, each with a test that trips it | Risk test suite |
| 9 | Paper trading completes a session unattended with correct square-off | Phase 5 gate |
| 10 | Deployed on VPS behind HTTPS; login works from outside | Phase 6 gate |
| 11 | **Live-paper track record ≥ 100 round trips over ≥ 3 months** before any real-money gating | Phase 7 precondition |

---

## 10. Verified Stack Versions (2026-10-22)

| Backend | Version | Note |
|---------|---------|------|
| `fastapi` | **0.159.1** | |
| `pydantic` / `pydantic-settings` | **2.14.1** / 2.16.1 | |
| `uvicorn` | 0.54.0 | |
| `sqlalchemy` | **2.1.6** | **Use directly** — SQLModel 0.0.48 lags on Pydantic v2 features |
| `alembic` | 1.20.1 | |
| `asyncpg` | 0.32.0 | or `psycopg` 3.3.6 |
| `redis` | **8.1.0** | **Use `redis.asyncio` — `aioredis` is dead (2021)** |
| `apscheduler` | **3.11.3** | **4.x is pre-release alpha — "do NOT use in production!"** |
| `celery` | 5.6.3 | Heavier; also does not support Windows |
| `pyjwt` | 2.15.1 | Over `python-jose` 3.5.0 |
| `argon2-cffi` | **25.1.0** | **Over bcrypt (72-byte silent truncation; passlib 1.7.4 is from 2020)** |
| `fastapi-users` | 15.0.5 | Optional — ready-made OAuth2/JWT + user CRUD |
| `websockets` | 17.3 | |
| `httpx` | 0.28.1 | |
| `orjson` | 3.13.0 | Fast JSON on the hot tick path |

| Quant | Version | Note |
|------|---------|------|
| `statsmodels` | **0.15.0** | `coint`, `adfuller`, `coint_johansen`, `VECM` |
| `arch` | 8.0.0 | GARCH/EGARCH/DCC — **conditional vol, not cointegration** |
| `pandas` | 3.0.6 | **3.0 is a major release — breaking changes (CoW default, string dtype)** |
| `numpy` | 2.5.4 | |
| `scipy` | 1.18.1 | Requires Python ≥ 3.12, numpy ≥ 2.0 |
| `numba` | 0.68.0 | Rolling kernels |
| `polars` | 2.0.0 | **Major release — breaking changes** |
| `duckdb` | 2.0.0 | **Major release** |
| `pyarrow` | 26.0.0 | Parquet layer |
| `vectorbt` | 1.2.0 | Fair-code licence + paid PRO tier |
| `backtrader` | 1.9.78.123 | ❌ **Unmaintained (Apr 2023)** |
| `backtesting.py` | 0.6.6 | Maintained but **single-asset** — poor fit for pairs |
| `yfinance` | 1.7.0 | **60-day 5-min cap** |

| Frontend | Version | Note |
|----------|---------|------|
| `react` / `react-dom` | **19.3.1** | React 18 is on maintenance |
| `vite` | **8.3.5** | 6/7 are both superseded |
| `@vitejs/plugin-react` | 6.1.2 | |
| `typescript` | 7.0.2 | |
| `@tanstack/react-query` | **5.104.5** | REST/snapshot queries only |
| `zustand` | 5.0.16 | Holds the live WebSocket feed |
| `tailwindcss` | **4.3.3** | **v4 = CSS-first config; `tailwind.config.js` is no longer auto-loaded** |
| `lightweight-charts` | **5.2.1** | **Purpose-built for realtime candlesticks** — canvas, 60fps `update()` |
| `recharts` | 3.10.1 | Slow-moving stat tiles (equity curve, z-score) |
| `echarts` | 6.1.0 | Only if a general dashboard is needed |
| `plotly.js` | 4.1.2 | Heavy for streaming |
| `shadcn` | 4.22.1 | Supports Tailwind v4 |
| `socket.io-client` | 4.8.4 | If Socket.IO is preferred over raw WS |
| `lucide-react` | 1.61.0 | Icons |

**Charting decision:** `lightweight-charts` for the live price/spread candlestick chart + `recharts` for stat tiles. Recharts alone is too slow for dense live candles; Plotly is heavy for streaming.

**Live-feed decision:** direct **WebSocket** into a **Zustand** store for the tick feed; **TanStack Query only for REST snapshots**. Polling the quote API cannot meet the 5-minute latency goal.

---

*Strategy spec v2, 2026-10-22. Version numbers verified against PyPI/npm registries. Cost rates and square-off times require re-verification against the current broker rate card before backtesting.*
