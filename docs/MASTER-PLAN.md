# Master Implementation Plan — NSE Intraday Pair Trading

**Date:** 2026-10-22
**Read first:** `project.md` (design) → `STRATEGY.md` (trading logic) → `MCP-SERVERS-AND-SKILLS.md` (tooling)

**Status:** Planning only. No application code written yet.

> **Version 2** — revised after a technical research pass that corrected the data-source assumption, the transaction-cost model, and several library-version choices. See `STRATEGY.md` §0 for the full correction table.

---

## 0. How This Plan Is Structured

Seven phases. Each phase has:
- **Goal** — what it delivers
- **Files** — what gets created or changed
- **Tasks** — ordered, each independently verifiable
- **Exit gate** — the condition that must hold before the next phase starts

Phases are gated. Two gates are hard:
- **Before Phase 1:** a data-source decision (free 60-day scope vs. paid 1-year scope).
- **Phase 2 → 3:** **if the walk-forward backtest does not show a positive edge after costs, stop and revisit the premise.** Do not build a frontend for a strategy that does not work.

---

## Phase 0 — Foundation

**Goal:** Repo, environment, dependencies, and local services running.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 0.1 | `git init`, add `.gitignore` (`.venv/`, `__pycache__/`, `.env`, `data/`, `node_modules/`) | `git status` clean |
| 0.2 | Commit `docs/` as the first commit | `git log` shows 1 commit |
| 0.3 | Write `backend/requirements.txt` with pinned versions (see `STRATEGY.md` §10) | — |
| 0.4 | Install backend deps into existing `.venv` | `.venv/Scripts/python -c "import fastapi, statsmodels"` |
| 0.5 | Write `docker-compose.yml` — Postgres 15 + Redis 7 | `docker compose up -d` → both healthy |
| 0.6 | Write `backend/config.py` — pydantic-settings config from env | `.venv/Scripts/python -c "from config import settings; print(settings)"` |
| 0.7 | Write `backend/app.py` — FastAPI skeleton + `/health` + CORS | `curl localhost:8000/health` → `{"status":"ok"}` |
| 0.8 | Write `backend/schemas.py` — Pydantic models | — |
| 0.9 | Write `frontend/package.json`, `vite.config.ts`, `index.html`, and **Tailwind v4 CSS-first config** — ⚠️ no `tailwind.config.js`, v4 does not auto-load it | `npm install` succeeds, `npm run dev` serves a page |
| 0.10 | Write `.env.example` (no real secrets) | — |
| 0.11 | **Install Docker Desktop** — not present on this machine, required for 0.5 | `docker --version` works |

### Files created
```
.gitignore
.env.example
docker-compose.yml
backend/requirements.txt
backend/config.py
backend/app.py
backend/schemas.py
frontend/package.json
frontend/vite.config.ts
frontend/index.html
frontend/src/index.css          ← Tailwind v4: @import "tailwindcss" + @theme
frontend/src/main.tsx
frontend/src/App.tsx
```

**Exit gate:** `docker compose up -d` healthy; `/health` responds; backend imports; frontend dev server starts.

---

## Phase 1 — Data Layer

**Goal:** Provider-agnostic bar storage covering the target window of 5-minute OHLCV, with point-in-time symbol membership and corporate-action adjustment.

> ⚠️ **The data-source decision must be made before this phase.** yfinance caps 5-minute data at 60 days; nothing free covers 1 year. Either purchase an entitlement (Dhan / Zerodha / Upstox / TrueData / GDF / IEX) or scope the backtest to a 60-day rolling window and label it as such.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 1.1 | Write the **`BarStore` protocol** — `bars()`, `symbol_master(as_of)`, `corporate_actions()`. No provider detail leaks past this interface | Protocol importable; providers plug in |
| 1.2 | Write the `nse-data` MCP server (`backend/mcp/nse_data/`) — `get_historical_bars`, `get_live_quote`, `get_index_constituents`, `get_corporate_actions` | MCP server starts; tools list correctly |
| 1.3 | Implement provider adapters — yfinance, Dhan, broker-historical. Each behind `BarStore` | Each adapter passes a shared contract test |
| 1.4 | Implement a broker WebSocket quote client — ⚠️ **not** nseindia.com, that API 403s plain HTTP clients | Live quote received |
| 1.5 | `backend/data/symbols.py` — **point-in-time** membership from bhavcopy presence + index-change events; **archive every list snapshot on first fetch** | Delisted symbols included; snapshots dated |
| 1.6 | `backend/data/downloader.py` — batch download, retry, rate-limit backoff, resume, idempotent re-run | Re-run adds no duplicates |
| 1.7 | `backend/data/store.py` — Parquet writer, partitioned `symbol=/date=` | Files land on disk |
| 1.8 | `backend/data/loader.py` — **DuckDB 2.0.0** query helper over Parquet | Query returns expected bar count |
| 1.9 | `backend/data/panel.py` — **Polars 2.0.0** wide panel (one column per symbol) with rolling expressions | Panel builds; rolling corr matches pandas |
| 1.10 | `backend/data/adjust.py` — split/dividend adjustment applied **before** screening | Known corporate action adjusts correctly |
| 1.11 | `backend/data/circuits.py` — NSE price-band / circuit data | Band lookup works for a known symbol |
| 1.12 | Download the target dataset | Row counts match expected (≈ 250 sessions × 38 bars/symbol) |
| 1.13 | `tests/unit/test_data_loader.py`, `test_barstore_contract.py` | Tests pass |

### Files created
```
backend/data/barstore.py          ← the protocol
backend/data/providers/yfinance.py
backend/data/providers/dhan.py
backend/data/providers/broker_historical.py
backend/data/symbols.py
backend/data/downloader.py
backend/data/store.py
backend/data/loader.py
backend/data/panel.py
backend/data/adjust.py
backend/data/circuits.py
backend/mcp/nse_data/server.py
backend/mcp/nse_data/nse_client.py
backend/mcp/nse_data/tools.py
tests/unit/test_data_loader.py
tests/unit/test_barstore_contract.py
```

**Exit gate:** target window stored and queryable; a spot-check symbol reconciles against the source; coverage ≥ 95% per symbol; point-in-time universe includes delisted names.

---

## Phase 2 — Strategy Engine + Backtest ⭐

**Goal:** Cointegration screen, live z-score engine, signal generator, risk engine, cost model, and a walk-forward backtest that reports honest post-cost results.

> This phase decides whether the project is viable. Everything after it is plumbing.
> **Build the cost model first** — it gates which pairs are even tradable.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 2.1 | **`backend/engine/costs.py` FIRST** — full per-leg NSE model (brokerage, STT 0.08% sell-side, exchange, SEBI, IPST, GST 18% on the correct base, stamp duty buy-side, slippage) + the worse-side second-leg fill assumption | Per-leg and 4-fill pair round trip match a hand calculation |
| 2.2 | `backend/engine/cointegration.py` — OLS hedge ratio, Engle-Granger ADF, half-life calc (`statsmodels` 0.15.0) | Synthetic cointegrated series pass; random walks rejected |
| 2.3 | `backend/engine/screening.py` — weekly screen, all guards (both-orderings ADF, half-life ≤ 30 bars, spread-vol floor, circuit exclusion, **edge-to-cost ≥ 3×**) | Produces ranked pair list |
| 2.4 | `backend/engine/screening_fast.py` — vectorised pre-filter + Numba 0.68.0 rolling kernels; `statsmodels.coint` only on survivors | Full universe screens in minutes, not hours |
| 2.5 | `backend/engine/zscore.py` — frozen μ/σ, live z-score | Known deviation matches hand calculation |
| 2.6 | `backend/engine/signals.py` — entry/exit rules per `STRATEGY.md` §5 | Table-driven tests for every branch |
| 2.7 | `backend/engine/risk.py` — all limits, circuit breakers, position sizing | Every limit has a test that trips it |
| 2.8 | `backend/backtest/engine.py` — event-driven bar-by-bar loop, next-bar-open fills, forced square-offs | No lookahead: fill price ≠ signal bar close |
| 2.9 | `backend/backtest/walkforward.py` — screen on week $T$, trade week $T+1$, roll forward | No overlap between screen and trade windows |
| 2.10 | `backend/backtest/metrics.py` — Sharpe, **deflated Sharpe**, max DD, profit factor, win rate, turnover, **PBO** | Matches manual calc on a synthetic equity curve |
| 2.11 | `backend/backtest/report.py` — Markdown + JSON report, Sharpe with vs. without costs | Report file generated |
| 2.12 | `tests/unit/test_cointegration.py`, `test_zscore.py`, `test_signals.py`, `test_risk.py`, `test_costs.py` | All pass |
| 2.13 | `tests/unit/test_backtest_no_lookahead.py` — asserts fills never use the signal bar's close | Passes |
| 2.14 | `tests/unit/test_bias_survivorship.py` — asserts the universe includes delisted symbols | Passes |
| 2.15 | Run the full walk-forward backtest | `docs/reports/backtest-<date>.md` generated |

### Files created
```
backend/engine/costs.py
backend/engine/cointegration.py
backend/engine/screening.py
backend/engine/screening_fast.py
backend/engine/zscore.py
backend/engine/signals.py
backend/engine/risk.py
backend/backtest/engine.py
backend/backtest/walkforward.py
backend/backtest/metrics.py
backend/backtest/report.py
tests/unit/test_cointegration.py
tests/unit/test_zscore.py
tests/unit/test_signals.py
tests/unit/test_risk.py
tests/unit/test_costs.py
tests/unit/test_backtest_no_lookahead.py
tests/unit/test_bias_survivorship.py
```

**Exit gate:** ✅ Sharpe > 1.5 **after** costs, max DD < 20%, Sharpe-with-costs within 30% of Sharpe-without, no bias-check failures.
❌ **If not met → stop.** Report the actual numbers and revisit the premise (consider 15/30-minute bars, or daily bars with explicit approval). Do not proceed to Phase 3 with a failing edge.

---

## Phase 3 — Backend API + Authentication

**Goal:** FastAPI service with JWT auth, RBAC, full persistence, and both REST and WebSocket surfaces.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 3.1 | Write the DB schema — `users`, `pairs`, `signals`, `positions`, `trades`, `risk_limits`, `audit_log` | Alembic migration applies cleanly |
| 3.2 | `backend/db/models.py` — SQLAlchemy 2.1.6 async models (`DeclarativeBase` + `Mapped[]`) | — |
| 3.3 | `backend/db/session.py` — async engine + session dependency | — |
| 3.4 | Set up Alembic 1.20.1; generate and apply the initial migration | `alembic upgrade head` succeeds on a fresh DB |
| 3.5 | `backend/auth/password.py` — **Argon2id** via `argon2-cffi` 25.1.0 — ⚠️ not bcrypt (72-byte truncation), not passlib (2020) | Hash/verify round-trip |
| 3.6 | `backend/auth/jwt.py` — access token (15 min TTL) + refresh token with rotation, PyJWT 2.15.1 | Claims correct; tampered token rejected |
| 3.7 | `backend/auth/deps.py` — `get_current_user`, `require_role("admin")` | — |
| 3.8 | `backend/api/auth.py` — `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me` | Full flow via HTTP |
| 3.9 | `backend/api/pairs.py` — list/enable/disable cointegrated pairs | Role-gated |
| 3.10 | `backend/api/signals.py` — signals list, filtered by pair/time | — |
| 3.11 | `backend/api/positions.py` — open positions, closed trades, P&L | — |
| 3.12 | `backend/api/admin.py` — user CRUD, risk-limit config, system health | Admin-only |
| 3.13 | `backend/api/ws.py` — WebSocket broadcasting live z-scores and positions | Client receives a tick |
| 3.14 | `backend/services/scheduler.py` — **APScheduler 3.11.3** (⚠️ not 4.x): 5-min bar ingest, signal evaluation, risk checks, 15:20 square-off | Registers the right cron jobs |
| 3.15 | `backend/services/cache.py` — `redis.asyncio` price cache + signal pub/sub | Cache hit/miss works |
| 3.16 | `backend/services/notifier.py` — admin alerts (email + optional webhook) for limit breaches | Test sends a real alert |
| 3.17 | `tests/integration/test_auth.py` — register → login → refresh → protected route → role denial | All pass |
| 3.18 | `tests/integration/test_api.py` | All pass |

### Files created
```
backend/db/models.py
backend/db/session.py
backend/db/base.py
backend/auth/password.py
backend/auth/jwt.py
backend/auth/deps.py
backend/api/auth.py
backend/api/pairs.py
backend/api/signals.py
backend/api/positions.py
backend/api/admin.py
backend/api/ws.py
backend/api/router.py
backend/services/scheduler.py
backend/services/cache.py
backend/services/notifier.py
alembic.ini
alembic/versions/0001_initial.py
tests/integration/test_auth.py
tests/integration/test_api.py
```

**Exit gate:** every endpoint rejects unauthenticated requests; role denials verified; WebSocket pushes live data; migrations apply from scratch.

---

## Phase 4 — Frontend Dashboard

**Goal:** React SPA — login, live dashboard, pair management, P&L, admin panel.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 4.1 | Scaffold Vite 8 + React 19 + TS 7 + Tailwind v4 (**CSS-first**); dev proxy to `localhost:8000` | Page loads |
| 4.2 | `src/lib/api.ts` — typed API client, auth header, refresh-on-401 interceptor | — |
| 4.3 | `src/lib/auth.tsx` — auth context + `useAuth` hook | — |
| 4.4 | `src/lib/ws.ts` + `src/store/live.ts` — **Zustand** store fed by the WebSocket; TanStack Query only for REST snapshots | Ticks land in the store |
| 4.5 | `src/pages/Login.tsx` — login form, error states | Login succeeds; bad password shows an error |
| 4.6 | `src/pages/Dashboard.tsx` — live z-score board, pair table | Renders live values |
| 4.7 | `src/components/PairTable.tsx` — sortable pair list with enable/disable | Toggle persists |
| 4.8 | `src/components/SpreadChart.tsx` — `lightweight-charts` price + spread + z-score (**use the `dataviz` skill first**) | Chart renders and live-updates |
| 4.9 | `src/components/SignalFeed.tsx` — live signal stream | Updates without refresh |
| 4.10 | `src/components/PositionPanel.tsx` — open positions + unrealised P&L | — |
| 4.11 | `src/pages/PnL.tsx` — equity curve (Recharts), daily P&L, drawdown | — |
| 4.12 | `src/pages/Admin.tsx` — user management, risk limits | Admin-only; viewer sees a 403 |
| 4.13 | Responsive layout — 1440p, 1080p, tablet | Checked in browser |
| 4.14 | Accessibility pass — chart colour contrast (red/green gain-loss is a known WCAG failure) | Contrast check passes |
| 4.15 | `src/lib/api.test.ts` with Vitest | Tests pass |

### Files created
```
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/index.css
frontend/src/lib/api.ts
frontend/src/lib/auth.tsx
frontend/src/lib/ws.ts
frontend/src/store/live.ts
frontend/src/pages/Login.tsx
frontend/src/pages/Dashboard.tsx
frontend/src/pages/PnL.tsx
frontend/src/pages/Admin.tsx
frontend/src/components/PairTable.tsx
frontend/src/components/SpreadChart.tsx
frontend/src/components/SignalFeed.tsx
frontend/src/components/PositionPanel.tsx
```

**Exit gate:** login → dashboard → live z-score update → pair toggle → logout works end-to-end; no console errors; responsive and accessible.

---

## Phase 5 — Paper Trading

**Goal:** A full simulated trading day with no manual intervention.

> Build our own paper adapter rather than relying on a broker sandbox — only Angel One's UAT URL was found in SDK sources, and no broker sandbox was verified to model intraday frictions realistically.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 5.1 | Write the `paper-broker` MCP server — order placement, fill simulation, positions, funds | Server starts |
| 5.2 | `backend/services/broker.py` — the `Broker` protocol + `PaperBroker` adapter | Interface matches the live-broker contract |
| 5.3 | Realistic fills — slippage, partial fills, rejection on insufficient funds, **worse-side second leg** | Rejection path works; second-leg assumption holds |
| 5.4 | Full order lifecycle — entry, stop-loss, take-profit, max-hold, 15:20 square-off | Every exit path fires in a simulated day |
| 5.5 | Wire the scheduler to the paper broker | Signal → order → position → P&L recorded |
| 5.6 | Run a full simulated session | Position count, P&L, and square-off all correct |
| 5.7 | `tests/integration/test_paper_trading.py` | Passes |

### Files created
```
backend/mcp/paper_broker/server.py
backend/mcp/paper_broker/engine.py
backend/services/broker.py
backend/services/paper_broker.py
tests/integration/test_paper_trading.py
```

**Exit gate:** one complete session, unattended, correct square-off at 15:20, risk limits never breached silently.

---

## Phase 6 — Deployment

**Goal:** Running on a Linux VPS behind HTTPS, with CI/CD.

### Tasks

| # | Task | Verify |
|---|------|--------|
| 6.1 | `backend/Dockerfile` — multi-stage, `python:3.13-slim`, non-root user | Image < 200MB |
| 6.2 | `frontend/Dockerfile` — build → static serve via Caddy | — |
| 6.3 | `docker-compose.prod.yml` — backend, frontend, Postgres, Redis, Caddy | `docker compose -f docker-compose.prod.yml up -d` |
| 6.4 | `Caddyfile` — automatic TLS via Let's Encrypt, reverse proxy `/api` → backend | HTTPS works, cert auto-renews |
| 6.5 | **Run the strategy engine as a separate long-lived process from the web API** — different availability and failure semantics | Two services, independent restart |
| 6.6 | Wire the frontend build to the API base URL (no hardcoded localhost) | — |
| 6.7 | Secrets management — no secrets in images or repo; server env files only | `grep` the repo for secrets → clean |
| 6.8 | **Static egress IP** on the VPS — required for broker IP allow-listing | Documented and reserved |
| 6.9 | Postgres backups (nightly `pg_dump` + rotation) | Restore tested |
| 6.10 | Health checks + monitoring (`/health` polled; separate watchdog for the 15:20 square-off) | Alert on failure |
| 6.11 | `.github/workflows/ci.yml` — lint, type-check, test, build | Runs green |
| 6.12 | `.github/workflows/deploy.yml` — build images, push, SSH deploy, health-check gate | Deploys on merge to main |
| 6.13 | Write `README.md` — setup, deployment, operations runbook | — |
| 6.14 | Deploy to the VPS and verify from outside | Login works over HTTPS |

### Files created
```
backend/Dockerfile
frontend/Dockerfile
docker-compose.prod.yml
Caddyfile
.github/workflows/ci.yml
.github/workflows/deploy.yml
README.md
scripts/backup.sh
scripts/deploy.sh
```

**Exit gate:** deployed at a real URL; HTTPS valid; login works from outside the server; CI green; a rollback has been tested.

---

## Phase 7 — Live Broker Integration (Optional, Separate Approval)

> **Not started until Phases 0–6 are done, the paper track record requirement is met, and the user explicitly approves live-money work.**

### Tasks

| # | Task | Verify |
|---|------|--------|
| 7.1 | Choose and integrate a broker SDK — **Angel One** (refresh-token auth, `estimateCharges`) or **Dhan** (simplest auth, IP allow-list). Needs a brokerage account | Connection works |
| 7.2 | `backend/services/live_broker.py` — implements the same `Broker` protocol | Interface parity with `PaperBroker` |
| 7.3 | Order reconciliation — compare broker state to internal state, alert on drift | Drift detected in a test |
| 7.4 | Basket/leg-fill reconciliation — ⚠️ Zerodha's `place_autoslice_order` is **not atomic**; handle a half-filled pair | Half-fill unwinds correctly |
| 7.5 | Sandbox end-to-end run | Orders fill in sandbox |
| 7.6 | Risk controls re-verified against the live path | Limits enforced |
| 7.7 | **≥ 100 live-paper round trips over ≥ 3 months** before go-live | Track record exists |
| 7.8 | **Explicit user go-live sign-off** | Recorded |

**Exit gate:** live broker sandbox validated; paper track record met; user has approved going live.

---

## Cross-Cutting Concerns

| Concern | Where handled |
|---------|---------------|
| **Strategy honesty** | The cost model gates which pairs are tradable. Backtest reports Sharpe with and without costs, deflated Sharpe, and PBO. A raw Sharpe > 3 on 5-minute data is treated as a bug until proven otherwise. |
| **Security** | Argon2id hashing, 15-min access TTL + refresh rotation, role gating on every route, secrets out of the repo. Reviewed with `ecc:security-review` before the Phase 3 exit. |
| **Testing** | `pytest` + `httpx` for backend, Vitest for frontend. The engine tests (Phase 2) matter most — pure functions, cheap to test, highest defect density. |
| **Observability** | Structured logs from Phase 3; metrics endpoint; admin alerts on risk breaches. A **separate watchdog process** for the 15:20 square-off — it is the one failure that loses money. |
| **Documentation** | `README.md` (Phase 6), `docs/` updated as architecture changes, backtest reports archived per run. |

---

## Skills To Invoke Per Phase

| Phase | Skills |
|-------|--------|
| 0 | `superpowers:writing-plans`, `superpowers:executing-plans` |
| 1 | `ecc:fastapi-patterns`, `ecc:postgres-patterns`, `ecc:code-architect` |
| 2 | `superpowers:test-driven-development`, `mattpocock-skills:domain-modeling` |
| 3 | `ecc:api-design`, `ecc:security-review`, `ecc:redis-patterns` |
| 4 | `dataviz` (before chart code), `ecc:react-patterns`, `ecc:vite-patterns`, `ecc:frontend-design`, `ecc:accessibility` |
| 5 | `superpowers:systematic-debugging` (if fills misbehave) |
| 6 | `ecc:docker-patterns`, `ecc:github-ops` |
| 7 | `ecc:security-review` (again, pre-live) |

---

## Critical Path

```
Phase 0 ──► Phase 1 ──► Phase 2 ══[HARD GATE: positive edge after costs]══► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7
                (data)      (engine+backtest)                              (API+auth)   (UI)     (paper)      (deploy)   (live)
```

Phases 3–6 are roughly parallelisable once Phase 2 passes. Phase 1 and Phase 2 are strictly sequential — you cannot backtest without data, and you cannot trust the backtest without the engine.

**A data-purchase decision sits on the critical path before Phase 1.**

---

## Open Decisions Carried Forward

Settled by the research pass are marked ✅. The rest remain open, each flagged with the phase where it must be answered.

| # | Decision | Status | Needed by | Default if unanswered |
|---|----------|--------|-----------|-----------------------|
| 1 | Universe size | ✅ Settled | — | Nifty 200, point-in-time |
| 2 | **Historical 5-min data source** | ⬜ **OPEN — purchase decision** | Before Phase 1 | Scope to 60 days on yfinance, and label the backtest claim accordingly |
| 3 | Live quote source | ✅ Settled | — | Broker WebSocket feed (not nseindia.com) |
| 4 | WebSocket push vs polling | ✅ Settled | — | WebSocket push |
| 5 | Backtest framework | ✅ Settled | — | Custom event-driven loop |
| 6 | Admin alert channel | ⬜ OPEN | Phase 3 | Email via SMTP + optional webhook |
| 7 | DB schema tables and fields | ✅ Settled | — | Enumerated in Phase 3 task 3.1 |
| 8 | Backtest window | ⬜ OPEN | Phase 2 | Rolling 12 months to the backtest start date |
| 9 | Per-user vs shared books | ⬜ OPEN | Phase 3 | Per-user books; 15-min access TTL + refresh rotation |
| 10 | VPS provider and TLS | ⬜ OPEN | Phase 6 | Ubuntu 22.04 host with a static egress IP + Caddy auto-TLS |
| 11 | **Bar interval: 5-min vs 15/30-min vs daily** | ⬜ **OPEN — material** | Before Phase 2 | 5-min as specified; the alternatives are better-founded and need explicit approval |
| 12 | Live broker target | ⬜ OPEN | Phase 7 | Angel One or Dhan |

---

*Master plan v2, 2026-10-22. Implementation begins only after design approval.*
