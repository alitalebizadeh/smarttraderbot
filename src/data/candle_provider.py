from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from src.data.mt5_loader import MT5Loader, MT5LoaderError

__all__ = [
    "CandleProvider",
    "CandleProviderError",
    "create_provider",
    "DEFAULT_MAX_CANDLES",
    "DEFAULT_CACHE_TTL_SEC",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_MAX_CANDLES: int = 1000
DEFAULT_CACHE_TTL_SEC: float = 60.0
MAX_CACHE_ENTRIES: int = 200


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class CandleProviderError(Exception):
    """Raised when candle data cannot be loaded or retrieved from cache.

    Attributes:
        message: Human-readable description of the failure.
        cause: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        """Initialize with a message and optional root cause.

        Args:
            message: Description of the failure.
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
#  Internal Cache Entry (private)
# ─────────────────────────────────────────────

@dataclass
class _CacheEntry:
    """Internal dataclass holding one cached DataFrame and its metadata.

    Attributes:
        df: The cached OHLCV DataFrame.
        loaded_at: Monotonic timestamp (time.monotonic()) when entry was cached.
        symbol: Instrument symbol this entry belongs to.
        timeframe: Timeframe this entry belongs to.
    """

    df: pd.DataFrame
    loaded_at: float
    symbol: str
    timeframe: str


# ─────────────────────────────────────────────
#  CandleProvider
# ─────────────────────────────────────────────

class CandleProvider:
    """High-level candle data access layer with in-memory caching.

    Wraps MT5Loader to provide a clean, engine-facing interface for loading
    OHLCV DataFrames. Engines should never call MT5Loader directly — all
    data access goes through this class.

    Features:
    - TTL-based in-memory cache (avoids redundant disk/network reads)
    - Thread-safe cache access via threading.Lock
    - LRU-style eviction when the cache reaches MAX_CACHE_ENTRIES
    - Multi-timeframe loading with partial-failure tolerance
    - Preloading for warm-up before a scan cycle

    Example:
        provider = create_provider(data_dir="data", max_candles=500)
        df = provider.get_candles("XAUUSD", "H1")
        dfs = provider.get_candles_multi("XAUUSD", ["M1", "H1", "H4"])
    """

    def __init__(
        self,
        loader: MT5Loader,
        connection: Optional[Any] = None,
        max_candles: int | None = DEFAULT_MAX_CANDLES,
        cache_ttl_sec: float = DEFAULT_CACHE_TTL_SEC,
    ) -> None:
        """Initialize the CandleProvider.

        Args:
            loader: Configured MT5Loader instance for low-level data loading.
            connection: Optional active MT5Connection for live data mode.
            max_candles: Maximum number of candles to load per request.
            cache_ttl_sec: Seconds before a cache entry is considered stale.
        """
        self._loader = loader
        self._connection = connection
        self._max_candles = max_candles
        self._cache_ttl_sec = cache_ttl_sec
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)

    # ── Cache helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(symbol: str, timeframe: str) -> str:
        """Build a normalized cache key from symbol and timeframe.

        Args:
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            Uppercase cache key string.
        """
        return f"{symbol.upper()}_{timeframe.upper()}"

    def _is_expired(self, entry: _CacheEntry) -> bool:
        """Check whether a cache entry has exceeded its TTL.

        Args:
            entry: The cache entry to check.

        Returns:
            True if the entry is older than cache_ttl_sec.
        """
        return (time.monotonic() - entry.loaded_at) > self._cache_ttl_sec

    def _evict_oldest(self) -> None:
        """Remove the oldest cache entry when the cache is full.

        Must be called while holding self._lock.
        """
        if not self._cache:
            return
        oldest_key = min(self._cache, key=lambda k: self._cache[k].loaded_at)
        evicted = self._cache.pop(oldest_key)
        self._logger.debug(
            "Cache full (%d entries) — evicted oldest entry: '%s'.",
            MAX_CACHE_ENTRIES,
            oldest_key,
        )
        _ = evicted  # suppress unused-variable warning

    # ── Primary Interface ─────────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        force_reload: bool = False,
    ) -> pd.DataFrame:
        """Load and return OHLCV candles for one symbol/timeframe pair.

        Returns cached data if available and not expired, unless force_reload
        is True. On cache miss, loads from MT5Loader and stores the result.

        Args:
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "M1", "H4").
            force_reload: If True, bypass the cache and reload from source.

        Returns:
            Normalized OHLCV DataFrame with DatetimeIndex.

        Raises:
            CandleProviderError: If loading fails for any reason.
        """
        key = self._cache_key(symbol, timeframe)

        with self._lock:
            if not force_reload and key in self._cache:
                entry = self._cache[key]
                if not self._is_expired(entry):
                    self._logger.debug(
                        "Cache hit for '%s' — returning %d cached candles.",
                        key,
                        len(entry.df),
                    )
                    return entry.df.copy()
                else:
                    self._logger.debug("Cache entry '%s' expired — reloading.", key)

            # Load from source
            try:
                load_count = self._max_candles if self._max_candles and self._max_candles > 0 else None
                df = self._loader.load(
                    symbol=symbol,
                    timeframe=timeframe,
                    connection=self._connection,
                    max_candles=load_count,
                )
            except MT5LoaderError as exc:
                raise CandleProviderError(
                    f"Failed to load candles for {symbol} {timeframe}.", cause=exc
                ) from exc
            except Exception as exc:
                raise CandleProviderError(
                    f"Unexpected error loading candles for {symbol} {timeframe}.",
                    cause=exc,
                ) from exc

            # Evict oldest if at capacity
            if len(self._cache) >= MAX_CACHE_ENTRIES:
                self._evict_oldest()

            self._cache[key] = _CacheEntry(
                df=df.copy(),
                loaded_at=time.monotonic(),
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
            )
            self._logger.debug(
                "Cached '%s' — %d candles. Cache size: %d/%d.",
                key,
                len(df),
                len(self._cache),
                MAX_CACHE_ENTRIES,
            )
            return df

    def get_candles_multi(
        self,
        symbol: str,
        timeframes: list[str],
        force_reload: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Load OHLCV candles for one symbol across multiple timeframes.

        Tolerates partial failures — if one timeframe fails, it is skipped
        and a warning is logged. The returned dict contains only successful
        results.

        Args:
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframes: List of timeframe strings to load.
            force_reload: If True, bypass the cache for all timeframes.

        Returns:
            Dict mapping timeframe string to its normalized DataFrame.
            Keys are uppercase timeframe strings (e.g. {"M1": df, "H1": df}).
        """
        results: dict[str, pd.DataFrame] = {}
        for tf in timeframes:
            try:
                df = self.get_candles(symbol, tf, force_reload=force_reload)
                results[tf.upper()] = df
            except CandleProviderError as exc:
                self._logger.warning(
                    "Skipping timeframe '%s' for '%s' due to load failure: %s",
                    tf,
                    symbol,
                    exc,
                )
        return results

    def get_latest_price(
        self,
        symbol: str,
        timeframe: str = "M1",
    ) -> Optional[float]:
        """Return the most recent close price for a symbol.

        Args:
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframe: Timeframe to use for the price lookup. Defaults to "M1".

        Returns:
            Latest close price as a float, or None if loading fails.
        """
        try:
            df = self.get_candles(symbol, timeframe)
            if df.empty or "close" not in df.columns:
                return None
            return float(df["close"].iloc[-1])
        except Exception as exc:
            self._logger.warning(
                "Could not retrieve latest price for '%s %s': %s",
                symbol,
                timeframe,
                exc,
            )
            return None

    # ── Cache Management ──────────────────────────────────────────────────

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a specific entry from the cache.

        No-op if the entry is not currently cached.

        Args:
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.
        """
        key = self._cache_key(symbol, timeframe)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._logger.debug("Invalidated cache entry '%s'.", key)

    def invalidate_all(self) -> None:
        """Clear all entries from the cache.

        Logs the number of entries removed.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
        self._logger.info("Cache cleared — removed %d entry/entries.", count)

    def get_cache_stats(self) -> dict[str, Any]:
        """Return a summary of the current cache state.

        Returns:
            A dict with:
            - "total_entries": number of cached entries
            - "entries": list of dicts with symbol, timeframe, age_sec
            - "max_entries": MAX_CACHE_ENTRIES constant
            - "ttl_sec": configured cache TTL in seconds
        """
        now = time.monotonic()
        with self._lock:
            entries = [
                {
                    "symbol": entry.symbol,
                    "timeframe": entry.timeframe,
                    "age_sec": round(now - entry.loaded_at, 2),
                }
                for entry in self._cache.values()
            ]
            total = len(self._cache)

        return {
            "total_entries": total,
            "entries": entries,
            "max_entries": MAX_CACHE_ENTRIES,
            "ttl_sec": self._cache_ttl_sec,
        }

    def is_cached(self, symbol: str, timeframe: str) -> bool:
        """Check whether a valid (non-expired) cache entry exists.

        Args:
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            True if the entry is cached and has not expired.
        """
        key = self._cache_key(symbol, timeframe)
        with self._lock:
            if key not in self._cache:
                return False
            return not self._is_expired(self._cache[key])

    def preload(self, pairs: list[Any]) -> dict[str, bool]:
        """Preload candle data for a list of SymbolTimeframePair objects.

        Useful for warming the cache before a scan cycle starts.
        Failures are recorded as False in the result dict but do not raise.

        Args:
            pairs: List of SymbolTimeframePair objects with .symbol,
                .timeframe, and .display_name attributes.

        Returns:
            Dict mapping display_name to True (loaded) or False (failed).
        """
        results: dict[str, bool] = {}
        total = len(pairs)

        for idx, pair in enumerate(pairs, start=1):
            display = pair.display_name
            self._logger.info(
                "Preloading %d/%d: %s ...", idx, total, display
            )
            try:
                self.get_candles(pair.symbol, pair.timeframe)
                results[display] = True
                self._logger.debug("Preloaded '%s' successfully.", display)
            except Exception as exc:
                self._logger.warning(
                    "Preload failed for '%s': %s", display, exc
                )
                results[display] = False

        successful = sum(v for v in results.values())
        self._logger.info(
            "Preload complete: %d/%d pair(s) loaded successfully.",
            successful,
            total,
        )
        return results

    # ── Dunder ────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        """Return a developer-friendly string representation.

        Returns:
            String showing cache usage and configuration.
        """
        with self._lock:
            cached = len(self._cache)
        return (
            f"CandleProvider("
            f"cached={cached}, "
            f"max={MAX_CACHE_ENTRIES}, "
            f"ttl={self._cache_ttl_sec}s)"
        )


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_provider(
    data_dir: str = "data",
    connection: Optional[Any] = None,
    max_candles: int = DEFAULT_MAX_CANDLES,
    cache_ttl_sec: float = DEFAULT_CACHE_TTL_SEC,
) -> CandleProvider:
    """Factory function — create an MT5Loader and wrap it in a CandleProvider.

    Args:
        data_dir: Directory containing MT5-exported CSV files.
        connection: Optional active MT5Connection for live data mode.
        max_candles: Maximum number of candles to load per request.
        cache_ttl_sec: Seconds before a cached entry is considered stale.

    Returns:
        A fully configured, ready-to-use CandleProvider instance.

    Example:
        provider = create_provider(data_dir="data", max_candles=500)
        df = provider.get_candles("EURUSD", "H4")
    """
    loader = MT5Loader(data_dir=data_dir)
    return CandleProvider(
        loader=loader,
        connection=connection,
        max_candles=max_candles,
        cache_ttl_sec=cache_ttl_sec,
    )