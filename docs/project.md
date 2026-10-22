# NSE Intraday Pair Trading Project

**Project Scope:** Intraday statistical arbitrage pair trading on National Stock Exchange (NSE) equities.

**Why this project:** Build the infrastructure to identify cointegrated stock pairs and trade their mean-reversion movements during intraday sessions — and, critically, to **measure honestly** whether that edge exists after transaction costs.

> **Version 2 (2026-10-22)** — revised after a technical research pass. Several original claims were corrected: the data-source assumption, the transaction-cost model, and the NSE live-API assumption. See `STRATEGY.md` §0 for the full correction table. The headline change: **a 1-year 5-minute backtest requires paid data** (yfinance caps 5-min history at 60 days), and **round-trip cost per pair is ~0.25%, not 0.10%**.

---

## 1. Intent & The Why

This system automates the identification and monitoring of pair-trading opportunities in the Indian equities market (NSE). The core strategy is statistical arbitrage based on cointegration — when two historically correlated stocks deviate from their normal price relationship, the system signals a trade to profit from their eventual convergence.

**Honest framing:** this is *intraday spread monitoring with a live paper-trading engine*. The paper-trading phase is the primary experiment — it exists to measure whether the edge exists, not to validate a known-good strategy. At 5-minute horizons, intraday mean-reversion in Indian equities is a genuinely contested premise; `STRATEGY.md` §7 says so plainly.

**Target audience:** Quantitative traders, algo-trading enthusiasts, research analysts.

**Success criteria:**
- Accurately identifies cointegrated NSE stock pairs (Engle-Granger ADF-based)
- Generates intraday entry/exit signals with <5min latency
- Risk limits enforced per pair (max position size, max daily loss)
- Backtested Sharpe ratio > 1.5 after a full per-leg transaction-cost model
- Paper-trading mode with zero real-money risk at launch

---

## 2. Goals, Non-Goals & Anti-Goals

| Category | Items |
|----------|--------|
| **Goals** | • Real-time cointegration monitoring for NSE-listed stocks<br/>• Intraday signal generation (9:15 AM – 3:30 PM IST)<br/>• Web dashboard for signal visualization<br/>• Paper-trading mode<br/>• JWT-based authentication for multi-user access<br/>• Deployable on Linux server (Docker/VPS)<br/>• Python 3.13 backend with async signal processing |
| **Non-Goals** | • Overnight/positional holding (strictly intraday)<br/>• Options trading (equity spot only)<br/>• High-frequency trading (<1min bars)<br/>• Integration with broker APIs at launch (paper-trading only)<br/>• Mobile native app (web-responsive UI suffice) |
| **Anti-Goals** | • Guaranteed profits (mark clearly as speculative)<br/>• Martingale or grid strategies<br/>• Leverage > 2x intraday exposure<br/>• Real-money broker integration without explicit user control<br/>• AI/ML price prediction (use statistical methods only) |

---

## 3. Constraints

| Constraint | Detail |
|------------|--------|
| **Data source** | ⚠️ **Paid data or a broker entitlement required for a 1-year 5-min window.** yfinance caps 5-min at 60 days; nselib/nsepython are daily-only; nsepy is abandoned. Provider-agnostic `BarStore` interface. See `STRATEGY.md` §3.1 |
| **Live quotes** | ⚠️ **Broker WebSocket feed, not nseindia.com.** The NSE public JSON API returns 403 to plain HTTP clients (Akamai Bot Manager) — verified by direct probe |
| **Market hours** | 9:15 AM – 3:30 PM IST (Monday–Friday)<br/>Entry cutoff 14:45, auto square-off 15:20<br/>No trading outside these hours |
| **Risk management** | Max exposure per pair: ₹1 lakh notional<br/>Max daily loss per user: ₹50,000<br/>Circuit breaker: halt if drawdown > 20% |
| **Deployment** | Linux server (Ubuntu 22.04+), **static egress IP required** (broker IP allow-listing)<br/>Docker Compose for services<br/>Caddy for HTTPS (auto-TLS)<br/>Systemd service for backend |
| **Authentication** | JWT-based, OAuth2 optional later<br/>User roles: viewer, trader, admin<br/>Access token TTL 15 min + refresh rotation |
| **Data frequency** | 5-minute bars for signal generation<br/>Signals on bar close, fills at next bar's open |
| **Tech stack constraints** | Python 3.13 (verified working)<br/>Node.js 22 for frontend<br/>No TensorFlow/PyTorch (keep it statistical)<br/>No `backtrader` (unmaintained), no `aioredis` (dead), no APScheduler 4.x (pre-release) |

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DEPLOYMENT                            │
│  ┌─────────────┐  HTTPS  ┌─────────────────────┐           │
│  │  Frontend   │  ──────► │  Backend (FastAPI)  │           │
│  │  (React/TS) │           │  + Celery Beat     │           │
│  └─────────────┘           │  + PostgreSQL       │           │
│                           │  + Redis (cache)    │           │
│                           │  + JWT Auth         │           │
│                           └───────►┌──────────────┘           │
│                                 │  Auth Service         │
│                                 │  (JWT gen/verify)     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │  Data Processor     │
                │  (async, 5-min bars)│
                │  Cointegration     │
                │  Engine (Python)    │
                └─────────────────────┘
```

---

## 5. The How — Decided Components

### 5.1 Backend (Python FastAPI)
- **Framework:** FastAPI **0.159.1** with Pydantic **2.14.1**
- **Async model:** asyncio + uvicorn **0.54.0**
- **Scheduled tasks:** APScheduler **3.11.3** (every 5 min). ⚠️ Not 4.x — still pre-release alpha, upstream says "do NOT use in production!"
- **Database:** PostgreSQL via SQLAlchemy **2.1.6** (not SQLModel) + `asyncpg` **0.32.0**, Alembic **1.20.1**
- **Cache:** `redis` **8.1.0** using `redis.asyncio`. ⚠️ Not `aioredis` — dead since 2021
- **Auth:** PyJWT **2.15.1** + `argon2-cffi` **25.1.0**. ⚠️ Not bcrypt (72-byte silent truncation) and not passlib (2020)
- **Deployment:** Docker image, pushed to VPS, systemd service

### 5.2 Frontend (React + TypeScript)
- **Framework:** React **19.3.1** + Vite **8.3.5**
- **Language:** TypeScript **7.0.2**
- **State:** TanStack Query **5.104.5** for REST snapshots; **Zustand 5.0.16** for the live WebSocket feed
- **Charts:** `lightweight-charts` **5.2.1** for realtime candles + **Recharts 3.10.1** for stat tiles
- **UI:** TailwindCSS **4.3.3** — ⚠️ **v4 is CSS-first; `tailwind.config.js` is no longer auto-loaded**
- **Responsive:** Mobile-first, works at 1440p and 1080p

### 5.3 Data Pipeline
1. **`BarStore` abstraction** — one interface, provider adapters behind it. The strategy engine never knows where bars came from, and no provider's lookback limit leaks into the schema.
2. **Cointegration engine:** Engle-Granger + ADF (`statsmodels` 0.15.0 `coint`/`adfuller`)
3. **Rolling spread:** `S = log(P_i) - α - β·log(P_j)` with frozen coefficients
4. **Z-score trigger:** `|z| > 2.0` → entry; `|z| < 0.5` → exit
5. **Signal persistence:** PostgreSQL + Redis pub/sub; WebSocket push to the frontend

### 5.4 Trading Logic (Intraday Only)
| Condition | Action |
|-----------|--------|
| `z_score > upper_threshold` (e.g., 2.0) | **SELL** expensive stock, **BUY** cheap stock (convergence expected) |
| `z_score < lower_threshold` (e.g., -2.0) | **BUY** expensive stock, **SELL** cheap stock |
| `|z_score| < exit_threshold` (e.g., 0.5) | Close position (mean reversion achieved) |
| `|z_score| > 3.5` | Close position (stop-loss — spread diverging further) |
| **Daily P&L limit hit** | Auto-halt all positions, alert admin |
| **Circuit on one leg** | Immediately flatten the other leg — pair is unhedged |
| **14:45 IST** | No new entries |
| **15:20 IST** | Square off all open positions regardless of z-score |

### 5.5 Authentication & Authorization
- **Login flow:** POST `/auth/login` → returns access token (15 min TTL) + refresh token (rotating)
- **JWT payload:** `{sub: user_id, role: "viewer"|"trader"|"admin", iat, exp}`
- **Route protection:** `Depends[get_current_user]` on every API endpoint
- **Role limits:**
  - `viewer`: read-only dashboard, no signal generation
  - `trader`: can enable/disable pairs, view P&L, paper-trade mode
  - `admin`: user management, risk limit changes, system config

---

## 6. Parts Left to the Builder (This Document's Calls)

Items marked **RESOLVED** were settled by the research pass and are no longer open.

| Item | Status | Decision / Why it matters |
|------|--------|--------------------------|
| **Frontend charting library** | ✅ RESOLVED | `lightweight-charts` 5.2.1 (realtime candles) + Recharts 3.10.1 (stat tiles). Recharts alone is too slow for dense live candles |
| **Celery vs APScheduler** | ✅ RESOLVED | APScheduler 3.11.3. Celery is heavier and doesn't support Windows; a single-node intraday bot doesn't need multi-node fan-out |
| **Password hashing** | ✅ RESOLVED | `argon2-cffi` 25.1.0. bcrypt silently truncates at 72 bytes; passlib 1.7.4 is from 2020 |
| **Redis client** | ✅ RESOLVED | `redis.asyncio` from redis-py 8.1.0. `aioredis` is dead since 2021 |
| **Backtest framework** | ✅ RESOLVED | Custom event-driven loop. `backtrader` unmaintained since April 2023; `backtesting.py` is single-asset only — both poor fits for two-leg pairs |
| **Live quote source** | ✅ RESOLVED | Broker WebSocket feed (Angel One / Dhan / Upstox / Zerodha). The NSE public API returns 403 to plain HTTP clients |
| **Paper trading** | ✅ RESOLVED | Build our own paper adapter rather than relying on a broker sandbox — only Angel One's UAT URL was found, and broker sandboxes won't model intraday frictions anyway |
| **Specific NSE data vendor** | ⬜ OPEN | **Needs a purchase decision.** yfinance (60 days), Dhan (5 days), Zerodha/Upstox (paid entitlement), or TrueData/GDF/IEX. **Budget this before Phase 1** |
| **Pair selection thresholds** | ⬜ OPEN | ADF p-value, lookback window, half-life cap. Set from the Phase 2 walk-forward results |
| **Risk limit values** | ⬜ OPEN | Per-pair notional and daily loss limits. Defaults set in `STRATEGY.md` §5.4; tune after backtest |
| **Live broker target** | ⬜ OPEN | Angel One (refresh-token auth, `estimateCharges`) or Dhan (simplest auth, but IP allow-list). Phase 7 only |
| **OAuth2 provider** | ⬜ OPEN | None at launch; add Google/GitHub later |
| **VPS provider** | ⬜ OPEN | Any Ubuntu 22.04 host with a **static egress IP** (required for broker IP allow-listing) |

---

## 7. Project Structure (Already Created)

```
E:/D H BHARTHI/DEMO PROJECTS/AmazonQ/Omniroute/PairTrade/
├── docs/
│   ├── project.md          ← This design document
│   ├── STRATEGY.md         ← Trading strategy specification
│   ├── MASTER-PLAN.md      ← Seven-phase implementation plan
│   └── MCP-SERVERS-AND-SKILLS.md ← Tooling audit
├── backend/
│   ├── app.py              ← FastAPI entry point
│   ├── config.py           ← Config (risk limits, thresholds)
│   ├── data/
│   │   └── downloader.py   ← Historical NSE data fetcher
│   ├── engine/
│   │   └── cointegration.py← Pair scoring engine
│   ├── schemas.py          ← Pydantic models
│   ├── auth.py             ← JWT auth utilities
│   └── requirements.txt    ← Python deps
├── frontend/
│   ├── src/
│   │   ├── App.tsx         ← Main app shell
│   │   ├── index.css       ← Tailwind v4 CSS-first config (@theme)
│   │   ├── pages/
│   │   │   └── dashboard.tsx
│   │   ├── components/
│   │   │   ├── PairList.tsx
│   │   │   └── ChartPanel.tsx
│   │   └── hooks/
│   │       └── usePairs.ts
│   ├── index.html
│   └── package.json
├── alembic/                  ← DB migrations (Phase 3)
├── scripts/                  ← Deploy + backup scripts (Phase 6)
├── .github/                  ← CI/CD workflows (Phase 6)
├── data/                     ← Market data store (gitignored)
├── tests/
│   ├── unit/
│   └── integration/
├── .venv/                    ← Virtual environment (already created)
├── .gitignore                ← Created
└── README.md                 ← Project index
```

---

## 8. Next Steps (After Design Approval)

1. **Write `backend/requirements.txt`** with exact pinned versions
2. **Write `backend/app.py`** — FastAPI skeleton + JWT auth
3. **Write `frontend/package.json`** — React + Vite + Tailwind scaffolding
4. **Write `docker-compose.yml` — PostgreSQL + Redis + backend + frontend
5. **Implement data downloader** — Fetch 1 year NSE historical 5-min data
6. **Implement cointegration engine** — Statsmodels-based pair scoring
7. **Build frontend dashboard** — Real-time z-score chart + pair list
8. **Set up CI/CD** — GitHub Actions for Docker build + deploy

---

## 9. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **⚠️ The strategy premise may be wrong** | **Critical** | At 5-min horizons the spread's stationarity is mostly shared intraday beta and bid-ask bounce — a liquidity-provision payment, not free alpha. Phase 2 is a genuine go/no-go gate. If Sharpe after costs < 1.5, **stop and revisit** — consider 15/30-min bars, or daily bars (needs explicit approval, as it breaks the intraday requirement) |
| **⚠️ No free data covers the backtest window** | **Critical** | yfinance caps 5-min at 60 days. Either purchase a data entitlement, or scope the backtest to a 60-day rolling walk-forward and label it as such. Budget the purchase before Phase 1 |
| **⚠️ Costs exceed the expected edge** | **High** | A pair round trip is 4 fills ≈ **0.25%** of notional (STT 0.08% sell-side + GST + brokerage). Hard gate: reject any pair whose expected gross edge < 3× round-trip cost |
| **Multiple testing → false discovery** | High | Deflated Sharpe ratio + PBO; strict walk-forward; treat an in-sample Sharpe > 3 on 5-min data as a bug until proven otherwise |
| **Survivorship bias** | High | Point-in-time universe reconstructed from bhavcopy presence + index-change events; archive every symbol-list snapshot on first fetch |
| **Corporate actions in one leg** | High | Adjust both legs before screening — a split manufactures a fake spread and a guaranteed live loss |
| **NSE public API blocks programmatic access** | Medium | Use a broker WebSocket feed. Do not depend on nseindia.com scraping |
| **Cointegration model drift** | Medium | Re-screen weekly; log p-value decay |
| **Circuit on one leg** | Medium | Immediately flatten the other leg; terminate that pair for the day |
| **Non-simultaneous leg fills** | Medium | Conservative model: the illiquid leg fills at the worse side. This alone can flip a profitable backtest to a loss |
| **User credential leaks** | Medium | Argon2 hashing, short access-token TTL + refresh rotation, secrets only in server env files |
| **Intraday shorting not permitted** | Medium | Needs the MIS/intraday-leverage product. Delivery-only accounts need an ETF proxy — a materially different strategy. Resolve before Phase 7 |
| **Broker IP allow-listing** | Medium | Deploy to a single VPS with a static egress IP; no serverless, no autoscaling to a different IP |
| **Cointegration breaks intraday** | Medium | Events can break the relationship within a session; holding time is capped at ~5.5 hours |
| **Docker image size** | Low | Multi-stage builds; final image < 200MB |

---

## 10. Quick-Start Commands (After Code Written)

```bash
# 1. Activate venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows PowerShell

# 2. Install backend deps
cd backend && pip install -r requirements.txt

# 3. Install frontend deps
cd ../frontend && npm install

# 4. Start services
docker compose up -d      # PostgreSQL + Redis

# 5. Run backend
cd ../backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 6. Run frontend  
cd ../frontend && npm run dev   # Vite dev server at http://localhost:5173
```

---

*Document generated on 2026-10-22 as part of pair trading project design.*