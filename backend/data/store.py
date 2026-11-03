import pyarrow.parquet as pq
import pyarrow.dataset as ds
import pandas as pd
from pathlib import Path
from typing import Optional

class ParquetBarStore:
    def __init__(self, base_path: str = "data/bars"):
        self.base_path = Path(base_path).resolve()

    def _validate_schema(self, df: pd.DataFrame) -> None:
        expected_schema = {
            "timestamp": "datetime64[ns]",
            "symbol": "str",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "int64"
        }
        for column, expected_dtype in expected_schema.items():
            if column not in df.columns:
                raise ValueError(f"Missing required column: {column}")
            if df[column].dtype.name != expected_dtype:
                raise ValueError(f"Column {column} has incorrect dtype. Expected {expected_dtype}, got {df[column].dtype.name}")

    def write(self, df: pd.DataFrame, symbol: str, date: str) -> None:
        self._validate_schema(df)
        # Ensure partition directories exist
        partition_path = self.base_path / f"symbol={symbol}" / f"date={date}"
        partition_path.mkdir(parents=True, exist_ok=True)
        # Write or append to data.parquet
        table = pq.Table.from_pandas(df)
        dataset = ds.dataset(str(partition_path), format="parquet")
        # Check if data already exists to ensure idempotency
        if dataset:
            existing_df = dataset.to_table().to_pandas()
            if not existing_df.empty:
                # Check for duplicates
                merged = pd.merge(existing_df, df, indicator=True, how='outer')
                if len(merged[merged['_merge'] == 'both']) > 0:
                    # Duplicate data found, skip writing
                    return
        # Write the DataFrame
        pq.write_table(table, str(partition_path / "data.parquet"))

    def read(self, symbol: str, date: str) -> Optional[pd.DataFrame]:
        partition_path = self.base_path / f"symbol={symbol}" / f"date={date}"
        if not partition_path.exists():
            return None
        dataset = ds.dataset(str(partition_path), format="parquet")
        return dataset.to_table().to_pandas()
