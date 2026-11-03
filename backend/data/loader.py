import duckdb
import polars as pl

class DuckDBBarLoader:
    def load_bars(self, symbols: list[str], start: date, end: date) -> pl.DataFrame:
        query = f"""
        SELECT *
        FROM read_parquet(glob('data/bars/symbol=*/date=*/data.parquet'))
        WHERE symbol IN ({','.join(['?'] * len(symbols))})
        AND date BETWEEN ? AND ?
        ORDER BY symbol, timestamp
        """
        return duckdb.sql(query, parameters=symbols + [start, end]).pl()

    def load_session_bars(self, symbols: list[str], session_date: date) -> pl.DataFrame:
        query = f"""
        SELECT *
        FROM read_parquet(glob('data/bars/symbol=*/date=*/data.parquet'))
        WHERE symbol IN ({','.join(['?'] * len(symbols))})
        AND date = ?
        AND session_start <= ? AND session_end >= ?
        ORDER BY symbol, timestamp
        """
        # Assuming session_date is used for date and time range
        return duckdb.sql(query, parameters=symbols + [session_date, session_date, session_date]).pl()

    def count_bars(self, symbols: list[str], start: date, end: date) -> int:
        query = f"""
        SELECT COUNT(open)
        FROM read_parquet(glob('data/bars/symbol=*/date=*/data.parquet'))
        WHERE symbol IN ({','.join(['?'] * len(symbols))})
        AND date BETWEEN ? AND ?
        """
        result = duckdb.sql(query, parameters=symbols + [start, end])
        return result.fetchone()[0]

    def _validate_schema(self, df: pl.DataFrame):
        expected_columns = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in expected_columns:
            assert col in df.columns, f"Missing expected column: {col}"
        # Check for NaN/inf in price columns
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            assert df[col].is_finite().all(), f"NaN/inf detected in {col}"
        # Validate timestamps are monotonic
        assert df['timestamp'].is_monotonic(), "Timestamps are not monotonic"

    def load_bars_validated(self, symbols: list[str], start: date, end: date) -> pl.DataFrame:
        df = self.load_bars(symbols, start, end)
        self._validate_schema(df)
        return df
