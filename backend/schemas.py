"""Shared Pydantic schemas.

These are the wire shapes the API, the WebSocket feed and the frontend all
speak. Two conventions apply throughout:

- **`extra="forbid"`** — an unknown field is an error, not a silent drop. A
  typo in a payload should fail loudly at the boundary instead of quietly
  losing data downstream.
- **Invariants are enforced at the edge** — a pair with the same symbol on both
  legs, a negative price, or a NaN z-score is rejected here rather than
  becoming an unhedged position in the engine.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Side(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class SignalType(str, Enum):
    """Lifecycle events the engine emits.

    `ENTRY_LONG_SPREAD` means long the cheap leg and short the rich leg
    (z < -2); `ENTRY_SHORT_SPREAD` is the mirror (z > +2).
    """

    ENTRY_LONG_SPREAD = "ENTRY_LONG_SPREAD"
    ENTRY_SHORT_SPREAD = "ENTRY_SHORT_SPREAD"
    EXIT = "EXIT"
    STOP_LOSS = "STOP_LOSS"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(StrictModel):
    """Service liveness payload."""

    status: str = "ok"
    version: str


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


class Symbol(StrictModel):
    """An NSE trading symbol."""

    symbol: str = Field(min_length=1)
    exchange: str = "NSE"

    @field_validator("symbol")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()


class PairLeg(StrictModel):
    """One leg of a two-leg pair position."""

    symbol: str = Field(min_length=1)
    side: Side
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()


class Pair(StrictModel):
    """A cointegrated pair and its frozen hedge ratio."""

    symbol_a: str = Field(min_length=1)
    symbol_b: str = Field(min_length=1)
    hedge_ratio: float = Field(gt=0)
    enabled: bool = True
    adf_pvalue: float | None = None
    half_life_bars: float | None = None

    @field_validator("symbol_a", "symbol_b")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()

    @model_validator(mode="after")
    def _check_distinct_legs(self) -> "Pair":
        if self.symbol_a == self.symbol_b:
            raise ValueError("a pair must have two distinct symbols")
        return self


# ---------------------------------------------------------------------------
# Signals and state
# ---------------------------------------------------------------------------


class ZScorePoint(StrictModel):
    """One observation of a pair's spread z-score."""

    z_score: float
    spread: float
    timestamp: datetime

    @field_validator("z_score", "spread")
    @classmethod
    def _reject_non_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class Signal(StrictModel):
    """A trading signal emitted by the engine."""

    pair_symbol_a: str = Field(min_length=1)
    pair_symbol_b: str = Field(min_length=1)
    signal_type: SignalType
    price: float = Field(ge=0)
    z_score: float | None = None
    quantity: int | None = Field(default=None, gt=0)
    timestamp: datetime

    @field_validator("z_score")
    @classmethod
    def _reject_non_finite_z(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("z_score must be finite")
        return value

    @field_validator("pair_symbol_a", "pair_symbol_b")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()

    @model_validator(mode="after")
    def _check_distinct_legs(self) -> "Signal":
        if self.pair_symbol_a == self.pair_symbol_b:
            raise ValueError("a signal must reference two distinct symbols")
        return self


class Position(StrictModel):
    """An open pair position."""

    pair_symbol_a: str = Field(min_length=1)
    pair_symbol_b: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    unrealised_pnl: float = 0.0
    opened_at: datetime

    @field_validator("pair_symbol_a", "pair_symbol_b")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()

    @model_validator(mode="after")
    def _check_distinct_legs(self) -> "Position":
        if self.pair_symbol_a == self.pair_symbol_b:
            raise ValueError("a position must reference two distinct symbols")
        return self


class Trade(StrictModel):
    """A closed pair trade."""

    pair_symbol_a: str = Field(min_length=1)
    pair_symbol_b: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    pnl: float
    opened_at: datetime
    closed_at: datetime

    @field_validator("pair_symbol_a", "pair_symbol_b")
    @classmethod
    def _normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("symbol must not be blank")
        return cleaned.upper()

    @model_validator(mode="after")
    def _check_distinct_legs(self) -> "Trade":
        if self.pair_symbol_a == self.pair_symbol_b:
            raise ValueError("a trade must reference two distinct symbols")
        return self


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorResponse(StrictModel):
    """Uniform error body for API responses."""

    detail: str
    error_code: str | None = None
