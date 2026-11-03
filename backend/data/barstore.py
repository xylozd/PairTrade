"""Provider-agnostic bar storage protocol.

The `BarStore` protocol defines the interface every data provider must implement.
No provider-specific details (yfinance's 60-day cap, Dhan's 5-day limit, broker
entitlements) leak past this interface. The strategy engine and backtester depend
only on the protocol — providers are swappable.

Design notes (STRATEGY.md §3.2):

1. **Point-in-time semantics for `symbol_master(as_of)`**: the universe at any
   historical date must include symbols that were live then, even if delisted
   today. Using today's Nifty 200 list to backtest last year is survivorship bias.

2. **Corporate actions before screening**: a split in one leg of a pair creates a
   fake unit root in the spread. Adjust both legs before running cointegration
   tests, or you'll find "significant" pairs that lose money live.

3. **Return type is `polars.DataFrame`**: the screening engine uses Polars for
   wide-panel operations (one column per symbol) with lazy evaluation. Providers
   may fetch from any source, but the return must be Polars.

Schema specifications below describe the mandatory columns and types for each
method's return value. Providers that omit required columns or use incompatible
types will fail contract tests.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, Sequence

import polars as pl


class BarStore(Protocol):
    """Provider-agnostic interface for OHLCV bar data and symbol metadata.

    All providers (yfinance, Dhan, broker historical APIs, local Parquet stores)
    must implement this protocol. The strategy engine never imports a provider
    directly — it accepts any `BarStore`-compatible object.

    Implementations should be registered in a provider factory, keyed by a string
    identifier (e.g., "yfinance", "dhan", "parquet"). The data layer selects a
    provider at runtime based on configuration, not hardcoded imports.
    """

    def bars(
        self,
        symbols: Sequence[str],
        start: date | datetime,
        end: date | datetime,
        interval: str = "5m",
    ) -> pl.DataFrame:
        """Fetch OHLCV bars for the given symbols and date range.

        Args:
            symbols: NSE symbol codes (e.g., ["RELIANCE", "TCS", "INFY"]).
            start: Inclusive start date/datetime.
            end: Inclusive end date/datetime.
            interval: Bar interval — "5m" (default), "15m", "30m", "1h", "1d".
                      Providers that don't support a requested interval should
                      raise `ValueError` rather than silently returning a
                      different interval.

        Returns:
            Polars DataFrame with the following schema:

            | Column      | Type                  | Description                          |
            |-------------|-----------------------|--------------------------------------|
            | `timestamp` | `pl.Datetime`         | Bar start time (UTC or IST, consistent per provider) |
            | `symbol`    | `pl.Utf8`             | NSE symbol code                      |
            | `open`      | `pl.Float64`          | Open price                           |
            | `high`      | `pl.Float64`          | High price                           |
            | `low`       | `pl.Float64`          | Low price                            |
            | `close`     | `pl.Float64`          | Close price                          |
            | `volume`    | `pl.Int64`            | Volume (shares traded)               |

            - Timestamps must be timezone-aware (prefer UTC; IST is acceptable if
              consistent). The caller is responsible for timezone conversion.
            - Missing bars are omitted, not filled with NaN/null. Gaps indicate
              no trading (market closed, circuit breaker, symbol suspended).
            - Rows are sorted by (`symbol`, `timestamp`).

        Raises:
            ValueError: If the interval is unsupported or the date range exceeds
                        the provider's capabilities (e.g., yfinance's 60-day cap).
            LookupError: If none of the requested symbols exist.

        Notes:
            - **Lookback limits are provider-specific.** yfinance caps 5-minute
              data at 60 days; Dhan caps at 5 trading days. The provider should
              raise `ValueError` with a clear message ("yfinance 5m data is
              capped at 60 days; requested range spans 365 days") rather than
              silently truncating.
            - **Adjustments:** this method returns **raw** (unadjusted) prices by
              default. Corporate-action adjustments are applied separately via
              `corporate_actions()` before screening. Providers that only offer
              pre-adjusted data (e.g., yfinance `auto_adjust=True`) must document
              that caveat.
        """
        ...

    def symbol_master(self, as_of: date) -> pl.DataFrame:
        """Fetch the point-in-time universe membership as of a given date.

        Args:
            as_of: The date for which to reconstruct the universe. This must
                   support historical queries — calling with `as_of=2025-06-01`
                   should return the symbols that were in the target universe
                   (e.g., Nifty 200) on that date, even if some have since been
                   delisted or removed from the index.

        Returns:
            Polars DataFrame with the following schema:

            | Column          | Type          | Description                          |
            |-----------------|---------------|--------------------------------------|
            | `symbol`        | `pl.Utf8`     | NSE symbol code                      |
            | `name`          | `pl.Utf8`     | Company name                         |
            | `sector`        | `pl.Utf8`     | Sector classification (optional)     |
            | `valid_from`    | `pl.Date`     | Date this symbol entered the universe|
            | `valid_to`      | `pl.Date`     | Date this symbol left (null if live) |
            | `is_active`     | `pl.Boolean`  | True if actively trading on `as_of`  |

            - `valid_to` is `null` for symbols still in the universe.
            - `is_active=False` indicates a delisted or suspended symbol that was
              live on `as_of` but is no longer trading.

        Raises:
            ValueError: If `as_of` is before the provider's data start date.

        Notes:
            - **Point-in-time semantics are mandatory.** Using today's Nifty 200
              constituents to backtest 2025 is survivorship bias — companies that
              underperformed and were removed from the index are missing, which
              inflates backtest results.
            - **Snapshot discipline:** once fetched, a historical symbol list is
              unrecoverable from most sources. Persist a dated copy of every list
              ever fetched, with validity intervals derived from index-change
              events (rebalances, delistings) and daily bhavcopy symbol presence.
            - **Delisted symbols must be included** if they were live on `as_of`.
              This is the primary bias check — see STRATEGY.md §6.5.
            - Providers that cannot reconstruct historical membership (e.g.,
              yfinance, which has no index-change history) should document that
              limitation and fail with a clear error rather than returning today's
              list labeled with a historical date.
        """
        ...

    def corporate_actions(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        """Fetch corporate actions (splits, bonuses, dividends) for adjustment.

        Args:
            symbols: NSE symbol codes.
            start: Inclusive start date.
            end: Inclusive end date.

        Returns:
            Polars DataFrame with the following schema:

            | Column       | Type          | Description                          |
            |--------------|---------------|--------------------------------------|
            | `symbol`     | `pl.Utf8`     | NSE symbol code                      |
            | `ex_date`    | `pl.Date`     | Ex-date (the date the action takes effect) |
            | `action`     | `pl.Utf8`     | Action type: "split", "bonus", "dividend" |
            | `ratio`      | `pl.Float64`  | Split/bonus ratio (e.g., 2.0 for 1:2 split) |
            | `amount`     | `pl.Float64`  | Dividend amount (Rs per share)       |

            - For splits and bonuses, `ratio` is the multiplier applied to prices
              (e.g., a 1:10 split sets `ratio=10.0`; old price × 10 = adjusted).
            - For dividends, `amount` is the payout per share; `ratio=1.0`.
            - Empty DataFrame (0 rows) if no actions in the date range.

        Raises:
            LookupError: If none of the requested symbols exist.

        Notes:
            - **Adjustment before screening:** a split or bonus in one leg of a
              cointegration pair creates a fake unit root in the spread — the
              unadjusted price series shows a structural break that looks like
              non-stationarity. Both legs must be adjusted **before** running ADF
              tests. See STRATEGY.md §3.1.
            - **Ex-date is the key date:** the action affects prices from the
              ex-date onward. Adjust all bars with `timestamp >= ex_date`.
            - **Source priority:** NSE bhavcopy "CA" files, then `nselib`/`nsepython`
              corporate-action endpoints, then broker APIs. yfinance's `actions`
              DataFrame is available but sometimes incomplete for NSE symbols.
        """
        ...
