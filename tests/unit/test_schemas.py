"""Pydantic schema validation.

These models are the wire format between the API, the WebSocket feed and the
frontend. Two failure modes matter:

- A field silently dropped (a typo in a payload) — hence `extra="forbid"`.
- A nonsensical value accepted (same symbol on both legs of a pair, a NaN
  z-score) — a pair that trades itself is not a recoverable bug.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas import (
    ErrorResponse,
    HealthResponse,
    Pair,
    PairLeg,
    Position,
    Side,
    Signal,
    SignalType,
    Symbol,
    Trade,
    ZScorePoint,
)


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


def test_side_enum_has_exactly_buy_and_sell() -> None:
    assert {s.value for s in Side} == {"BUY", "SELL"}


def test_signal_type_covers_the_strategy_lifecycle() -> None:
    values = {s.value for s in SignalType}
    assert values == {
        "ENTRY_LONG_SPREAD",
        "ENTRY_SHORT_SPREAD",
        "EXIT",
        "STOP_LOSS",
    }


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def test_health_response_requires_version() -> None:
    response = HealthResponse(status="ok", version="0.1.0")
    assert response.status == "ok"
    assert response.version == "0.1.0"

    with pytest.raises(ValidationError):
        HealthResponse(status="ok")


# --------------------------------------------------------------------------
# Symbol
# --------------------------------------------------------------------------


def test_symbol_normalises_to_uppercase() -> None:
    assert Symbol(symbol="reliance").symbol == "RELIANCE"
    assert Symbol(symbol="  tcs  ").symbol == "TCS"


@pytest.mark.parametrize("bad", ["", "   ", "\t"])
def test_symbol_rejects_blank(bad: str) -> None:
    with pytest.raises(ValidationError):
        Symbol(symbol=bad)


# --------------------------------------------------------------------------
# Pair
# --------------------------------------------------------------------------


def test_pair_requires_distinct_symbols() -> None:
    with pytest.raises(ValidationError):
        Pair(symbol_a="INFY", symbol_b="INFY", hedge_ratio=1.0)


def test_pair_requires_positive_hedge_ratio() -> None:
    with pytest.raises(ValidationError):
        Pair(symbol_a="INFY", symbol_b="TCS", hedge_ratio=0.0)
    with pytest.raises(ValidationError):
        Pair(symbol_a="INFY", symbol_b="TCS", hedge_ratio=-1.2)


def test_pair_accepts_a_valid_pair() -> None:
    pair = Pair(symbol_a="INFY", symbol_b="TCS", hedge_ratio=1.05)
    assert pair.symbol_a == "INFY"
    assert pair.symbol_b == "TCS"


# --------------------------------------------------------------------------
# PairLeg
# --------------------------------------------------------------------------


def test_pair_leg_requires_positive_quantity_and_price() -> None:
    leg = PairLeg(symbol="INFY", side=Side.BUY, quantity=100, price=1500.0)
    assert leg.side is Side.BUY

    with pytest.raises(ValidationError):
        PairLeg(symbol="INFY", side=Side.BUY, quantity=0, price=1500.0)
    with pytest.raises(ValidationError):
        PairLeg(symbol="INFY", side=Side.BUY, quantity=100, price=0.0)


# --------------------------------------------------------------------------
# Z-score
# --------------------------------------------------------------------------


def test_zscore_point_carries_spread_and_timestamp() -> None:
    now = datetime.now(timezone.utc)
    point = ZScorePoint(z_score=2.35, spread=0.012, timestamp=now)
    assert point.z_score == 2.35
    assert point.spread == 0.012
    assert point.timestamp == now


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_zscore_point_rejects_non_finite(bad: float) -> None:
    with pytest.raises(ValidationError):
        ZScorePoint(z_score=bad, spread=0.01, timestamp=datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Signal
# --------------------------------------------------------------------------


def test_signal_requires_timestamp() -> None:
    with pytest.raises(ValidationError):
        Signal(
            pair_symbol_a="INFY",
            pair_symbol_b="TCS",
            signal_type=SignalType.ENTRY_LONG_SPREAD,
            price=1500.0,
        )


def test_signal_rejects_negative_price() -> None:
    with pytest.raises(ValidationError):
        Signal(
            pair_symbol_a="INFY",
            pair_symbol_b="TCS",
            signal_type=SignalType.ENTRY_LONG_SPREAD,
            price=-1.0,
            timestamp=datetime.now(timezone.utc),
        )


# --------------------------------------------------------------------------
# Position / Trade
# --------------------------------------------------------------------------


def test_position_requires_positive_quantity() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        pair_symbol_a="INFY",
        pair_symbol_b="TCS",
        quantity=100,
        entry_price=1500.0,
        opened_at=now,
    )
    assert position.quantity == 100

    with pytest.raises(ValidationError):
        Position(
            pair_symbol_a="INFY",
            pair_symbol_b="TCS",
            quantity=0,
            entry_price=1500.0,
            opened_at=now,
        )


def test_trade_records_realised_pnl() -> None:
    now = datetime.now(timezone.utc)
    trade = Trade(
        pair_symbol_a="INFY",
        pair_symbol_b="TCS",
        quantity=100,
        entry_price=1500.0,
        exit_price=1510.0,
        pnl=1000.0,
        opened_at=now,
        closed_at=now,
    )
    assert trade.pnl == 1000.0


# --------------------------------------------------------------------------
# Strictness
# --------------------------------------------------------------------------


def test_unknown_fields_are_rejected() -> None:
    """A typo in a payload must fail loudly rather than silently drop data."""
    with pytest.raises(ValidationError):
        HealthResponse(status="ok", version="0.1.0", unexpected="boom")


def test_error_response_shape() -> None:
    error = ErrorResponse(detail="pair not found", error_code="PAIR_NOT_FOUND")
    assert error.detail == "pair not found"
    assert error.error_code == "PAIR_NOT_FOUND"
