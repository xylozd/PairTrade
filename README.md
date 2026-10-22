# NSE Intraday Pair Trading

Intraday statistical arbitrage (pair trading) on National Stock Exchange equities.
Backend (Python/FastAPI) + frontend (React/TS), deployable to a Linux VPS with JWT authentication.

**Status:** Phase 0 (foundation) in progress — backend skeleton, config, schemas and tests are in place.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/project.md`](docs/project.md) | Full design document — intent, goals, constraints, architecture, decided components |
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | Trading strategy specification — cointegration engine, signals, risk limits, backtest method, bias checks |
| [`docs/MASTER-PLAN.md`](docs/MASTER-PLAN.md) | Seven-phase implementation plan with tasks, files, and exit gates |
| [`docs/MCP-SERVERS-AND-SKILLS.md`](docs/MCP-SERVERS-AND-SKILLS.md) | Environment audit — MCP servers required, skills to use, verified tooling gaps |
| [`docs/superpowers/plans/phase0-foundation.md`](docs/superpowers/plans/phase0-foundation.md) | Phase 0 backend implementation plan — task-by-task steps and exit criteria |

---

## Quick Facts

| | |
|---|---|
| **Market** | NSE, equity spot, intraday only |
| **Session** | 09:15 – 15:20 IST (entry cutoff 14:45, auto square-off 15:20, market closes 15:30) |
| **Bars** | 5-minute OHLCV |
| **Method** | Cointegration (Engle-Granger ADF) + z-score mean reversion |
| **Entry / Exit** | \|Z\| > 2.0 → \|Z\| < 0.5, stop at \|Z\| > 3.5 |
| **Position** | Market-neutral, equal notional per leg, hedge-ratio sized |
| **Backend** | Python 3.13, FastAPI 0.159, SQLAlchemy 2.1, PostgreSQL, Redis 8.1, APScheduler 3.11, JWT (Argon2id) |
| **Frontend** | React 19, TypeScript 7, Vite 8, Tailwind v4, TanStack Query v5 + Zustand, WebSocket |
| **Deploy** | Docker Compose + Caddy (auto-TLS) on a single static-IP Ubuntu VPS |
| **Costs** | ⚠️ **~0.25% round trip per pair** (4 fills, STT 0.08% sell-side + GST + brokerage) |

---

## Two Things to Decide Before Building

| # | Decision | Why it blocks |
|---|----------|---------------|
| 1 | **Buy historical 5-minute data, or scope to 60 days?** | yfinance caps 5-min history at 60 days (verified in its source). Nothing free covers 1 year. The walk-forward backtest — the project's primary success criterion — is untestable without this. |
| 2 | **Keep 5-minute bars, or move to 15/30-minute?** | Cointegration is a daily-horizon concept. At 5 minutes the spread's stationarity is mostly shared intraday beta and bid-ask bounce, and costs (~0.25% per pair round trip) can consume the whole edge. Moving to 15/30-min bars is better-founded but changes the spec; daily bars are best-founded but break the "purely intraday" requirement. |

---

## Current Environment

| Item | Status |
|------|--------|
| Python 3.13.3 | ✅ installed |
| `.venv` virtual environment | ✅ created at project root, backend deps installed |
| Backend deps (FastAPI, SQLAlchemy, statsmodels, Polars, DuckDB …) | ✅ installed and pin-guarded by a test |
| Backend app (`/health` + CORS) | ✅ running — `uvicorn app:app` |
| Backend test suite | ✅ 89 tests passing |
| Node v22.23.3 / npm 12.2.0 | ✅ installed |
| Docker | ❌ **not installed** — required before the Phase 0 exit |
| PostgreSQL / Redis | ❌ not installed (Docker solves both) |
| Git repo | ✅ initialised — working on `feature/phase0-foundation` |
| 1-year 5-min data source | ❌ **not yet chosen — purchase decision pending** |

---

## Setup (once implementation begins)

```bash
# 1. Activate the virtual environment
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows PowerShell

# 2. Install backend dependencies
cd backend && pip install -r requirements.txt

# 3. Install frontend dependencies
cd ../frontend && npm install

# 4. Start local services (Postgres + Redis)
docker compose up -d

# 5. Run backend
cd ../backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 6. Run frontend
cd ../frontend && npm run dev     # http://localhost:5173
```

### Running the tests

```bash
# From the repo root — pytest.ini puts `backend/` on the import path
.venv/Scripts/python.exe -m pytest -q          # Windows
python -m pytest -q                            # Linux/macOS
```

`tests/unit/test_requirements.py` fails if `backend/requirements.txt` and the
installed virtualenv drift apart — reinstall with
`pip install -r backend/requirements.txt` if it does.

---

## Backend Layout (as built)

```
backend/
├── app.py            ← FastAPI entry point: GET /health, GET /, CORS
├── config.py         ← Strategy constants + dated/versioned cost model
├── schemas.py        ← Pydantic wire models (Signal, Pair, Position, …)
└── requirements.txt  ← Exact pins from docs/STRATEGY.md §10
```

---

## ⚠️ Risk Disclosure

This is a **speculative** trading strategy. Past backtest performance does not indicate future results.
The project launches in **paper-trading mode only** — no real-money broker integration ships
without explicit user approval (Phase 7).

At 5-minute horizons, intraday mean-reversion in Indian equities is **not a settled premise**,
and the research behind this design says so plainly:

- Cointegration is a **daily-horizon** concept. Classical pairs-trading results are overwhelmingly daily.
- At 5 minutes, spread stationarity is mostly **shared intraday beta** and **bid-ask bounce** — a
  liquidity-provision payment, not free alpha (Hou–Hochschild–Scherbina 2011; Almgren–Chao 2000).
- **Costs are the same order as the edge.** A two-leg pair round trip is 4 fills ≈ **0.25%** of
  notional. If typical gross capture is 0.3–0.5%, costs can consume 50–100% of it.
- Scanning thousands of pairs on 5-minute data finds "significant" pairs almost by construction —
  multiple-testing correction (deflated Sharpe, PBO) is mandatory.

The walk-forward backtest in Phase 2 is therefore a **genuine go/no-go gate**, not a formality.
If it does not show a positive edge after full transaction costs, the strategy does not ship and
the premise is revisited — including the possibility that 15/30-minute bars or daily bars are the
better-founded product.

See [`docs/STRATEGY.md`](docs/STRATEGY.md) §7 for the full list of known challenges, including the
intraday shorting constraint that determines whether the "short the rich leg" approach is even
executable on a given brokerage account.

---

*Project initialised 2026-10-22. Design v2, revised after a technical research pass.*

