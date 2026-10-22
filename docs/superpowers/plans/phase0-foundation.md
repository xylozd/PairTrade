# Phase 0 — Foundation (Backend)

**Plan file:** `docs/superpowers/plans/phase0-foundation.md`
**Spec:** `docs/STRATEGY.md` (strategy + version pins) — binding authority
**Supporting:** `docs/project.md` (design), `docs/MASTER-PLAN.md` (phase plan)
**Scope:** Backend only. Frontend (master-plan task 0.9) and Docker Desktop install (0.11) are excluded — see "Out of Scope".

---

## Global Constraints

- **Python 3.13.3** in `.venv` at repo root. Every command runs with that interpreter.
- **Backend import root is `backend/`.** `backend/` is NOT a package (no `backend/__init__.py`). Run from `backend/` (`uvicorn app:app`), import as `from config import settings`, `from schemas import ...`. This matches master-plan verification commands (`from config import settings; print(settings)`).
- **Version pins are fixed** to `docs/STRATEGY.md` §10. All were re-verified against PyPI on 2026-10-22 and every one has a cp313-compatible Windows wheel. Do not float them.
- **`backend/app.py` must not import `backend/db`, `backend/auth`, or `backend/api`** — those are Phase 3. Phase 0's app imports only `config` and `schemas`.
- **Test layout:** `tests/unit/` (Phase 0 scope) and `tests/integration/` (later phases). `pytest.ini` at repo root sets `pythonpath = backend` and `asyncio_mode = auto`.
- **No secrets in the repo.** `.env.example` holds placeholders only.
- **Every commit** ends with the `Co-Authored-By: Claude Code <noreply@anthropic.com>` trailer.

---

## Task 1: Backend dependencies

**Produces:** `backend/requirements.txt`, installed venv, `tests/unit/test_requirements.py`, `pytest.ini`.

`requirements.txt` pins the full backend set from `STRATEGY.md` §10 (web + auth + DB + quant + data). It is installed into the existing `.venv`.

`pytest.ini` at repo root:

```ini
[pytest]
testpaths = tests
pythonpath = backend
asyncio_mode = auto
```

**TDD note:** `requirements.txt` and `pytest.ini` are configuration files (plan-granted TDD exception). The *drift* between `requirements.txt` and the installed venv is a real failure mode, so it gets a test: `tests/unit/test_requirements.py` parses `requirements.txt` and asserts each pinned package's installed version equals the pin.

### Steps

1. **RED** — write `tests/unit/test_requirements.py`: parse `backend/requirements.txt`, skip comments/blank lines, and for each `name==version` assert `importlib.metadata.version(name) == version`. Also assert the file pins every package named in `STRATEGY.md` §10 (web stack, auth, DB, quant, data). Assert `pytest.ini` exists, sets `pythonpath = backend`, and `testpaths = tests`.
2. Run `python -m pytest tests/unit/test_requirements.py -q` → expect FAIL: `backend/requirements.txt` does not exist.
3. **GREEN** — write `backend/requirements.txt` with exact pins:
   - Web/API: `fastapi==0.159.1`, `uvicorn[standard]==0.54.0`, `orjson==3.13.0`, `websockets==17.3`, `httpx==0.28.1`, `python-multipart==0.0.20`
   - Config/models: `pydantic==2.14.1`, `pydantic-settings==2.16.1`, `python-dotenv==1.2.4`
   - DB: `sqlalchemy==2.1.6`, `alembic==1.20.1`, `asyncpg==0.32.0`
   - Cache/scheduling: `redis==8.1.0`, `apscheduler==3.11.3`
   - Auth: `pyjwt==2.15.1`, `argon2-cffi==25.1.0`
   - Quant: `numpy==2.5.4`, `pandas==3.0.6`, `scipy==1.18.1`, `statsmodels==0.15.0`, `arch==8.0.0`, `numba==0.68.0`
   - Data: `polars==2.0.0`, `duckdb==2.0.0`, `pyarrow==26.0.0`, `yfinance==1.7.0`
   - Test: `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pyyaml==6.0.3`
4. Install: `python -m pip install -r backend/requirements.txt`
5. Write `pytest.ini` as above.
6. Run `python -m pytest tests/unit/test_requirements.py -q` → expect PASS.
7. Commit.

**Expected:** test run reports all tests passed.

---

## Task 2: Configuration

**Produces:** `backend/config.py`, `tests/unit/test_config.py`.

`backend/config.py` exposes a single `settings` instance of a pydantic-settings `BaseSettings` subclass. Env prefix `PAIRTRADE_`. It carries the strategy constants from `STRATEGY.md` §2, §4, §5 — risk limits, z-score thresholds, session times, universe/screening parameters, and the **dated, versioned transaction-cost model** (STRATEGY.md §5.3 demands the cost model be "a first-class, dated, versioned parameter — not a blended bps fudge").

### Steps

1. **RED** — write `tests/unit/test_config.py` asserting:
   - Defaults match `STRATEGY.md` exactly: entry z `2.0`, exit z `0.5`, stop z `3.5`, max hold `45` bars, min hold `3` bars, lookback `60` sessions, max half-life `30` bars, ADF p-value `0.05`, edge-to-cost ratio `3.0`.
   - Risk limits: max notional per pair `100000`, max gross exposure `500000`, max daily loss `50000`, max loss per trade `7500`, max concurrent pairs `10`, max trades/day `50`, max drawdown `0.20`.
   - Session times are `Asia/Kolkata`: market open `09:15`, entry cutoff `14:45`, auto square-off `15:20`, market close `15:30`.
   - Cost model is **dated and versioned**: carries an `as_of` date and a `version` string, and its rates match §5.3 (brokerage `20`/order, STT `0.08%` sell-side, exchange `0.00297%`, SEBI `0.0001%`, IPST `0.00003%`, GST `18%`, stamp duty `0.003%` buy-side intraday, tick size `0.05`).
   - Secret: `jwt_secret_key` has no usable default — it is required or must be explicitly marked dev-only. Env overrides work: setting `PAIRTRADE_MAX_DAILY_LOSS` changes the value.
   - Config is a singleton — `settings` is the same object on re-import.
2. Run `python -m pytest tests/unit/test_config.py -q` → expect FAIL: `ModuleNotFoundError: No module named 'config'`.
3. **GREEN** — write `backend/config.py`.
4. Run `python -m pytest tests/unit/test_config.py -q` → expect PASS.
5. Run `python -c "from config import settings; print(settings)"` from `backend/` → expect no exception.
6. Commit.

**Expected:** test run reports all tests passed; the `settings` print succeeds.

---

## Task 3: Schemas

**Produces:** `backend/schemas.py`, `tests/unit/test_schemas.py`.

Pydantic v2 models shared by the API and (later) the engine. Phase 0 needs: `HealthResponse`, `Symbol`, `Pair`, `PairLeg`, `Signal`, `SignalType`, `Side`, `Position`, `Trade`, `ZScorePoint`, `ErrorResponse`.

### Steps

1. **RED** — write `tests/unit/test_schemas.py` asserting:
   - `HealthResponse(status="ok")` validates; `version` is required.
   - `Side` is an enum with exactly `BUY` and `SELL`.
   - `SignalType` covers `ENTRY_LONG_SPREAD`, `ENTRY_SHORT_SPREAD`, `EXIT`, `STOP_LOSS`.
   - `Pair` requires two **distinct** symbols and a positive hedge ratio; `Pair(symbol_a="A", symbol_b="A", ...)` is rejected.
   - `Symbol` rejects empty/whitespace-only strings and normalises to uppercase.
   - `ZScorePoint` rejects NaN/inf and carries `z_score`, `spread`, `timestamp`.
   - `Signal` requires a `timestamp` and rejects a signal whose `price` is negative.
   - Unknown fields are **rejected** (`model_config = ConfigDict(extra="forbid")`) — a typo in an API payload should fail loudly, not silently drop.
2. Run `python -m pytest tests/unit/test_schemas.py -q` → expect FAIL: `ModuleNotFoundError: No module named 'schemas'`.
3. **GREEN** — write `backend/schemas.py`.
4. Run `python -m pytest tests/unit/test_schemas.py -q` → expect PASS.
5. Commit.

**Expected:** test run reports all tests passed.

---

## Task 4: FastAPI application

**Produces:** `backend/app.py`, `tests/unit/test_app.py`.

FastAPI skeleton with `/health` and CORS. The health payload matches `HealthResponse` from Task 3.

### Steps

1. **RED** — write `tests/unit/test_app.py` asserting, via `fastapi.testclient.TestClient`:
   - `GET /health` → `200`, JSON `{"status": "ok"}`, and a `version` field.
   - `GET /health` returns `Cache-Control: no-store` — a stale cached health response would mask a dead service.
   - CORS: a request with `Origin: http://localhost:5173` returns `access-control-allow-origin: http://localhost:5173`; a disallowed origin does not.
   - `GET /openapi.json` → `200` and the app's routes are present.
   - `POST /health` → `405` (method not allowed).
2. Run `python -m pytest tests/unit/test_app.py -q` → expect FAIL: `ModuleNotFoundError: No module named 'app'`.
3. **GREEN** — write `backend/app.py`: FastAPI instance, CORS middleware configured from `settings.cors_origins`, `/health` route returning `HealthResponse`, and a `GET /` root route describing the service.
4. Run `python -m pytest tests/unit/test_app.py -q` → expect PASS.
5. Run `python -m pytest -q` → whole suite PASS.
6. Boot the server for real: `uvicorn app:app --port 8000` from `backend/`, `curl localhost:8000/health` → `{"status":"ok",...}`. Kill it after.
7. Commit.

**Expected:** test run reports all tests passed; live `curl` returns `status: ok`.

---

## Task 5: Local services + environment template

**Produces:** `docker-compose.yml`, `.env.example`, `tests/unit/test_infra_files.py`.

### Steps

1. **RED** — write `tests/unit/test_infra_files.py` asserting:
   - `docker-compose.yml` parses as YAML and defines `postgres` and `redis` services.
   - Postgres service image is `postgres:15-alpine`; Redis is `redis:7-alpine`; both declare a `healthcheck`.
   - Postgres service sets `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` from env with safe defaults and persists to a named volume.
   - No hardcoded real credentials appear in the compose file (values come from env with `${VAR:-default}` form).
   - `.env.example` exists, contains no real secret (the JWT secret value is a placeholder like `change-me`), and lists the variables the app reads.
2. Run `python -m pytest tests/unit/test_infra_files.py -q` → expect FAIL: files do not exist.
3. **GREEN** — write `docker-compose.yml` and `.env.example`.
4. Run `python -m pytest tests/unit/test_infra_files.py -q` → expect PASS.
5. **Blocked verification:** `docker compose up -d` cannot run — Docker is not installed on this machine (master-plan task 0.11). Record this in the ledger as a blocked item; the compose file is verified by test only.
6. Commit.

**Expected:** test run reports all tests passed.

---

## Out of Scope

- **Frontend** (master-plan 0.9): a separate plan after backend is green.
- **Docker Desktop install** (master-plan 0.11): requires the human partner's machine action. `docker compose up -d` stays unverified until then.
- **Alpine note:** the compose file targets Linux hosts (VPS). On this Windows machine, Docker Desktop's Linux containers satisfy the same compose file.

---

## Final Verification

1. `python -m pytest -q` from repo root → all tests pass, no warnings.
2. `python -c "from config import settings; print(settings)"` from `backend/` → succeeds.
3. `uvicorn app:app` boots and `curl localhost:8000/health` → `{"status":"ok"}`.
4. `git status` clean; every task committed.
