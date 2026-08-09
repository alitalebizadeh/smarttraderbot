from __future__ import annotations

import math
from typing import Union

__all__ = [
    # Constants
    "PIP_SIZES",
    # Pip / Point
    "get_pip_size",
    "price_to_pips",
    "pips_to_price",
    "round_to_pip",
    # Range / Zone
    "calculate_range",
    "calculate_midpoint",
    "calculate_zone_size_pct",
    "is_price_in_zone",
    "price_distance_to_zone",
    # Premium / Discount
    "classify_premium_discount",
    "is_in_discount",
    "is_in_premium",
    # ATR
    "calculate_true_range",
    "calculate_atr",
    # Candle
    "candle_body_size",
    "candle_total_range",
    "candle_body_ratio",
    "is_bullish_candle",
    "is_bearish_candle",
    "is_doji",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

PIP_SIZES: dict[str, float] = {
    "JPY":     0.01,
    "XAU":     0.01,
    "XAG":     0.001,
    "US30":    1.0,
    "NAS":     1.0,
    "SPX":     0.1,
    "OIL":     0.01,
    "BTC":     1.0,
    "DEFAULT": 0.0001,
}

_DEFAULT_PIP: float = PIP_SIZES["DEFAULT"]
_EQUILIBRIUM_MID: float = 0.5


# ─────────────────────────────────────────────
#  Pip / Point Utilities
# ─────────────────────────────────────────────

def get_pip_size(symbol: str) -> float:
    """Return the pip size for a given trading instrument symbol.

    Checks whether any key in PIP_SIZES (except "DEFAULT") appears as a
    case-insensitive substring of the symbol. Returns the DEFAULT pip size
    (0.0001) when no match is found.

    Args:
        symbol: Trading instrument symbol (e.g. "XAUUSD", "USDJPY").

    Returns:
        Pip size as a float. Returns 0.0001 for unrecognized symbols.
        Never raises.
    """
    try:
        upper = symbol.upper()
        for key, size in PIP_SIZES.items():
            if key == "DEFAULT":
                continue
            if key in upper:
                return size
        return _DEFAULT_PIP
    except Exception:
        return _DEFAULT_PIP


def price_to_pips(price_diff: float, symbol: str) -> float:
    """Convert an absolute price difference to pips for the given symbol.

    Formula: abs(price_diff) / get_pip_size(symbol)

    Args:
        price_diff: Raw price difference (positive or negative).
        symbol: Trading instrument symbol used to determine pip size.

    Returns:
        Equivalent number of pips as a float. Returns 0.0 on any error.
        Never raises.
    """
    try:
        pip = get_pip_size(symbol)
        if pip == 0.0:
            return 0.0
        return abs(float(price_diff)) / pip
    except Exception:
        return 0.0


def pips_to_price(pips: float, symbol: str) -> float:
    """Convert a pip count to a price difference for the given symbol.

    Formula: pips * get_pip_size(symbol)

    Args:
        pips: Number of pips to convert.
        symbol: Trading instrument symbol used to determine pip size.

    Returns:
        Equivalent price difference as a float. Returns 0.0 on any error.
        Never raises.
    """
    try:
        return float(pips) * get_pip_size(symbol)
    except Exception:
        return 0.0


def round_to_pip(price: float, symbol: str) -> float:
    """Round a price to the nearest pip for the given symbol.

    Formula: round(price / pip_size) * pip_size

    Args:
        price: Raw price value to round.
        symbol: Trading instrument symbol used to determine pip size.

    Returns:
        Price rounded to the nearest pip. Returns price unchanged on any error.
        Never raises.
    """
    try:
        pip = get_pip_size(symbol)
        if pip == 0.0:
            return float(price)
        return round(float(price) / pip) * pip
    except Exception:
        try:
            return float(price)
        except Exception:
            return 0.0


# ─────────────────────────────────────────────
#  Range / Zone Math
# ─────────────────────────────────────────────

def calculate_range(high: float, low: float) -> float:
    """Calculate the price range between high and low.

    Args:
        high: Upper price boundary.
        low: Lower price boundary.

    Returns:
        high - low as a float. Returns 0.0 if high < low or on any error.
        Never raises.
    """
    try:
        h, lo = float(high), float(low)
        if h < lo:
            return 0.0
        return h - lo
    except Exception:
        return 0.0


def calculate_midpoint(high: float, low: float) -> float:
    """Calculate the midpoint between high and low prices.

    Args:
        high: Upper price boundary.
        low: Lower price boundary.

    Returns:
        (high + low) / 2 as a float. Returns 0.0 on any error. Never raises.
    """
    try:
        return (float(high) + float(low)) / 2.0
    except Exception:
        return 0.0


def calculate_zone_size_pct(
    zone_top: float,
    zone_bottom: float,
    price: float,
) -> float:
    """Calculate the zone height as a percentage of the reference price.

    Formula: (zone_top - zone_bottom) / price * 100

    Args:
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.
        price: Reference price (e.g. current price or zone midpoint).

    Returns:
        Zone size percentage as a float. Returns 0.0 if price <= 0 or on error.
        Never raises.
    """
    try:
        p = float(price)
        if p <= 0.0:
            return 0.0
        size = float(zone_top) - float(zone_bottom)
        if size <= 0.0:
            return 0.0
        return size / p * 100.0
    except Exception:
        return 0.0


def is_price_in_zone(price: float, zone_top: float, zone_bottom: float) -> bool:
    """Return True if the price is within the inclusive zone boundaries.

    Args:
        price: Price to test.
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.

    Returns:
        True if zone_bottom <= price <= zone_top. False on any error.
        Never raises.
    """
    try:
        p = float(price)
        return float(zone_bottom) <= p <= float(zone_top)
    except Exception:
        return False


def price_distance_to_zone(
    price: float,
    zone_top: float,
    zone_bottom: float,
) -> float:
    """Return the distance from price to the nearest zone boundary.

    If price is inside the zone the distance is 0.0.
    If price is above zone_top, returns price - zone_top.
    If price is below zone_bottom, returns zone_bottom - price.

    Args:
        price: Current price.
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.

    Returns:
        Non-negative float distance in price terms. Returns 0.0 on any error.
        Never raises.
    """
    try:
        p = float(price)
        top = float(zone_top)
        bot = float(zone_bottom)
        if p > top:
            return p - top
        if p < bot:
            return bot - p
        return 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
#  Premium / Discount Classification
# ─────────────────────────────────────────────

def classify_premium_discount(
    price: float,
    range_high: float,
    range_low: float,
    equilibrium_tolerance: float = 0.1,
) -> str:
    """Classify where price sits within a high-low swing range.

    Divides the range into three zones:
    - Premium:     above the upper tolerance band of the midpoint
    - Discount:    below the lower tolerance band of the midpoint
    - Equilibrium: within tolerance of the midpoint (50% level)

    Formula:
        range_size      = range_high - range_low
        equilibrium     = range_low + range_size * 0.5
        eq_band         = range_size * equilibrium_tolerance

    Args:
        price: Current price to classify.
        range_high: Highest price of the reference swing range.
        range_low: Lowest price of the reference swing range.
        equilibrium_tolerance: Fraction of range used as equilibrium band
            on each side of the midpoint. Defaults to 0.1 (10%).

    Returns:
        One of "premium", "discount", "equilibrium", or "unknown".
        Returns "unknown" on any error or if range_size <= 0. Never raises.
    """
    try:
        p = float(price)
        hi = float(range_high)
        lo = float(range_low)
        tol = float(equilibrium_tolerance)

        range_size = hi - lo
        if range_size <= 0.0:
            return "unknown"

        equilibrium = lo + range_size * _EQUILIBRIUM_MID
        eq_band = range_size * tol

        if p > equilibrium + eq_band:
            return "premium"
        if p < equilibrium - eq_band:
            return "discount"
        return "equilibrium"
    except Exception:
        return "unknown"


def is_in_discount(
    price: float,
    range_high: float,
    range_low: float,
) -> bool:
    """Return True if price is in the discount zone of the swing range.

    Args:
        price: Current price.
        range_high: Highest price of the reference swing range.
        range_low: Lowest price of the reference swing range.

    Returns:
        True when classify_premium_discount returns "discount". Never raises.
    """
    try:
        return classify_premium_discount(price, range_high, range_low) == "discount"
    except Exception:
        return False


def is_in_premium(
    price: float,
    range_high: float,
    range_low: float,
) -> bool:
    """Return True if price is in the premium zone of the swing range.

    Args:
        price: Current price.
        range_high: Highest price of the reference swing range.
        range_low: Lowest price of the reference swing range.

    Returns:
        True when classify_premium_discount returns "premium". Never raises.
    """
    try:
        return classify_premium_discount(price, range_high, range_low) == "premium"
    except Exception:
        return False


# ─────────────────────────────────────────────
#  ATR (Average True Range)
# ─────────────────────────────────────────────

def calculate_true_range(
    high: float,
    low: float,
    prev_close: float,
) -> float:
    """Calculate the True Range for a single candle.

    Formula: max(high - low, abs(high - prev_close), abs(low - prev_close))

    Args:
        high: Candle high price.
        low: Candle low price.
        prev_close: Previous candle's close price.

    Returns:
        True Range as a non-negative float. Returns 0.0 on any error.
        Never raises.
    """
    try:
        h = float(high)
        lo = float(low)
        pc = float(prev_close)
        return max(h - lo, abs(h - pc), abs(lo - pc))
    except Exception:
        return 0.0


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calculate the Average True Range (ATR) using a simple average.

    Requires at least period + 1 data points to compute one period's worth
    of True Range values (each TR needs the previous close).

    Args:
        highs: List of candle high prices (oldest first).
        lows: List of candle low prices (oldest first).
        closes: List of candle close prices (oldest first).
        period: Lookback period for the average. Defaults to 14.

    Returns:
        ATR value as a float. Returns 0.0 if data is insufficient or on error.
        Never raises.
    """
    try:
        n = len(highs)
        if n < period + 1 or len(lows) < n or len(closes) < n:
            return 0.0

        # Compute TR for the last `period` candles (each needs prev close)
        true_ranges: list[float] = []
        # We need candles at indices [n-period-1 .. n-1], giving `period` TRs
        start = n - period - 1
        for i in range(start + 1, n):
            tr = calculate_true_range(
                float(highs[i]),
                float(lows[i]),
                float(closes[i - 1]),
            )
            true_ranges.append(tr)

        if not true_ranges:
            return 0.0

        return sum(true_ranges) / len(true_ranges)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
#  Candle Analysis Helpers
# ─────────────────────────────────────────────

def candle_body_size(open: float, close: float) -> float:
    """Return the absolute size of the candle body (open-to-close distance).

    Args:
        open: Candle open price.
        close: Candle close price.

    Returns:
        abs(close - open) as a float. Returns 0.0 on any error. Never raises.
    """
    try:
        return abs(float(close) - float(open))
    except Exception:
        return 0.0


def candle_total_range(high: float, low: float) -> float:
    """Return the total wick-to-wick range of a candle.

    Args:
        high: Candle high price.
        low: Candle low price.

    Returns:
        high - low as a float. Returns 0.0 if high < low or on any error.
        Never raises.
    """
    try:
        h, lo = float(high), float(low)
        if h < lo:
            return 0.0
        return h - lo
    except Exception:
        return 0.0


def candle_body_ratio(
    open: float,
    close: float,
    high: float,
    low: float,
) -> float:
    """Return the ratio of the candle body to its total range.

    Formula: abs(close - open) / (high - low)

    Args:
        open: Candle open price.
        close: Candle close price.
        high: Candle high price.
        low: Candle low price.

    Returns:
        Body-to-range ratio between 0.0 and 1.0.
        Returns 0.0 if total range is zero or on any error. Never raises.
    """
    try:
        total = candle_total_range(high, low)
        if total == 0.0:
            return 0.0
        body = candle_body_size(open, close)
        return body / total
    except Exception:
        return 0.0


def is_bullish_candle(open: float, close: float) -> bool:
    """Return True if the candle closed above its open (bullish).

    Args:
        open: Candle open price.
        close: Candle close price.

    Returns:
        True if close > open, False otherwise. Never raises.
    """
    try:
        return float(close) > float(open)
    except Exception:
        return False


def is_bearish_candle(open: float, close: float) -> bool:
    """Return True if the candle closed below its open (bearish).

    Args:
        open: Candle open price.
        close: Candle close price.

    Returns:
        True if close < open, False otherwise. Never raises.
    """
    try:
        return float(close) < float(open)
    except Exception:
        return False


def is_doji(
    open: float,
    close: float,
    high: float,
    low: float,
    doji_threshold: float = 0.1,
) -> bool:
    """Return True if the candle qualifies as a Doji pattern.

    A Doji has a very small body relative to its total range, indicating
    indecision. The candle is a Doji when body_ratio <= doji_threshold.

    Args:
        open: Candle open price.
        close: Candle close price.
        high: Candle high price.
        low: Candle low price.
        doji_threshold: Maximum body-to-range ratio to qualify as Doji.
            Defaults to 0.1 (body <= 10% of total range).

    Returns:
        True if body_ratio <= doji_threshold, False otherwise. Never raises.
    """
    try:
        ratio = candle_body_ratio(open, close, high, low)
        return ratio <= float(doji_threshold)
    except Exception:
        return False