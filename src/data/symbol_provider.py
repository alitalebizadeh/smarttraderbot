from __future__ import annotations

import logging
from typing import Any, Optional

from src.models.scan_result import SymbolTimeframePair

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

__all__ = [
    "SymbolProvider",
    "SymbolProviderError",
    "create_provider",
    "create_single_pair_provider",
    "DEFAULT_SYMBOLS",
    "DEFAULT_TIMEFRAMES",
    "VALID_TIMEFRAMES",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY",
    "USDCAD", "AUDUSD", "NZDUSD", "USDCHF",
    "US30", "USOIL",
)

DEFAULT_TIMEFRAMES: tuple[str, ...] = (
    "M1", "M5", "M15", "M30", "H1", "H4", "D1"
)

VALID_TIMEFRAMES: frozenset[str] = frozenset({
    "M1", "M5", "M15", "M30",
    "H1", "H4",
    "D1", "W1", "MN1",
})


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class SymbolProviderError(Exception):
    """Raised when symbol or timeframe validation or MT5 lookup fails.

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
#  SymbolProvider
# ─────────────────────────────────────────────

class SymbolProvider:
    """Single source of truth for which symbols and timeframes to scan.

    Manages the list of trading instruments and chart timeframes that the
    scanner will process. Supports optional validation against a live MT5
    terminal to ensure all requested symbols are actually available.

    Example:
        provider = SymbolProvider(
            symbols=["XAUUSD", "EURUSD"],
            timeframes=["M1", "H1"],
        )
        for pair in provider.get_pairs():
            print(pair.display_name)
    """

    def __init__(
        self,
        symbols: Optional[list[str]] = None,
        timeframes: Optional[list[str]] = None,
    ) -> None:
        """Initialize the provider with symbols and timeframes to scan.

        Args:
            symbols: List of instrument symbols to scan. Defaults to
                DEFAULT_SYMBOLS when None.
            timeframes: List of timeframe strings to scan. Defaults to
                DEFAULT_TIMEFRAMES when None. Each must be in VALID_TIMEFRAMES.

        Raises:
            SymbolProviderError: If any timeframe string is not in VALID_TIMEFRAMES.
        """
        self._logger = logging.getLogger(__name__)

        raw_symbols: tuple[str, ...] | list[str] = (
            symbols if symbols is not None else DEFAULT_SYMBOLS
        )
        raw_timeframes: tuple[str, ...] | list[str] = (
            timeframes if timeframes is not None else DEFAULT_TIMEFRAMES
        )

        normalized_timeframes = [tf.upper() for tf in raw_timeframes]
        invalid_tfs = [
            tf for tf in normalized_timeframes if tf not in VALID_TIMEFRAMES
        ]
        if invalid_tfs:
            raise SymbolProviderError(
                f"Invalid timeframe(s): {invalid_tfs}. "
                f"Valid options are: {sorted(VALID_TIMEFRAMES)}."
            )

        self._symbols: list[str] = [s.upper() for s in raw_symbols]
        self._timeframes: list[str] = normalized_timeframes

    # ── Read ──────────────────────────────────────────────────────────────

    def get_pairs(self) -> list[SymbolTimeframePair]:
        """Return all symbol × timeframe combinations as SymbolTimeframePair objects.

        The outer loop iterates over symbols and the inner loop over timeframes,
        so all timeframes for a given symbol appear consecutively.

        Returns:
            Ordered list of SymbolTimeframePair instances. Length equals
            len(symbols) × len(timeframes).
        """
        return [
            SymbolTimeframePair(
                symbol=symbol,
                timeframe=tf,
                display_name=f"{symbol} {tf}",
            )
            for symbol in self._symbols
            for tf in self._timeframes
        ]

    def get_symbols(self) -> list[str]:
        """Return a copy of the current symbols list.

        Returns:
            List of uppercase symbol strings.
        """
        return list(self._symbols)

    def get_timeframes(self) -> list[str]:
        """Return a copy of the current timeframes list.

        Returns:
            List of uppercase timeframe strings.
        """
        return list(self._timeframes)

    def get_pair_count(self) -> int:
        """Return the total number of symbol × timeframe pairs.

        Returns:
            len(symbols) * len(timeframes).
        """
        return len(self._symbols) * len(self._timeframes)

    # ── MT5 Validation ────────────────────────────────────────────────────

    def validate_against_mt5(
        self, connection: Any
    ) -> tuple[list[str], list[str]]:
        """Check which symbols are available in the connected MT5 terminal.

        Args:
            connection: An active MT5Connection instance.

        Returns:
            A tuple (valid_symbols, invalid_symbols) where valid_symbols are
            recognised by MT5 and invalid_symbols are not.

        Raises:
            SymbolProviderError: If MT5 is available but the connection is
                not active.
        """
        if not MT5_AVAILABLE:
            self._logger.warning(
                "MT5 package not available — skipping MT5 symbol validation. "
                "All %d symbol(s) treated as valid.",
                len(self._symbols),
            )
            return (list(self._symbols), [])

        if not connection.is_connected():
            raise SymbolProviderError(
                "MT5 not connected. Call connection.connect() before validating symbols."
            )

        valid_symbols: list[str] = []
        invalid_symbols: list[str] = []

        for symbol in self._symbols:
            try:
                info = mt5.symbol_info(symbol)  # type: ignore[union-attr]
            except Exception as exc:
                self._logger.warning(
                    "mt5.symbol_info('%s') raised an exception: %s — treating as invalid.",
                    symbol,
                    exc,
                )
                invalid_symbols.append(symbol)
                continue

            if info is not None:
                valid_symbols.append(symbol)
            else:
                self._logger.warning(
                    "Symbol '%s' not found in MT5 terminal — it will be skipped.",
                    symbol,
                )
                invalid_symbols.append(symbol)

        self._logger.info(
            "MT5 symbol validation complete: %d valid, %d invalid out of %d total.",
            len(valid_symbols),
            len(invalid_symbols),
            len(self._symbols),
        )
        return (valid_symbols, invalid_symbols)

    def filter_to_valid_mt5_symbols(self, connection: Any) -> SymbolProvider:
        """Return a new SymbolProvider containing only MT5-recognised symbols.

        Does not mutate this instance.

        Args:
            connection: An active MT5Connection instance.

        Returns:
            A new SymbolProvider with invalid symbols removed and the same
            timeframes as this instance.

        Raises:
            SymbolProviderError: If MT5 is available but the connection is
                not active.
        """
        valid_symbols, _ = self.validate_against_mt5(connection)
        return SymbolProvider(
            symbols=valid_symbols,
            timeframes=list(self._timeframes),
        )

    # ── Mutation ──────────────────────────────────────────────────────────

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol to the scan list if not already present.

        Args:
            symbol: Instrument symbol to add (case-insensitive).
        """
        upper = symbol.upper()
        if upper not in self._symbols:
            self._symbols.append(upper)
            self._logger.info("Added symbol '%s'. Total symbols: %d.", upper, len(self._symbols))
        else:
            self._logger.info("Symbol '%s' already present — skipping.", upper)

    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from the scan list if present.

        Args:
            symbol: Instrument symbol to remove (case-insensitive).
        """
        upper = symbol.upper()
        if upper in self._symbols:
            self._symbols.remove(upper)
            self._logger.info(
                "Removed symbol '%s'. Total symbols: %d.", upper, len(self._symbols)
            )
        else:
            self._logger.info("Symbol '%s' not found — nothing removed.", upper)

    def add_timeframe(self, timeframe: str) -> None:
        """Add a timeframe to the scan list if not already present.

        Args:
            timeframe: Timeframe string to add (case-insensitive).

        Raises:
            SymbolProviderError: If the timeframe is not in VALID_TIMEFRAMES.
        """
        upper = timeframe.upper()
        if upper not in VALID_TIMEFRAMES:
            raise SymbolProviderError(
                f"Invalid timeframe '{timeframe}'. "
                f"Valid options are: {sorted(VALID_TIMEFRAMES)}."
            )
        if upper not in self._timeframes:
            self._timeframes.append(upper)
            self._logger.info(
                "Added timeframe '%s'. Total timeframes: %d.", upper, len(self._timeframes)
            )
        else:
            self._logger.info("Timeframe '%s' already present — skipping.", upper)

    def remove_timeframe(self, timeframe: str) -> None:
        """Remove a timeframe from the scan list if present.

        Args:
            timeframe: Timeframe string to remove (case-insensitive).
        """
        upper = timeframe.upper()
        if upper in self._timeframes:
            self._timeframes.remove(upper)
            self._logger.info(
                "Removed timeframe '%s'. Total timeframes: %d.", upper, len(self._timeframes)
            )
        else:
            self._logger.info("Timeframe '%s' not found — nothing removed.", upper)

    # ── Dunder ────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        """Return a developer-friendly string representation.

        Returns:
            String showing symbol count, timeframe count, and total pair count.
        """
        return (
            f"SymbolProvider("
            f"symbols={len(self._symbols)}, "
            f"timeframes={len(self._timeframes)}, "
            f"pairs={self.get_pair_count()})"
        )


# ─────────────────────────────────────────────
#  Factory Functions
# ─────────────────────────────────────────────

def create_provider(
    symbols: Optional[list[str]] = None,
    timeframes: Optional[list[str]] = None,
) -> SymbolProvider:
    """Factory function — create and return a configured SymbolProvider.

    Args:
        symbols: List of instrument symbols to scan. Defaults to DEFAULT_SYMBOLS.
        timeframes: List of timeframe strings to scan. Defaults to DEFAULT_TIMEFRAMES.

    Returns:
        A ready-to-use SymbolProvider instance.

    Raises:
        SymbolProviderError: If any timeframe is not in VALID_TIMEFRAMES.
    """
    return SymbolProvider(symbols=symbols, timeframes=timeframes)


def create_single_pair_provider(
    symbol: str,
    timeframe: str,
) -> SymbolProvider:
    """Factory function — create a SymbolProvider for exactly one symbol/timeframe pair.

    Useful for targeted scans, debugging, and unit testing.

    Args:
        symbol: Instrument symbol (e.g. "XAUUSD").
        timeframe: Chart timeframe string (e.g. "M1").

    Returns:
        A SymbolProvider that produces exactly one SymbolTimeframePair.

    Raises:
        SymbolProviderError: If the timeframe is not in VALID_TIMEFRAMES.
    """
    return SymbolProvider(symbols=[symbol], timeframes=[timeframe])