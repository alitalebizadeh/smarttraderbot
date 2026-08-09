from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

__all__ = [
    "MT5Loader",
    "MT5LoaderError",
    "create_loader",
    "MT5_AVAILABLE",
    "STANDARD_COLUMNS",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

STANDARD_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "tick_volume")

CSV_SEPARATOR_CANDIDATES: tuple[str, ...] = (",", "\t", ";")

MT5_TIMEFRAME_MAP: dict[str, int] = (
    {
        "M1":  mt5.TIMEFRAME_M1,   # type: ignore[union-attr]
        "M5":  mt5.TIMEFRAME_M5,   # type: ignore[union-attr]
        "M15": mt5.TIMEFRAME_M15,  # type: ignore[union-attr]
        "M30": mt5.TIMEFRAME_M30,  # type: ignore[union-attr]
        "H1":  mt5.TIMEFRAME_H1,   # type: ignore[union-attr]
        "H4":  mt5.TIMEFRAME_H4,   # type: ignore[union-attr]
        "D1":  mt5.TIMEFRAME_D1,   # type: ignore[union-attr]
        "W1":  mt5.TIMEFRAME_W1,   # type: ignore[union-attr]
        "MN1": mt5.TIMEFRAME_MN1,  # type: ignore[union-attr]
    }
    if MT5_AVAILABLE
    else {}
)

_MIN_COLUMNS_THRESHOLD: int = 5
_MIN_PRICE_VALUE: float = 0.0


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class MT5LoaderError(Exception):
    """Raised when loading candle data from MT5 or CSV fails.

    Attributes:
        message: Human-readable description of the failure.
        cause: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        """Initialize with a message and optional root cause.

        Args:
            message: Description of the load failure.
            cause: Optional underlying exception.
        """
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        """Return a string representation including the cause if present.

        Returns:
            Formatted error string.
        """
        base = super().__str__()
        if self.cause is not None:
            return f"{base} | Caused by: {type(self.cause).__name__}: {self.cause}"
        return base


# ─────────────────────────────────────────────
#  Loader
# ─────────────────────────────────────────────

class MT5Loader:
    """Loads OHLCV candle data from MetaTrader 5 or CSV files into DataFrames.

    Supports two operating modes:
    - Phase 1 (CSV): reads MT5-exported CSV files from a local directory.
    - Phase 2 (Live): fetches candles directly from a connected MT5 terminal.

    The primary entry point is `load()`, which automatically selects the
    appropriate mode based on whether a live connection is provided.

    All returned DataFrames share a standard format:
    - Columns: open, high, low, close, tick_volume (plus any extras)
    - Index: DatetimeIndex named "time", sorted ascending, no duplicates
    - Types: open/high/low/close → float64, tick_volume → int64

    Example:
        loader = MT5Loader(data_dir="data")
        df = loader.load("XAUUSD", "M1", max_candles=500)
        print(df.shape)
    """

    def __init__(self, data_dir: str = "data") -> None:
        """Initialize the loader with a data directory for CSV files.

        Args:
            data_dir: Path to the directory containing CSV files exported from MT5.
        """
        self._data_dir = Path(data_dir)
        self._logger = logging.getLogger(__name__)

    def load_csv(
        self,
        symbol: str,
        timeframe: str,
        max_candles: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load candle data from a CSV file exported by MetaTrader 5.

        Automatically detects the separator and handles both single-column
        datetime format (time) and split Date/Time column format.

        Args:
            symbol: Trading instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "M1", "H4").
            max_candles: If set, return only the last N candles.

        Returns:
            A normalized DataFrame with OHLCV data.

        Raises:
            MT5LoaderError: If the file is not found, cannot be parsed,
                or is missing required columns after normalization.
        """
        filename = f"{symbol.upper()}_{timeframe.upper()}.csv"
        filepath = self._data_dir / filename

        if not filepath.exists():
            raise MT5LoaderError(
                f"CSV file not found: {filepath}. "
                f"Export '{symbol} {timeframe}' from MT5 to the data directory."
            )

        df: Optional[pd.DataFrame] = None
        last_exc: Optional[Exception] = None

        for sep in CSV_SEPARATOR_CANDIDATES:
            try:
                candidate = pd.read_csv(
                    filepath,
                    sep=sep,
                    engine="python",
                    on_bad_lines="skip",
                )
                if len(candidate.columns) >= _MIN_COLUMNS_THRESHOLD:
                    df = candidate
                    self._logger.debug(
                        "Parsed '%s' with separator %r — %d columns detected.",
                        filename,
                        sep,
                        len(candidate.columns),
                    )
                    break
            except Exception as exc:
                last_exc = exc
                continue

        if df is None:
            raise MT5LoaderError(
                f"Could not parse '{filepath}' with any known separator "
                f"({CSV_SEPARATOR_CANDIDATES}). Last error: {last_exc}",
                cause=last_exc,
            )

        try:
            df = self._normalize_dataframe(df, symbol, timeframe)
        except MT5LoaderError:
            raise
        except Exception as exc:
            raise MT5LoaderError(
                f"Normalization failed for '{filepath}'.", cause=exc
            ) from exc

        if max_candles is not None and max_candles > 0:
            df = df.iloc[-max_candles:]

        self._logger.info(
            "Loaded CSV '%s': %d candles, columns=%s.",
            filename,
            len(df),
            list(df.columns),
        )
        return df

    def load_live(
        self,
        connection: Any,
        symbol: str,
        timeframe: str,
        count: int = 1000,
    ) -> pd.DataFrame:
        """Load candle data directly from a connected MetaTrader 5 terminal.

        Args:
            connection: An active MT5Connection instance.
            symbol: Trading instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "M1", "H4").
            count: Number of candles to fetch (most recent first).

        Returns:
            A normalized DataFrame with OHLCV data.

        Raises:
            MT5LoaderError: If MT5 is not available, the timeframe is unknown,
                or the MT5 API call fails.
        """
        if not MT5_AVAILABLE:
            raise MT5LoaderError(
                "MetaTrader5 package not available. "
                "Live loading requires Windows with MT5 installed."
            )

        tf_upper = timeframe.upper()
        if tf_upper not in MT5_TIMEFRAME_MAP:
            raise MT5LoaderError(
                f"Unknown timeframe '{timeframe}'. "
                f"Supported: {list(MT5_TIMEFRAME_MAP.keys())}."
            )

        tf_const = MT5_TIMEFRAME_MAP[tf_upper]

        try:
            rates = mt5.copy_rates_from_pos(  # type: ignore[union-attr]
                symbol.upper(), tf_const, 0, count
            )
        except Exception as exc:
            raise MT5LoaderError(
                f"mt5.copy_rates_from_pos failed for {symbol} {timeframe}.",
                cause=exc,
            ) from exc

        if rates is None or len(rates) == 0:
            last_err = mt5.last_error() if MT5_AVAILABLE else "N/A"  # type: ignore[union-attr]
            raise MT5LoaderError(
                f"No data returned for {symbol} {timeframe}. "
                f"MT5 last error: {last_err}."
            )

        try:
            df = pd.DataFrame(rates)
        except Exception as exc:
            raise MT5LoaderError(
                f"Failed to convert MT5 rates to DataFrame for {symbol} {timeframe}.",
                cause=exc,
            ) from exc

        try:
            df = self._normalize_dataframe(df, symbol, timeframe)
        except MT5LoaderError:
            raise
        except Exception as exc:
            raise MT5LoaderError(
                f"Normalization failed for live data {symbol} {timeframe}.",
                cause=exc,
            ) from exc

        self._logger.info(
            "Loaded live '%s %s': %d candles.",
            symbol.upper(),
            timeframe.upper(),
            len(df),
        )
        return df

    def load(
        self,
        symbol: str,
        timeframe: str,
        connection: Optional[Any] = None,
        max_candles: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load candle data using the best available source.

        If a live connection is provided and MT5 is available, attempts live
        loading first and falls back to CSV on failure. Otherwise loads from CSV.

        This is the primary entry point for all engine consumers.

        Args:
            symbol: Trading instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "M1", "H4").
            connection: Optional active MT5Connection for live data loading.
            max_candles: If set, return only the last N candles (CSV mode only).

        Returns:
            A normalized DataFrame with OHLCV data.

        Raises:
            MT5LoaderError: If all available loading methods fail.
        """
        if connection is not None and MT5_AVAILABLE:
            try:
                count = max_candles if max_candles is not None else 1000
                return self.load_live(connection, symbol, timeframe, count=count)
            except MT5LoaderError as exc:
                self._logger.warning(
                    "Live load failed for %s %s, falling back to CSV. Reason: %s",
                    symbol,
                    timeframe,
                    exc,
                )

        return self.load_csv(symbol, timeframe, max_candles=max_candles)

    def get_available_csv_files(self) -> list[dict[str, str]]:
        """Scan the data directory and return metadata for all valid CSV files.

        Parses filenames matching the pattern `{SYMBOL}_{TIMEFRAME}.csv`.
        Files that do not match the pattern are silently skipped.

        Returns:
            A list of dicts, each with keys: "symbol", "timeframe", "path".
            Returns an empty list if the data directory does not exist.
        """
        if not self._data_dir.exists():
            self._logger.warning(
                "Data directory '%s' does not exist.", self._data_dir
            )
            return []

        results: list[dict[str, str]] = []

        for csv_path in sorted(self._data_dir.glob("*.csv")):
            stem = csv_path.stem  # e.g. "XAUUSD_M1"
            parts = stem.split("_", maxsplit=1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                self._logger.debug(
                    "Skipping '%s' — does not match SYMBOL_TIMEFRAME pattern.",
                    csv_path.name,
                )
                continue

            results.append({
                "symbol": parts[0].upper(),
                "timeframe": parts[1].upper(),
                "path": str(csv_path.resolve()),
            })

        self._logger.debug(
            "Found %d valid CSV file(s) in '%s'.", len(results), self._data_dir
        )
        return results

    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pd.DataFrame:
        """Normalize a raw DataFrame into the standard engine-ready format.

        Handles:
        - Column name normalization (lowercase, strip, underscores)
        - MT5 split Date+Time column merging into a single "time" column
        - DateTime parsing and UTC-aware indexing
        - Deduplication and ascending sort
        - Type enforcement for OHLCV columns
        - Invalid row removal (NaN prices, zero prices, inverted high/low)

        Args:
            df: Raw DataFrame as loaded from CSV or MT5 API.
            symbol: Symbol name used for log messages.
            timeframe: Timeframe string used for log messages.

        Returns:
            Cleaned, normalized DataFrame with DatetimeIndex named "time".

        Raises:
            MT5LoaderError: If required OHLCV columns are missing after normalization.
        """
        label = f"{symbol.upper()} {timeframe.upper()}"

        # ── 1. Normalize column names ──────────────────────────────────────
        df = df.copy()
        df.columns = [
            str(c).strip().lower().replace(" ", "_") for c in df.columns
        ]

        # ── 2. Handle split Date + Time columns ───────────────────────────
        # MT5 sometimes exports: <DATE>  <TIME>  <OPEN>  ...
        # After normalization these become: <date> <time> or date time
        date_col: Optional[str] = None
        time_col: Optional[str] = None

        for col in df.columns:
            if col in ("date", "<date>"):
                date_col = col
            if col in ("time", "<time>") and "date" in (date_col or ""):
                # only treat "time" as the time-part if there's also a date col
                time_col = col

        # Determine if we have split columns
        has_split = (
            date_col is not None
            and time_col is not None
            and date_col != time_col
        )

        if has_split:
            df["time"] = pd.to_datetime(
                df[date_col].astype(str) + " " + df[time_col].astype(str),
                utc=True,
                errors="coerce",
            )
            df = df.drop(columns=[date_col, time_col], errors="ignore")
        elif "time" in df.columns:
            # Single time column — may be unix timestamp (int) or datetime string
            raw_time = df["time"]
            if pd.api.types.is_numeric_dtype(raw_time):
                df["time"] = pd.to_datetime(raw_time, unit="s", utc=True, errors="coerce")
            else:
                df["time"] = pd.to_datetime(raw_time, utc=True, errors="coerce")
        else:
            # Try to use the index if it looks like datetime
            try:
                df["time"] = pd.to_datetime(df.index, utc=True, errors="coerce")
            except Exception:
                raise MT5LoaderError(
                    f"Cannot find or parse a 'time' column in {label}. "
                    f"Available columns: {list(df.columns)}."
                )

        # ── 3. Set DatetimeIndex ───────────────────────────────────────────
        df = df.set_index("time")
        df.index.name = "time"
        df = df.sort_index(ascending=True)
        df = df[~df.index.duplicated(keep="last")]

        # ── 4. Check required columns ──────────────────────────────────────
        missing = [col for col in STANDARD_COLUMNS if col not in df.columns]
        if missing:
            raise MT5LoaderError(
                f"Missing required columns in {label}: {missing}. "
                f"Available columns: {list(df.columns)}."
            )

        # ── 5. Type conversion ─────────────────────────────────────────────
        price_cols = ("open", "high", "low", "close")
        for col in price_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

        df["tick_volume"] = (
            pd.to_numeric(df["tick_volume"], errors="coerce")
            .fillna(0)
            .astype("int64")
        )

        # ── 6. Drop invalid candles ────────────────────────────────────────
        initial_len = len(df)

        # NaN in any price column
        nan_mask = df[list(price_cols)].isna().any(axis=1)
        if nan_mask.sum() > 0:
            self._logger.warning(
                "%s: Dropping %d row(s) with NaN price values.",
                label,
                nan_mask.sum(),
            )
            df = df[~nan_mask]

        # Zero or negative prices
        non_positive_mask = (df[list(price_cols)] <= _MIN_PRICE_VALUE).any(axis=1)
        if non_positive_mask.sum() > 0:
            self._logger.warning(
                "%s: Dropping %d row(s) with zero or negative prices.",
                label,
                non_positive_mask.sum(),
            )
            df = df[~non_positive_mask]

        # Inverted high/low
        inverted_mask = df["high"] < df["low"]
        if inverted_mask.sum() > 0:
            self._logger.warning(
                "%s: Dropping %d row(s) where high < low (invalid candles).",
                label,
                inverted_mask.sum(),
            )
            df = df[~inverted_mask]

        dropped_total = initial_len - len(df)
        if dropped_total > 0:
            self._logger.warning(
                "%s: Total rows dropped during normalization: %d (kept %d).",
                label,
                dropped_total,
                len(df),
            )

        return df


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_loader(data_dir: str = "data") -> MT5Loader:
    """Factory function — creates and returns a configured MT5Loader.

    Args:
        data_dir: Path to the directory containing MT5-exported CSV files.

    Returns:
        A ready-to-use MT5Loader instance.

    Example:
        loader = create_loader(data_dir="data")
        df = loader.load("EURUSD", "H1", max_candles=200)
    """
    return MT5Loader(data_dir=data_dir)