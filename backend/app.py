"""FastAPI application entry point.

Run locally with:

    cd backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000

Phase 0 scope is deliberately narrow: a health endpoint and CORS. The auth,
database and domain routers arrive in Phase 3 — importing them here would
mean this skeleton could not boot without Postgres and Redis running.
"""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from schemas import HealthResponse

__version__ = "0.1.0"

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Intraday statistical arbitrage (pair trading) on NSE equities. "
        "Paper-trading mode only — no real-money broker integration."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health(response: Response) -> HealthResponse:
    """Liveness probe.

    Sends `Cache-Control: no-store` so an intermediary cannot serve a stale
    200 for a process that has since died.
    """
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(status="ok", version=__version__)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Service description, useful for confirming which build is deployed."""
    return {
        "status": "ok",
        "name": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "docs": "/docs",
    }
