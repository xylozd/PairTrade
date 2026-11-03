import polars as pl
from datetime import date
from typing import List, Tuple

class CorporateActionAdjuster:
    def __init__(self, barstore: "BarStore"):
        self.barstore = barstore

    def get_actions(self, symbol: str, start: date, end: date) -> pl.DataFrame:
        # Fetch corporate actions from BarStore
        return self.barstore.corporate_actions(symbol, start, end)

    def adjust_prices(self, bars: pl.DataFrame, actions: pl.DataFrame) -> pl.DataFrame:
        # Apply split and dividend adjustments
        adjusted_bars = bars.clone()

        # Process splits: multiply prices before split date by ratio
        split_actions = actions.filter(pl.col("action_type") == "split")
        for action in split_actions.iter_rows(named=True):
            effective_date = action["effective_date"]
            ratio = action["ratio"]
            adjusted_bars = adjusted_bars.with_columns([
                pl.when(pl.col("date") < effective_date)
                  .then(pl.col(col) * ratio)
                  .otherwise(pl.col(col))
                  .alias(col)
                for col in ["open", "high", "low", "close"]
            ])

        # Process dividends: subtract dividend amount from prices before ex-date
        dividend_actions = actions.filter(pl.col("action_type") == "dividend")
        for action in dividend_actions.iter_rows(named=True):
            ex_date = action["ex_date"]
            amount = action["amount"]
            adjusted_bars = adjusted_bars.with_columns([
                pl.when(pl.col("date") < ex_date)
                  .then(pl.col(col) - amount)
                  .otherwise(pl.col(col))
                  .alias(col)
                for col in ["open", "high", "low", "close"]
            ])

        # Add adjusted flag
        adjusted_bars = adjusted_bars.with_columns(adjusted=pl.Series([True] * len(adjusted_bars)))
        return adjusted_bars

    def has_actions_in_window(self, symbol: str, start: date, end: date) -> bool:
        actions = self.get_actions(symbol, start, end)
        return not actions.is_empty()
