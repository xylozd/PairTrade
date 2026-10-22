"""Application configuration.

Every strategy constant the engine, the API and the backtester depend on lives
here, sourced from `docs/STRATEGY.md`. Two rules govern this module:

1. **The numbers are the spec.** Thresholds, risk limits and session times are
   copied from STRATEGY.md and pinned by `tests/unit/test_config.py`. Change a
   number here and the test fails — that is deliberate. Changing the strategy
   means changing the spec first.

2. **The cost model is dated and versioned.** STRATEGY.md §5.3 is explicit that
   costs must be "a first-class, dated, versioned parameter — not a blended bps
   fudge". Brokerage rates change; a backtest result is only reproducible if you
   can say which rate card produced it.

Environment overrides use the `PAIRTRADE_` prefix, e.g.
`PAIRTRADE_MAX_DAILY_LOSS=25000`.
"""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Transaction costs — STRATEGY.md §5.3
# ---------------------------------------------------------------------------


class CostModel(BaseModel):
    """Per-fill NSE equity transaction costs.

    Rates are fractions of traded notional (0.0008 == 0.08%). Verify against
    your broker's current rate card before trusting a backtest — these change.
    """

    model_config = {"extra": "forbid"}

    brokerage_per_order: float = 20.0
    # STT 0.08% on equity delivery/intraday-equity — sell side only.
    stt_rate: float = 0.0008
    stt_side: Literal["buy", "sell"] = "sell"
    # NSE exchange transaction charge — both sides.
    exchange_transaction_rate: float = 0.0000297
    # SEBI turnover: Rs 10 per crore — both sides.
    sebi_turnover_rate: float = 0.000001
    # IPST: Rs 3 per crore — both sides.
    ipst_rate: float = 0.0000003
    # GST 18% on (brokerage + exchange + SEBI + IPST). Not on STT or stamp duty.
    gst_rate: float = 0.18
    # Stamp duty ~0.003% intraday — buy side only.
    stamp_duty_rate: float = 0.00003
    stamp_duty_side: Literal["buy", "sell"] = "buy"
    # Minimum tick size for most scrips (Rs 0.01 for some sub-Rs 250 names).
    tick_size: float = 0.05


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Runtime configuration, resolved from the environment with defaults."""

    model_config = SettingsConfigDict(
        env_prefix="PAIRTRADE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service ---------------------------------------------------------
    app_name: str = "NSE Intraday Pair Trading"
    environment: Literal["dev", "test", "prod"] = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- Infrastructure --------------------------------------------------
    database_url: str = "postgresql+asyncpg://pairtrade:pairtrade@localhost:5432/pairtrade"
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ------------------------------------------------------------
    # Dev-only fallback. In `prod` the app refuses to start on this value.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    # --- Market session (IST) — STRATEGY.md §2, §5.1 ----------------------
    timezone: str = "Asia/Kolkata"
    market_open: time = time(9, 15)
    entry_cutoff: time = time(14, 45)
    auto_square_off: time = time(15, 20)
    market_close: time = time(15, 30)
    bar_interval: str = "5m"

    # --- Signal thresholds — STRATEGY.md §5.1 -----------------------------
    zscore_entry_threshold: float = 2.0
    zscore_exit_threshold: float = 0.5
    zscore_stop_loss_threshold: float = 3.5
    max_hold_bars: int = 45
    min_hold_bars: int = 3

    # --- Screening — STRATEGY.md §2, §4 -----------------------------------
    screening_lookback_sessions: int = 60
    max_half_life_bars: int = 30
    adf_pvalue_threshold: float = 0.05
    # Hard gate, not a nicety: a pair whose expected gross edge is under 3x
    # its round-trip cost is not tradable.
    min_edge_to_cost_ratio: float = 3.0
    min_median_bar_value: float = 5_000_000  # Rs 50 lakh, 30-day median
    min_bar_coverage: float = 0.95
    spread_vol_percentile_floor: float = 10.0

    # --- Risk limits — STRATEGY.md §5.4 -----------------------------------
    max_notional_per_pair: float = 100_000
    max_total_gross_exposure: float = 500_000
    max_daily_loss: float = 50_000
    max_loss_per_trade: float = 7_500
    max_trades_per_day: int = 50
    max_drawdown: float = 0.20
    max_concurrent_pairs: int = 10
    max_consecutive_losses_per_pair: int = 3
    stale_feed_seconds: int = 90

    # --- Cost model — STRATEGY.md §5.3 -----------------------------------
    costs: CostModel = Field(default_factory=CostModel)
    cost_model_version: str = "nse-equity-2026-10-22"
    cost_model_as_of: date = date(2026, 10, 22)

    # --- Backtest --------------------------------------------------------
    backtest_start: date = date(2025, 10, 22)
    backtest_end: date = date(2026, 10, 22)
    risk_free_rate: float = 0.065
    target_sharpe: float = 1.5

    @model_validator(mode="after")
    def _check_production_secret(self) -> "Settings":
        if self.environment == "prod" and "dev-only" in self.jwt_secret_key:
            raise ValueError(
                "jwt_secret_key must be set to a real secret when environment=prod"
            )
        return self

    @model_validator(mode="after")
    def _check_threshold_ordering(self) -> "Settings":
        if not (
            self.zscore_exit_threshold
            < self.zscore_entry_threshold
            < self.zscore_stop_loss_threshold
        ):
            raise ValueError(
                "z-score thresholds must satisfy exit < entry < stop-loss"
            )
        if self.min_hold_bars >= self.max_hold_bars:
            raise ValueError("min_hold_bars must be less than max_hold_bars")
        if not (
            self.market_open < self.entry_cutoff < self.auto_square_off < self.market_close
        ):
            raise ValueError("session times must be strictly increasing")
        return self


settings = Settings()
