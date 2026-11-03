"""Batch download manager for historical bar data.

Phase 1, Task 1.6: Downloads bars for multiple symbols across date ranges with
idempotent resumption, exponential backoff on rate limits, and progress tracking.

Key features:
- Batch download with progress tracking (every 10 symbols)
- Exponential backoff on rate limits (1s, 2s, 4s, 8s, fail)
- Resume from last successful download
- Idempotent: re-running does not duplicate data
- Store download metadata (timestamp, symbol count, date range)

Design:
- Takes a `BarStore` provider (source) and `ParquetBarStore` sink (destination)
- State tracking in `data/downloads/.state.json`
- Per-symbol download status: complete|partial|failed
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

import polars as pl

from backend.data.barstore import BarStore
from backend.data.store import ParquetBarStore

logger = logging.getLogger(__name__)


class BarDownloader:
    """Batch downloader with progress tracking, retry logic, and resume capability.

    Example:
        >>> provider = YFinanceBarStore()
        >>> sink = ParquetBarStore("data/bars")
        >>> downloader = BarDownloader(provider, sink)
        >>> result = downloader.download_batch(
        ...     symbols=["RELIANCE", "TCS", "INFY"],
        ...     start=date(2026, 1, 1),
        ...     end=date(2026, 3, 31)
        ... )
        >>> print(f"Success: {result['success']}, Failed: {result['failed']}")
    """

    def __init__(
        self,
        provider: BarStore,
        sink: ParquetBarStore,
        state_dir: str = "data/downloads",
        max_retries: int = 4,
        progress_interval: int = 10,
    ):
        """Initialize the batch downloader.

        Args:
            provider: Data source implementing BarStore protocol
            sink: ParquetBarStore for writing downloaded data
            state_dir: Directory for tracking download state
            max_retries: Maximum retry attempts with exponential backoff
            progress_interval: Log progress every N symbols
        """
        self.provider = provider
        self.sink = sink
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / ".state.json"
        self.max_retries = max_retries
        self.progress_interval = progress_interval
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load download state from disk."""
        if not self.state_file.exists():
            return {}

        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load state file: {e}. Starting fresh.")
            return {}

    def _save_state(self) -> None:
        """Persist download state to disk."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self._state, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save state file: {e}")

    def _get_symbol_state(self, symbol: str) -> dict:
        """Get download state for a symbol."""
        return self._state.get(symbol, {
            "status": "pending",
            "last_date": None,
            "attempts": 0,
            "last_error": None,
        })

    def _update_symbol_state(
        self,
        symbol: str,
        status: str,
        last_date: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update download state for a symbol."""
        if symbol not in self._state:
            self._state[symbol] = {}

        self._state[symbol]["status"] = status
        if last_date is not None:
            self._state[symbol]["last_date"] = last_date
        if error is not None:
            self._state[symbol]["last_error"] = error
        self._state[symbol]["updated_at"] = datetime.now().isoformat()

        self._save_state()

    def _should_skip_symbol(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> bool:
        """Check if symbol should be skipped (already complete in range)."""
        state = self._get_symbol_state(symbol)

        # Skip if complete and covers the entire requested range
        if state["status"] == "complete" and state["last_date"]:
            last_downloaded = date.fromisoformat(state["last_date"])
            if last_downloaded >= end:
                logger.debug(f"Skipping {symbol}: already complete through {last_downloaded}")
                return True

        return False

    def _exponential_backoff(self, attempt: int, error: Exception) -> bool:
        """Apply exponential backoff on rate limit errors.

        Args:
            attempt: Current retry attempt (0-indexed)
            error: The exception that triggered the retry

        Returns:
            True if should retry, False if max retries exceeded
        """
        if attempt >= self.max_retries:
            return False

        # Calculate backoff: 1s, 2s, 4s, 8s
        delay = 2 ** attempt

        # Check if this is a rate limit error (heuristic)
        error_str = str(error).lower()
        is_rate_limit = any(
            keyword in error_str
            for keyword in ["rate limit", "too many requests", "429", "throttle"]
        )

        if is_rate_limit:
            logger.warning(
                f"Rate limit hit (attempt {attempt + 1}/{self.max_retries}). "
                f"Backing off {delay}s..."
            )
        else:
            logger.warning(
                f"Error occurred (attempt {attempt + 1}/{self.max_retries}): {error}. "
                f"Retrying in {delay}s..."
            )

        time.sleep(delay)
        return True

    def download_symbol(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "5m",
    ) -> bool:
        """Download bars for a single symbol with retry logic.

        Args:
            symbol: NSE symbol code
            start: Start date (inclusive)
            end: End date (inclusive)
            interval: Bar interval (default "5m")

        Returns:
            True if successful, False if all retries exhausted
        """
        for attempt in range(self.max_retries + 1):
            try:
                # Fetch bars from provider
                df = self.provider.bars(
                    symbols=[symbol],
                    start=start,
                    end=end,
                    interval=interval,
                )

                # Check if data was returned
                if df.is_empty():
                    logger.warning(f"No data returned for {symbol}")
                    self._update_symbol_state(
                        symbol,
                        status="partial",
                        last_date=end.isoformat(),
                        error="No data returned",
                    )
                    return False

                # Convert to pandas for ParquetBarStore compatibility
                df_pandas = df.to_pandas()

                # Write data partitioned by date
                # Group by date and write each partition
                df_pandas['date'] = df_pandas['timestamp'].dt.date

                for date_val, group_df in df_pandas.groupby('date'):
                    # Drop the date column before writing
                    group_df = group_df.drop(columns=['date'])
                    self.sink.write(
                        df=group_df,
                        symbol=symbol,
                        date=date_val.isoformat(),
                    )

                # Update state to complete
                self._update_symbol_state(
                    symbol,
                    status="complete",
                    last_date=end.isoformat(),
                )

                logger.info(f"Successfully downloaded {symbol}: {len(df)} bars")
                return True

            except Exception as e:
                if not self._exponential_backoff(attempt, e):
                    # Max retries exceeded
                    logger.error(
                        f"Failed to download {symbol} after {self.max_retries} retries: {e}"
                    )
                    self._update_symbol_state(
                        symbol,
                        status="failed",
                        error=str(e),
                    )
                    return False

        return False

    def download_batch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        interval: str = "5m",
    ) -> dict:
        """Download bars for multiple symbols with progress tracking.

        This is the main entry point for batch downloads. It:
        - Skips symbols already complete in the target range (idempotent)
        - Logs progress every N symbols
        - Estimates time remaining
        - Continues on errors (downloads all possible symbols)

        Args:
            symbols: List of NSE symbol codes
            start: Start date (inclusive)
            end: End date (inclusive)
            interval: Bar interval (default "5m")

        Returns:
            Summary dict with keys:
            - success: Number of successfully downloaded symbols
            - failed: List of failed symbol names
            - skipped: Number of skipped symbols (already complete)
            - total: Total symbols processed
            - elapsed_seconds: Total elapsed time
        """
        start_time = time.time()
        success_count = 0
        failed_symbols = []
        skipped_count = 0
        total = len(symbols)

        logger.info(
            f"Starting batch download: {total} symbols, "
            f"{start.isoformat()} to {end.isoformat()}"
        )

        for idx, symbol in enumerate(symbols, start=1):
            # Check if should skip
            if self._should_skip_symbol(symbol, start, end):
                skipped_count += 1
                continue

            # Download symbol
            success = self.download_symbol(symbol, start, end, interval)

            if success:
                success_count += 1
            else:
                failed_symbols.append(symbol)

            # Log progress every N symbols
            if idx % self.progress_interval == 0:
                elapsed = time.time() - start_time
                processed = idx
                remaining = total - processed

                # Estimate time remaining
                if processed > 0:
                    avg_time_per_symbol = elapsed / processed
                    eta_seconds = avg_time_per_symbol * remaining
                    eta_minutes = eta_seconds / 60

                    logger.info(
                        f"Progress: {processed}/{total} symbols "
                        f"({processed/total*100:.1f}%) | "
                        f"Success: {success_count}, Failed: {len(failed_symbols)}, "
                        f"Skipped: {skipped_count} | "
                        f"ETA: {eta_minutes:.1f} min"
                    )

        elapsed_seconds = time.time() - start_time

        # Final summary
        result = {
            "success": success_count,
            "failed": failed_symbols,
            "skipped": skipped_count,
            "total": total,
            "elapsed_seconds": elapsed_seconds,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"Batch download complete: {success_count} succeeded, "
            f"{len(failed_symbols)} failed, {skipped_count} skipped "
            f"in {elapsed_seconds:.1f}s"
        )

        # Save download metadata
        self._save_download_metadata(result)

        return result

    def _save_download_metadata(self, result: dict) -> None:
        """Save download metadata for audit trail."""
        metadata_file = self.state_dir / f"download_{result['timestamp'].replace(':', '-')}.json"
        try:
            with open(metadata_file, "w") as f:
                json.dump(result, f, indent=2)
        except IOError as e:
            logger.warning(f"Failed to save download metadata: {e}")

    def get_download_status(self) -> dict:
        """Get summary of what's been downloaded and what's pending.

        Returns:
            Dict with keys:
            - complete: List of symbols with status=complete
            - partial: List of symbols with status=partial
            - failed: List of symbols with status=failed
            - pending: List of symbols with status=pending
            - total_symbols: Total number of tracked symbols
        """
        complete = []
        partial = []
        failed = []
        pending = []

        for symbol, state in self._state.items():
            status = state.get("status", "pending")

            if status == "complete":
                complete.append({
                    "symbol": symbol,
                    "last_date": state.get("last_date"),
                })
            elif status == "partial":
                partial.append({
                    "symbol": symbol,
                    "last_date": state.get("last_date"),
                    "error": state.get("last_error"),
                })
            elif status == "failed":
                failed.append({
                    "symbol": symbol,
                    "error": state.get("last_error"),
                })
            else:
                pending.append(symbol)

        return {
            "complete": complete,
            "partial": partial,
            "failed": failed,
            "pending": pending,
            "total_symbols": len(self._state),
        }

    def reset_symbol(self, symbol: str) -> None:
        """Reset download state for a symbol (for manual retry)."""
        if symbol in self._state:
            del self._state[symbol]
            self._save_state()
            logger.info(f"Reset state for {symbol}")

    def reset_failed(self) -> None:
        """Reset all failed symbols for retry."""
        failed = [
            symbol for symbol, state in self._state.items()
            if state.get("status") == "failed"
        ]

        for symbol in failed:
            del self._state[symbol]

        self._save_state()
        logger.info(f"Reset {len(failed)} failed symbols")
