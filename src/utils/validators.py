from __future__ import annotations

import math
import re
from typing import Union

import pandas as pd

__all__ = [
    # Constants
    "VALID_TIMEFRAMES",
    # Timeframe
    "is_valid_timeframe",
    "normalize_timeframe",
    # Symbol
    "is_valid_symbol",
    "normalize_symbol",
    # Price
    "is_valid_price",
    "is_valid_price_range",
    "clamp_price",
    # Score
    "is_valid_score",
    "clamp_score",
    # DataFrame
    "is_valid_ohlcv",
    "has_required_columns",
    "get_missing_columns",
    # Config
    "is_valid_interval_seconds",
    "is_positive_int",
    "is_non_empty_string",
    # Batch
    "validate_symbols",
    "validate_timeframes",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

VALID_TIMEFRAMES: frozenset[str] = frozenset(
    {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN", "MN1"}
)

_OHLCV_REQUIRED: list[str] = ["open", "high", "low", "close"]

# Symbol: alphanumeric, dots, underscores; length 2–20
_SYMBOL_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._]{2,20}$")

_SCORE_MIN: float = 0.0
_SCORE_MAX: float = 100.0
_INTERVAL_MIN: float = 1.0


# ─────────────────────────────────────────────
#  Timeframe Validation
# ─────────────────────────────────────────────

def is_valid_timeframe(timeframe: str) -> bool:
    """Return True if the timeframe string is a recognized trading timeframe.

    Validation is case-sensitive — "M1" is valid, "m1" is not.
    Returns False for non-string, None, or empty input.

    Args:
        timeframe: Timeframe string to validate (e.g. "M1", "H4", "D1").

    Returns:
        True if timeframe is in VALID_TIMEFRAMES, False otherwise.
    """
    try:
        return isinstance(timeframe, str) and timeframe in VALID_TIMEFRAMES
    except Exception:
        return False


def normalize_timeframe(timeframe: str) -> str:
    """Strip whitespace and uppercase a timeframe string.

    Args:
        timeframe: Raw timeframe string (e.g. "  h4  ").

    Returns:
        Normalized string (e.g. "H4").
        Returns "" for non-string or empty input — never raises.
    """
    try:
        if not isinstance(timeframe, str):
            return ""
        return timeframe.strip().upper()
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  Symbol Validation
# ─────────────────────────────────────────────

def is_valid_symbol(symbol: str) -> bool:
    """Return True if the symbol is a valid trading instrument identifier.

    A valid symbol:
    - Is a non-empty string
    - Contains only alphanumeric characters, dots, or underscores
    - Has a length between 2 and 20 characters (inclusive)

    Args:
        symbol: Instrument symbol to validate (e.g. "XAUUSD", "EUR.USD").

    Returns:
        True if the symbol passes all validation rules, False otherwise.
        Never raises.
    """
    try:
        if not isinstance(symbol, str) or not symbol:
            return False
        return bool(_SYMBOL_PATTERN.match(symbol))
    except Exception:
        return False


def normalize_symbol(symbol: str) -> str:
    """Strip whitespace and uppercase a symbol string.

    Args:
        symbol: Raw symbol string (e.g. "  xauusd  ").

    Returns:
        Normalized string (e.g. "XAUUSD").
        Returns "" for non-string or empty input — never raises.
    """
    try:
        if not isinstance(symbol, str):
            return ""
        return symbol.strip().upper()
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  Price Validation
# ─────────────────────────────────────────────

def is_valid_price(price: Union[float, int]) -> bool:
    """Return True if the price is a positive, finite number.

    Rejects zero, negative values, NaN, infinity, and non-numeric types.

    Args:
        price: Price value to validate.

    Returns:
        True if price > 0 and is finite, False otherwise. Never raises.
    """
    try:
        p = float(price)
        return p > 0.0 and math.isfinite(p)
    except Exception:
        return False


def is_valid_price_range(low: float, high: float) -> bool:
    """Return True if low and high form a valid price range.

    Both values must be positive and finite, and high must be >= low.

    Args:
        low: Lower bound of the price range.
        high: Upper bound of the price range.

    Returns:
        True if low > 0 and high > 0 and high >= low, False otherwise.
        Never raises.
    """
    try:
        lo = float(low)
        hi = float(high)
        return (
            lo > 0.0
            and hi > 0.0
            and math.isfinite(lo)
            and math.isfinite(hi)
            and hi >= lo
        )
    except Exception:
        return False


def clamp_price(price: float, min_price: float, max_price: float) -> float:
    """Clamp a price value to the inclusive range [min_price, max_price].

    Args:
        price: Price value to clamp.
        min_price: Lower bound of the acceptable range.
        max_price: Upper bound of the acceptable range.

    Returns:
        price clamped to [min_price, max_price].
        Returns min_price if price is NaN, infinite, or non-numeric.
        Never raises.
    """
    try:
        p = float(price)
        if not math.isfinite(p):
            return float(min_price)
        return max(float(min_price), min(p, float(max_price)))
    except Exception:
        try:
            return float(min_price)
        except Exception:
            return 0.0


# ─────────────────────────────────────────────
#  Score Validation
# ─────────────────────────────────────────────

def is_valid_score(score: float) -> bool:
    """Return True if the score is a finite number in the range [0.0, 100.0].

    Args:
        score: Confluence score to validate.

    Returns:
        True if 0.0 <= score <= 100.0 and score is finite, False otherwise.
        Never raises.
    """
    try:
        s = float(score)
        return math.isfinite(s) and _SCORE_MIN <= s <= _SCORE_MAX
    except Exception:
        return False


def clamp_score(score: float) -> float:
    """Clamp a score value to the inclusive range [0.0, 100.0].

    Args:
        score: Raw score value to clamp.

    Returns:
        Score clamped to [0.0, 100.0].
        Returns 0.0 if score is NaN, infinite, or non-numeric.
        Never raises.
    """
    try:
        s = float(score)
        if not math.isfinite(s):
            return _SCORE_MIN
        return max(_SCORE_MIN, min(s, _SCORE_MAX))
    except Exception:
        return _SCORE_MIN


# ─────────────────────────────────────────────
#  DataFrame Validation
# ─────────────────────────────────────────────

def is_valid_ohlcv(df: pd.DataFrame, min_rows: int = 50) -> bool:
    """Return True if the DataFrame is a valid OHLCV candle dataset.

    Validation criteria:
    - df is a non-None pandas DataFrame
    - Has at least min_rows rows
    - Contains all columns: open, high, low, close
    - None of the required columns are entirely NaN

    Args:
        df: DataFrame to validate.
        min_rows: Minimum number of rows required. Defaults to 50.

    Returns:
        True if all criteria are satisfied, False otherwise. Never raises.
    """
    try:
        if not isinstance(df, pd.DataFrame) or df is None:
            return False
        if len(df) < min_rows:
            return False
        for col in _OHLCV_REQUIRED:
            if col not in df.columns:
                return False
            if df[col].isna().all():
                return False
        return True
    except Exception:
        return False


def has_required_columns(df: pd.DataFrame, columns: list[str]) -> bool:
    """Return True if the DataFrame contains all specified column names.

    Args:
        df: DataFrame to inspect.
        columns: List of column names that must all be present.

    Returns:
        True if df is a DataFrame and all columns are present.
        False otherwise. Never raises.
    """
    try:
        if not isinstance(df, pd.DataFrame):
            return False
        return all(col in df.columns for col in columns)
    except Exception:
        return False


def get_missing_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Return a list of column names that are absent from the DataFrame.

    Args:
        df: DataFrame to inspect.
        required: List of column names that should be present.

    Returns:
        List of column names from required that are not in df.
        Returns all of required if df is not a DataFrame.
        Returns [] if all columns are present.
        Never raises.
    """
    try:
        if not isinstance(df, pd.DataFrame):
            return list(required)
        return [col for col in required if col not in df.columns]
    except Exception:
        try:
            return list(required)
        except Exception:
            return []


# ─────────────────────────────────────────────
#  Config Validation
# ─────────────────────────────────────────────

def is_valid_interval_seconds(seconds: Union[int, float]) -> bool:
    """Return True if the value is a valid scan interval in seconds.

    A valid interval is a positive finite number >= 1.0.

    Args:
        seconds: Interval value in seconds to validate.

    Returns:
        True if seconds >= 1.0 and is finite, False otherwise. Never raises.
    """
    try:
        s = float(seconds)
        return math.isfinite(s) and s >= _INTERVAL_MIN
    except Exception:
        return False


def is_positive_int(value: int) -> bool:
    """Return True if the value is a strictly positive integer (not a bool).

    Booleans are excluded because bool is a subclass of int in Python and
    True / False are not meaningful as positive integer counts.

    Args:
        value: Value to validate.

    Returns:
        True if value is an int (not bool) and > 0, False otherwise.
        Never raises.
    """
    try:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    except Exception:
        return False


def is_non_empty_string(value: str) -> bool:
    """Return True if the value is a non-empty string after stripping whitespace.

    Args:
        value: Value to validate.

    Returns:
        True if value is a str and value.strip() is non-empty, False otherwise.
        Never raises.
    """
    try:
        return isinstance(value, str) and bool(value.strip())
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Batch Validation
# ─────────────────────────────────────────────

def validate_symbols(
    symbols: list[str],
) -> tuple[list[str], list[str]]:
    """Validate a list of symbol strings and separate valid from invalid.

    Each symbol is normalized (stripped and uppercased) before validation.

    Args:
        symbols: List of raw symbol strings to validate.

    Returns:
        Tuple of (valid_symbols, invalid_symbols), both normalized to uppercase.
        Never raises — returns ([], []) on any unexpected error.
    """
    valid: list[str] = []
    invalid: list[str] = []
    try:
        for raw in symbols:
            normalized = normalize_symbol(raw)
            if is_valid_symbol(normalized):
                valid.append(normalized)
            else:
                invalid.append(normalized if normalized else str(raw))
    except Exception:
        return [], []
    return valid, invalid


def validate_timeframes(
    timeframes: list[str],
) -> tuple[list[str], list[str]]:
    """Validate a list of timeframe strings and separate valid from invalid.

    Each timeframe is normalized (stripped and uppercased) before validation.

    Args:
        timeframes: List of raw timeframe strings to validate.

    Returns:
        Tuple of (valid_timeframes, invalid_timeframes), both normalized to uppercase.
        Never raises — returns ([], []) on any unexpected error.
    """
    valid: list[str] = []
    invalid: list[str] = []
    try:
        for raw in timeframes:
            normalized = normalize_timeframe(raw)
            if is_valid_timeframe(normalized):
                valid.append(normalized)
            else:
                invalid.append(normalized if normalized else str(raw))
    except Exception:
        return [], []
    return valid, invalid