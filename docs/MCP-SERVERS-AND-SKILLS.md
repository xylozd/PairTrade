# Required MCP Servers & Skills — Environment Audit

**Date:** 2026-10-22
**Scope:** Tooling required to build, verify, and deploy the NSE Intraday Pair Trading project.

---

## 1. Verified Environment Snapshot

Everything below was checked on this machine, not assumed.

| Component | Status | Detail |
|-----------|--------|--------|
| Python | ✅ Present | **3.13.3** at `C:\Users\ITI MANGROL\AppData\Local\Programs\Python\Python313\python` |
| pip | ✅ Present | 25.0.1 (bundled with 3.13.3) |
| venv module | ✅ Present | `python -m venv` works — **.venv already created** in project root |
| `python3` alias | ❌ Missing | Only `python` is on PATH — scripts must use `python`, not `python3` |
| `uv` / `uvx` | ❌ Missing | Not installed. Relevant: the **serena** MCP server requires `uvx` |
| Node.js | ✅ Present | **v22.23.3** |
| npm | ✅ Present | **12.2.0** |
| git | ✅ Present | 2.56.0.windows.2 |
| Docker | ❌ Missing | `docker` and `docker compose` both not on PATH |
| PostgreSQL client | ❌ Missing | `psql` not installed |
| Redis | ❌ Missing | `redis-server` not installed |
| `.mcp.json` in project | ❌ None | Project MCP config is empty — no servers registered |
| Project `mcpServers` | ❌ `{}` | Confirmed in `~/.claude.json` under this project path |

### Directories created
```
Omniroute/PairTrade/
├── .venv/        ← created, Python 3.13.3 (Scripts/ activate + pip.exe present)
├── backend/      ← empty
├── frontend/     ← empty
├── tests/        ← empty
├── alembic/      ← empty (migrations land here in Phase 3)
├── scripts/      ← empty (deploy/backup scripts land here in Phase 6)
├── .github/      ← empty (CI/CD workflows land here in Phase 6)
├── data/         ← empty (gitignored — market data store)
├── node_modules/ ← empty (gitignored — frontend deps)
├── .gitignore    ← created
├── README.md     ← created
└── docs/         ← project.md, STRATEGY.md, MASTER-PLAN.md, MCP-SERVERS-AND-SKILLS.md
```

### Installed Claude Code plugins
| Plugin | Version | Scope |
|--------|---------|-------|
| `superpowers@claude-plugins-official` | 7.0.0 | user |
| `mattpocock-skills@claude-plugins-official` | 1.3.1 | user |
| `ecc@ecc` | 2.2.3 | user |
| `document-skills@anthropic-agent-skills` | dbd4588f9e10 | user |

---

## 2. MCP Servers — Audit

MCP servers exist in two distinct places, and they are **not** interchangeable. This distinction matters for the setup steps.

### 2.1 MCP servers available via the plugin marketplace (not yet enabled)

These ship with the official marketplace and are already downloaded to
`~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/`.
Enabling one is a marketplace-plugin action — it does **not** require writing
`.mcp.json` by hand.

| MCP Server | Transport | Requires | Recommended for this project? |
|------------|-----------|----------|-------------------------------|
| **context7** | HTTP (remote) | none | ✅ **Yes — high value.** Pulls version-accurate docs for FastAPI, SQLAlchemy, Tailwind, TanStack Query. Directly reduces guessing on framework APIs. |
| **playwright** | stdio (`npx @playwright/mcp@latest`) | Node + npx | ✅ **Yes — high value.** Drives the dashboard in a real browser: login flow, chart rendering, WebSocket updates, responsive check. |
| **serena** | stdio (`uvx --from git+...`) | **`uvx` — NOT INSTALLED** | ⚠️ Optional. Semantic code navigation is nice-to-have; blocked until `uv` is installed. Skip for now. |
| **github** | HTTP | `GITHUB_PERSONAL_ACCESS_TOKEN` env var | ✅ **Yes — when the repo goes remote.** Needed for CI/CD (§8 step 8 of project.md). Requires a PAT with repo scope. |
| **firebase** | stdio (`npx firebase-tools mcp`) | Firebase project | ❌ No — project uses PostgreSQL + Redis, not Firebase. |
| **terraform** | stdio (Docker) | Docker **and** a TFE token | ❌ No — project deploys via Docker Compose + SSH, not Terraform. Also blocked: no Docker installed. |
| gitlab / asana / linear / discord / telegram / imessage / fakechat / laravel-boost | various | various accounts | ❌ No — not used by this project. |

### 2.2 The `chrome-devtools` MCP server (ecc plugin — already active)

The `ecc` plugin ships its own `.mcp.json`:
```json
{ "mcpServers": { "chrome-devtools": {
    "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1"] } } }
```
This is **already available** in this session (tools like `mcp__plugin_ecc_chrome-devtools__navigate_page` are listed).
It overlaps with Playwright but adds Lighthouse auditing, performance tracing, and network-request inspection —
genuinely useful for the "web dashboard" acceptance criteria.

### 2.3 MCP servers this project must add itself

Neither of these exist anywhere in the marketplace. They must be written by us
as project-scoped `.mcp.json` entries.

| MCP Server | Why this project needs it | What it would expose |
|------------|---------------------------|---------------------|
| **`nse-data`** | Fetch NSE intraday bars and live quotes. Wraps the provider-specific auth (broker tokens, NSE cookie/crumb handling) behind tool calls instead of scattering it through the codebase. Also the home of the **`BarStore` protocol** so the strategy engine never sees a provider-specific detail. | `get_historical_bars(symbol, interval, from, to)`<br/>`get_live_quote(symbol)`<br/>`get_index_constituents(index, as_of)`<br/>`get_corporate_actions(symbol, from, to)`<br/>`get_price_band(symbol, date)` |
| **`paper-broker`** | Simulate intraday order placement, positions, and P&L so the whole pipeline is testable before any real broker API is connected. Keeps the "no real money at launch" promise enforceable. | `place_order(symbol, side, qty, type)`<br/>`cancel_order(order_id)`<br/>`get_positions()`<br/>`get_funds()`<br/>`square_off_all()` |

**Recommendation:** write these two as project-scoped MCP servers in
`backend/mcp/`. This makes the strategy engine testable in isolation and lets
the *same* trading logic be driven by a live broker later by swapping one server.

### 2.4 Research correction — the NSE public API is not usable

Direct probes on 2026-10-22:

| Endpoint | Result |
|----------|--------|
| `https://www.nseindia.com/` | HTTP 200, sets `nsit`, `_abck`, `bm_sz` (Akamai Bot Manager) |
| `https://www.nseindia.com/api/quote-equity?symbol=RELIANCE` | **HTTP 403 Forbidden** — even with a browser UA, `Referer`, `X-Requested-With`, and warmed cookies |
| `https://www.nseindia.com/api/equity-stockIndices?index=NIFTY 50` | 404 on that path form |
| `https://www.nseindia.com/api/chart-of-equity?symbol=RELIANCE` | 404 on that path form |

**Conclusion:** the NSE public JSON API is not reliably callable programmatically. It is behind Akamai Bot Manager (cookie + TLS-fingerprinting) and is an undocumented scrape target with no published rate limit and no SLA. **Do not build a dependency on it.**

**Revised plan:** live quotes come from a **broker WebSocket feed** instead. Verified SDK support:

| Broker | SDK | WebSocket module | Notes |
|--------|-----|------------------|-------|
| **Angel One** | `smartapi-python` 1.5.5 | `smartWebSocketV2.py`, `smartWebSocketOrderUpdate.py` | Binary protocol, best-5 + depth-20 decoding, subscription by `correlation_id`. **Has a UAT base URL** (`openapisuat.angelbroking.com`) — the only sandbox hint found |
| **Dhan** | `dhanhq` 2.3.0 | `_market_feed.py`, `fulldepth.py` | 20-level depth feed — deepest free-ish Indian L2 source. Simplest auth (client_id + PIN + TOTP). ⚠️ **IP allow-listing is mandatory** |
| **Upstox** | `upstox-python-sdk` 2.30.0 | `websocket_api.py` | Heaviest SDK (402 files, 25 API modules) |
| **Zerodha** | `kiteconnect` 5.2.2 | `connect.py` | Simple REST; daily manual login is an operational burden for an unattended bot |

**No official paper-trading sandbox was verified** for Zerodha, Upstox, Dhan, or Fyers. Angel One's UAT host is the only candidate, and whether it fills intraday equity realistically is unverified. → **Build our own paper broker.** See `STRATEGY.md` §7.

### 2.5 Data provider reality (verified 2026-10-22)

| Provider | 5-min history | Lookback |
|----------|---------------|----------|
| **yfinance 1.7.0** | ✅ yes, `.NS` tickers work | ⚠️ **60 days** — hard-coded in source: `min_lookbacks = {"30m","15m","5m","2m": timedelta(days=60)}` |
| **nselib 2.5.1** | ❌ no | All 40+ endpoints are daily (bhavcopy, corporate actions, block deals) |
| **nsepython 2.101** | ❌ no | Daily-oriented scraper |
| **nsepy 0.8** | ❌ no | **Last release 2020-03-07 — abandoned, do not use** |
| **Dhan 2.3.0** | ✅ explicit 5-min interval | **Last 5 trading days** (`POST /charts/intraday`) |
| **Upstox 2.30.0** | ✅ current day only | `GET /v2/historical-candle/intraday/...` |
| **Zerodha 5.2.2** | ✅ but **paid entitlement** | Minutes data sold per instrument/month |
| **Angel One 1.5.5** | ✅ `getCandleData` | — |
| **IEX Cloud** | — | **Shut down Aug 2024** — do not plan around it |
| **Paid vendors** | ✅ | TrueData, GDF, IEX, NSE paid products, Twelve Data, TradingView |

**Bottom line:** no free source covers a 1-year 5-minute window. A purchase decision is required before Phase 1.

---

## 3. Skills — Audit

### 3.1 Skills to use during the build (from installed plugins)

| Skill | When to invoke | Why |
|-------|----------------|-----|
| `superpowers:writing-plans` | **Right after design approval** | Required next step per the brainstorming skill — produces the phased implementation plan. |
| `superpowers:test-driven-development` | During engine + backend implementation | The cointegration engine and signal logic are the parts most worth testing; they are pure functions and test them first. |
| `superpowers:verification-before-completion` | Before declaring any phase done | Prevents "looks done" claims about the backtest and auth flows. |
| `superpowers:executing-plans` | When the plan is approved | Executes the written plan phase by phase. |
| `superpowers:requesting-code-review` / `superpowers:receiving-code-review` | After each phase | Standard review loop. |
| `mattpocock-skills:tdd` | Alternative TDD workflow | Distinct from superpowers TDD; pick one to avoid conflicting flows. |
| `mattpocock-skills:domain-modeling` | When defining DB schema + entities | The project has several entities (User, Pair, Signal, Position, Trade, RiskLimit) with real relationships — this skill models them. |
| `mattpocock-skills:codebase-design` | Architecture review of the backend | Useful once modules exist. |
| `ecc:fastapi-patterns` | Building the backend | Async patterns, dependency injection, background tasks. |
| `ecc:postgres-patterns` | Schema, indexes, migrations | Covers the signal/position write path. |
| `ecc:redis-patterns` | Price cache + signal pub/sub | Rolling price cache and channel design. |
| `ecc:react-patterns` | Building the frontend | Component structure and data fetching. |
| `ecc:vite-patterns` | Frontend build tooling | Vite config, proxy setup to the backend. |
| `ecc:docker-patterns` | Containerisation | Backend image, nginx/Caddy frontend serve. |
| `ecc:security-review` | **Before the auth layer ships** | JWT handling, password hashing, secret management — the part a reviewer would catch late. |
| `ecc:api-design` | Designing REST endpoints | Keeps the frontend/backend contract clean. |
| `ecc:browser-qa` | Manual UI verification | Confirms the dashboard works end-to-end. |
| `ecc:codebase-onboarding` | First session on the codebase | Orients on what exists. |
| `ecc:update-docs` | As the project evolves | Keeps README/docs current. |
| `dataviz` | **Before writing any chart code** | Required by the dataviz skill trigger — covers the z-score/price charts in the dashboard, including palette and axis rules. |
| `ecc:frontend-design` | Dashboard UI pass | Ensures the UI is not generic. |
| `ecc:accessibility` / `ecc:frontend-a11y` | Dashboard markup | Chart colour contrast matters — a red/green gain-loss chart is a classic WCAG failure. |

### 3.2 Skills deliberately NOT used
- `ecc:gan-build` / `ecc:gan-design` / GAN harness agents — heavyweight, designed for generative UI benchmarks, not this project.
- `ecc:agent-*` orchestration skills — no multi-agent need here.
- `document-skills:*` — no Office document deliverables.
- `ecc:multi-backend` / `ecc:multi-frontend` — single backend, single frontend.

---

## 4. Gaps That Must Be Closed Before Implementation

| Gap | Impact | Action |
|-----|--------|--------|
| **Docker not installed** | Cannot run `docker compose up` for Postgres/Redis locally, cannot build images, cannot test the deployment path. | Install Docker Desktop (Windows) — required before the Phase 0 exit. |
| **No Postgres/Redis locally** | Backend cannot be run or tested end-to-end. | Docker Desktop solves both. |
| **No 1-year 5-min data source** | The primary success criterion (walk-forward Sharpe) is untestable without it. | Purchase an entitlement, or scope to 60 days and label the claim accordingly. **Decide before Phase 1.** |
| **`python3` not on PATH** | Scripts assuming `python3` fail on this machine. | Use `python` in all local commands, or add a shim. |
| **`uvx` not installed** | `serena` MCP server cannot start. | Optional — install `uv` if code-navigation tooling is wanted. |
| **No `.mcp.json` in project** | context7 / playwright / github MCP servers are not wired to this project. | Add a project `.mcp.json` enabling context7 + playwright. |
| **Not a git repository** | No version control, no CI/CD, no safe rollback. | Run `git init` and commit the docs before code starts. |

---

## 5. Recommended Setup Actions (to run when implementation begins)

```bash
# 1. Version control
cd "/e/D H BHARTHI/DEMO PROJECTS/AmazonQ/Omniroute/PairTrade"
git init && git add docs/ && git commit -m "docs: project design for NSE intraday pair trading"

# 2. Project-scoped MCP servers (create .mcp.json)
#    -> enables context7 + playwright for this project only

# 3. Install Docker Desktop (manual, from docker.com)
#    -> unlocks docker compose up (Postgres + Redis) and image builds

# 4. Backend deps into the existing .venv (pinned versions per STRATEGY.md §10)
.venv/Scripts/python -m pip install \
  "fastapi==0.159.1" "pydantic==2.14.1" "pydantic-settings==2.16.1" "uvicorn==0.54.0" \
  "sqlalchemy==2.1.6" "alembic==1.20.1" "asyncpg==0.32.0" "redis==8.1.0" \
  "apscheduler==3.11.3" "pyjwt==2.15.1" "argon2-cffi==25.1.0" \
  "websockets==17.3" "httpx==0.28.1" "orjson==3.13.0" \
  "statsmodels==0.15.0" "arch==8.0.0" "pandas==3.0.6" "numpy==2.5.4" "scipy==1.18.1" \
  "numba==0.68.0" "polars==2.0.0" "duckdb==2.0.0" "pyarrow==26.0.0" \
  "pytest" "pytest-asyncio" "httpx"
```

> ⚠️ `pandas` 3.0, `polars` 2.0, and `duckdb` 2.0 are all **major releases with breaking changes**. Pin exactly and expect to adapt code written against older APIs.

---

## 6. Library Gotchas Found During Research

| Library | Trap | Do instead |
|---------|------|------------|
| `aioredis` | **Dead** — last release Dec 2021 | `redis.asyncio` from redis-py 8.1.0 |
| `apscheduler` 4.x | **Pre-release alpha**; upstream README says "do NOT use this release in production!" | 3.11.3 |
| `bcrypt` | Silently truncates input at 72 bytes — a long passphrase gives *less* entropy than it appears | `argon2-cffi` (Argon2id, OWASP first choice) |
| `passlib` 1.7.4 | Last release Oct 2020; known bcrypt-4.x compatibility friction | Use `argon2-cffi` directly |
| `backtrader` | **Unmaintained** — last release April 2023 | Custom event-driven loop (stateful rules) |
| `backtesting.py` | Maintained, but **single-asset, single-direction** — poor fit for two-leg pairs | Custom loop; `vectorbt` if a vectorised comparison is wanted |
| `statsmodels.coint` | Full Johansen eigen-decomposition per call (~ms) — do NOT put in a hot loop over 20k+ pairs | Vectorised pre-filter, then `coint` on survivors only |
| `arch` | It is **conditional volatility** (GARCH/EGARCH/DCC), **not** a cointegration engine | `statsmodels` for cointegration; `arch` for volatility-normalised bands |
| `TA-Lib` (PyPI) | The name now points to an **unrelated** package | Use `pandas-ta` (beta) or write indicators directly |
| `nsepy` | Abandoned since March 2020 | `nselib` 2.5.1 (daily only) or a broker SDK |
| `tailwindcss` v4 | CSS-first config — `tailwind.config.js` is **no longer auto-loaded** | `@import "tailwindcss"` + `@theme` in CSS |
| `celery` | Does not support Microsoft Windows (this dev box) | APScheduler 3.11.3 |
| `yfinance` | 5-min capped at 60 days | `BarStore` abstraction; don't leak the cap into the schema |

---

*Audit performed 2026-10-22. All environment claims verified by command; all library/version claims verified against PyPI and the npm registry.*
