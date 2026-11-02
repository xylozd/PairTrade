"""Configuration defaults and overrides.

`backend/config.py` carries the strategy's numbers — thresholds, risk limits,
session times, transaction costs. If one of these drifts from
`docs/STRATEGY.md`, the engine silently trades a different strategy than the
one that was specified and backtested. These tests pin the values.
"""

from __future__ import annotations

import importlib
from datetime import time

import pytest

import config


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch):
    """Reload `config` with a clean env so defaults are exercised."""
    for key in list(__import__("os").environ):
        if key.startswith("PAIRTRADE_"):
            monkeypatch.delenv(key, raising=False)
    importlib.reload(config)
    yield config.settings
    importlib.reload(config)


# --------------------------------------------------------------------------
# Signal thresholds — STRATEGY.md §5.1
# --------------------------------------------------------------------------


def test_z_score_thresholds_match_strategy(fresh_settings) -> None:
    s = fresh_settings
    assert s.zscore_entry_threshold == 2.0
    assert s.zscore_exit_threshold == 0.5
    assert s.zscore_stop_loss_threshold == 3.5


def test_holding_period_limits_match_strategy(fresh_settings) -> None:
    s = fresh_settings
    assert s.max_hold_bars == 45
    assert s.min_hold_bars == 3


# --------------------------------------------------------------------------
# Screening — STRATEGY.md §2, §4
# --------------------------------------------------------------------------


def test_screening_parameters_match_strategy(fresh_settings) -> None:
    s = fresh_settings
    assert s.screening_lookback_sessions == 60
    assert s.max_half_life_bars == 30
    assert s.adf_pvalue_threshold == 0.05
    assert s.min_edge_to_cost_ratio == 3.0
    assert s.max_concurrent_pairs == 10


# --------------------------------------------------------------------------
# Risk limits — STRATEGY.md §5.4
# --------------------------------------------------------------------------


def test_risk_limits_match_strategy(fresh_settings) -> None:
    s = fresh_settings
    assert s.max_notional_per_pair == 100_000
    assert s.max_total_gross_exposure == 500_000
    assert s.max_daily_loss == 50_000
    assert s.max_loss_per_trade == 7_500
    assert s.max_trades_per_day == 50
    assert s.max_drawdown == 0.20
    assert s.max_consecutive_losses_per_pair == 3


# --------------------------------------------------------------------------
# Session clock — STRATEGY.md §2, §5.1
# --------------------------------------------------------------------------


def test_session_times_are_ist(fresh_settings) -> None:
    s = fresh_settings
    assert s.timezone == "Asia/Kolkata"
    assert s.market_open == time(9, 15)
    assert s.entry_cutoff == time(14, 45)
    assert s.auto_square_off == time(15, 20)
    assert s.market_close == time(15, 30)


def test_entry_cutoff_precedes_square_off_precedes_close(fresh_settings) -> None:
    s = fresh_settings
    assert s.market_open < s.entry_cutoff < s.auto_square_off < s.market_close


# --------------------------------------------------------------------------
# Cost model — STRATEGY.md §5.3. Dated and versioned, never a blended bps.
# --------------------------------------------------------------------------


def test_cost_model_is_dated_and_versioned(fresh_settings) -> None:
    s = fresh_settings
    assert s.cost_model_version
    assert s.cost_model_as_of is not None


def test_cost_model_rates_match_strategy(fresh_settings) -> None:
    s = fresh_settings
    c = s.costs
    assert c.brokerage_per_order == 20.0
    assert c.stt_rate == 0.0008          # 0.08%, sell side only
    assert c.exchange_transaction_rate == 0.0000297  # ~0.00297%
    assert c.sebi_turnover_rate == 0.000001          # Rs 10 per crore
    assert c.ipst_rate == 0.0000003                   # Rs 3 per crore
    assert c.gst_rate == 0.18
    assert c.stamp_duty_rate == 0.00003              # 0.003%, buy side intraday
    assert c.tick_size == 0.05


def test_stt_and_stamp_duty_are_one_sided(fresh_settings) -> None:
    """STT is sell-side only; stamp duty is buy-side only."""
    c = fresh_settings.costs
    assert c.stt_side == "sell"
    assert c.stamp_duty_side == "buy"


# --------------------------------------------------------------------------
# Secrets and overrides
# --------------------------------------------------------------------------


def test_jwt_secret_has_no_usable_production_default(fresh_settings) -> None:
    """A real deployment must never boot on the built-in dev secret."""
    s = fresh_settings
    assert s.environment in {"dev", "test", "prod"}
    if s.environment == "prod":
        assert "dev-only" not in s.jwt_secret_key
        assert "change-me" not in s.jwt_secret_key


def test_env_override_changes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAIRTRADE_MAX_DAILY_LOSS", "12345")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.settings.max_daily_loss == 12_345
    finally:
        monkeypatch.delenv("PAIRTRADE_MAX_DAILY_LOSS")
        importlib.reload(config)


def test_settings_is_a_singleton() -> None:
    assert config.settings is config.settings
    assert isinstance(config.settings, config.Settings)
