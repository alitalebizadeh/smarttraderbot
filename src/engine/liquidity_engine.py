from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.models.liquidity import (
    EqualHighLow,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySweep,
)

__all__ = ["LiquidityEngine", "LiquidityEngineError", "create_engine"]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_SWING_LENGTH: int = 5
DEFAULT_TOLERANCE_PCT: float = 0.05
MIN_CANDLES_REQUIRED: int = 20
RECENT_SWEEP_LOOKBACK: int = 50
_IMBALANCE_BODY_RATIO: float = 0.5


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class LiquidityEngineError(Exception):
    """Raised when liquidity analysis cannot be performed.

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
#  Engine
# ─────────────────────────────────────────────

class LiquidityEngine:
    """Detects liquidity levels and sweeps from OHLCV candle data.

    Implements Smart Money Concepts liquidity analysis:
    - BSL (Buy-Side Liquidity): stop losses resting above swing highs
    - SSL (Sell-Side Liquidity): stop losses resting below swing lows
    - EQH / EQL: clusters of equal highs/lows concentrating stop orders
    - Liquidity sweeps: price grabs liquidity then reverses

    Accepts pre-computed swing points from MarketStructureEngine or
    detects them internally using the same pivot algorithm.

    Example:
        engine = create_engine()
        lmap = engine.analyze(df, symbol="XAUUSD", timeframe="H1")
        print(lmap.recent_sweep)
    """

    def __init__(
        self,
        swing_length: int = DEFAULT_SWING_LENGTH,
        tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    ) -> None:
        """Initialize the liquidity engine.

        Args:
            swing_length: Pivot lookback on each side for swing detection. >= 2.
            tolerance_pct: Maximum % price difference for EQH/EQL grouping. > 0.

        Raises:
            LiquidityEngineError: If swing_length < 2 or tolerance_pct <= 0.
        """
        if swing_length < 2:
            raise LiquidityEngineError(
                f"swing_length must be >= 2, got {swing_length}."
            )
        if tolerance_pct <= 0:
            raise LiquidityEngineError(
                f"tolerance_pct must be > 0, got {tolerance_pct}."
            )
        self._swing_length = swing_length
        self._tolerance_pct = tolerance_pct
        self._logger = logging.getLogger(__name__)

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        swing_highs: Optional[list[Any]] = None,
        swing_lows: Optional[list[Any]] = None,
    ) -> LiquidityMap:
        """Analyze OHLCV data and return a complete LiquidityMap.

        If swing_highs and swing_lows are not provided, detects them
        internally using the same pivot algorithm as MarketStructureEngine.

        Args:
            df: OHLCV DataFrame with DatetimeIndex. Must contain high, low, close.
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "H1").
            swing_highs: Optional pre-computed swing highs. Each item must have
                "index", "time", and "price" keys (or .index/.time/.price attrs).
            swing_lows: Optional pre-computed swing lows. Same format.

        Returns:
            LiquidityMap with all detected levels, EQH/EQL clusters, and sweeps.
            Returns an empty LiquidityMap on validation failure.
        """
        label = f"{symbol} {timeframe}"

        # ── Validate ───────────────────────────────────────────────────
        required = {"high", "low", "close", "open"}
        if df is None or df.empty:
            self._logger.warning("%s: Empty DataFrame — returning empty LiquidityMap.", label)
            return self._empty_map(symbol, timeframe, 0)

        missing = required - set(df.columns)
        if missing:
            self._logger.warning(
                "%s: Missing columns %s — returning empty LiquidityMap.", label, missing
            )
            return self._empty_map(symbol, timeframe, len(df))

        if len(df) < MIN_CANDLES_REQUIRED:
            self._logger.warning(
                "%s: Insufficient candles (%d < %d) — returning empty LiquidityMap.",
                label, len(df), MIN_CANDLES_REQUIRED,
            )
            return self._empty_map(symbol, timeframe, len(df))

        try:
            # Resolve swing points
            if swing_highs is None or swing_lows is None:
                sh, sl = self._detect_swings(df)
            else:
                sh = [self._to_swing_dict(s) for s in swing_highs]
                sl = [self._to_swing_dict(s) for s in swing_lows]

            bsl_levels, ssl_levels = self._build_liquidity_levels(sh, sl, symbol, timeframe)
            equal_highs, equal_lows = self._detect_equal_highs_lows(sh, sl, symbol, timeframe)
            sweeps = self._detect_sweeps(df, bsl_levels, ssl_levels, symbol, timeframe)

            # Most recent sweep within lookback window
            recent_sweep: Optional[LiquiditySweep] = None
            if sweeps:
                cutoff_index = len(df) - RECENT_SWEEP_LOOKBACK
                recent_candidates = [
                    s for s in sweeps if s.sweep_candle_index >= cutoff_index
                ]
                if recent_candidates:
                    recent_sweep = max(
                        recent_candidates, key=lambda s: s.sweep_candle_index
                    )

            self._logger.info(
                "%s: Liquidity analysis complete — BSL=%d, SSL=%d, EQH=%d, EQL=%d, "
                "sweeps=%d, recent_sweep=%s.",
                label,
                len(bsl_levels),
                len(ssl_levels),
                len(equal_highs),
                len(equal_lows),
                len(sweeps),
                recent_sweep.sweep_type if recent_sweep else "None",
            )

            return LiquidityMap(
                symbol=symbol,
                timeframe=timeframe,
                analyzed_at=datetime.utcnow(),
                candle_count=len(df),
                bsl_levels=bsl_levels,
                ssl_levels=ssl_levels,
                equal_highs=equal_highs,
                equal_lows=equal_lows,
                sweeps=sweeps,
                recent_sweep=recent_sweep,
            )

        except Exception as exc:
            self._logger.warning(
                "%s: Unexpected error during liquidity analysis: %s — returning empty map.",
                label, exc,
            )
            return self._empty_map(symbol, timeframe, len(df))

    # ── Private: Swing Detection ──────────────────────────────────────────

    def _detect_swings(
        self, df: pd.DataFrame
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Detect pivot swing highs and lows using the standard pivot algorithm.

        Returns plain dicts instead of SwingPoint models to avoid cross-engine
        model dependency.

        Args:
            df: OHLCV DataFrame.

        Returns:
            Tuple of (swing_highs, swing_lows), each a list of dicts with
            keys: "index" (int), "time" (datetime), "price" (float).
        """
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        index_vals = df.index
        n = len(df)
        sl = self._swing_length

        swing_highs: list[dict[str, Any]] = []
        swing_lows: list[dict[str, Any]] = []

        for i in range(sl, n - sl):
            pivot_high = float(highs[i])
            pivot_low = float(lows[i])
            left_h = highs[i - sl: i]
            right_h = highs[i + 1: i + sl + 1]
            left_l = lows[i - sl: i]
            right_l = lows[i + 1: i + sl + 1]

            ts = self._to_datetime(index_vals[i])

            if (
                len(left_h) == sl and len(right_h) == sl
                and pivot_high > left_h.max()
                and pivot_high > right_h.max()
            ):
                swing_highs.append({"index": i, "time": ts, "price": pivot_high})

            if (
                len(left_l) == sl and len(right_l) == sl
                and pivot_low < left_l.min()
                and pivot_low < right_l.min()
            ):
                swing_lows.append({"index": i, "time": ts, "price": pivot_low})

        return swing_highs, swing_lows

    # ── Private: Liquidity Level Builder ─────────────────────────────────

    def _build_liquidity_levels(
        self,
        swing_highs: list[dict[str, Any]],
        swing_lows: list[dict[str, Any]],
        symbol: str,
        timeframe: str,
    ) -> tuple[list[LiquidityLevel], list[LiquidityLevel]]:
        """Build BSL and SSL LiquidityLevel objects from swing points.

        Each confirmed swing high generates one BSL level.
        Each confirmed swing low generates one SSL level.

        Args:
            swing_highs: List of swing high dicts with index/time/price.
            swing_lows: List of swing low dicts with index/time/price.
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            Tuple of (bsl_levels, ssl_levels).
        """
        bsl_levels: list[LiquidityLevel] = []
        for sh in swing_highs:
            idx = sh["index"]
            bsl_levels.append(LiquidityLevel(
                level_id=f"BSL_{symbol}_{timeframe}_{idx}",
                symbol=symbol,
                timeframe=timeframe,
                price=sh["price"],
                level_type="BSL",
                candle_index=idx,
                candle_time=sh["time"],
                touch_count=1,
                is_swept=False,
                swept_at_time=None,
            ))

        ssl_levels: list[LiquidityLevel] = []
        for sl in swing_lows:
            idx = sl["index"]
            ssl_levels.append(LiquidityLevel(
                level_id=f"SSL_{symbol}_{timeframe}_{idx}",
                symbol=symbol,
                timeframe=timeframe,
                price=sl["price"],
                level_type="SSL",
                candle_index=idx,
                candle_time=sl["time"],
                touch_count=1,
                is_swept=False,
                swept_at_time=None,
            ))

        return bsl_levels, ssl_levels

    # ── Private: Equal Highs / Lows Detection ────────────────────────────

    def _detect_equal_highs_lows(
        self,
        swing_highs: list[dict[str, Any]],
        swing_lows: list[dict[str, Any]],
        symbol: str,
        timeframe: str,
    ) -> tuple[list[EqualHighLow], list[EqualHighLow]]:
        """Group swing highs and lows into EQH and EQL clusters.

        Two swings are in the same group when their prices differ by at most
        tolerance_pct percent. Groups with fewer than two members are discarded.

        Args:
            swing_highs: List of swing high dicts.
            swing_lows: List of swing low dicts.
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            Tuple of (equal_highs, equal_lows) as EqualHighLow objects.
        """
        equal_highs = self._group_swings(swing_highs, "EQH", symbol, timeframe)
        equal_lows = self._group_swings(swing_lows, "EQL", symbol, timeframe)
        return equal_highs, equal_lows

    def _group_swings(
        self,
        swings: list[dict[str, Any]],
        level_type: str,
        symbol: str,
        timeframe: str,
    ) -> list[EqualHighLow]:
        """Cluster swings by price proximity into EQH or EQL groups.

        Uses a greedy single-pass grouping: each swing is assigned to the
        first existing group whose average price is within tolerance_pct,
        or starts a new group.

        Args:
            swings: List of swing dicts with index/time/price.
            level_type: "EQH" or "EQL".
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            List of EqualHighLow objects with touch_count >= 2.
        """
        if not swings:
            return []

        # groups: list of lists of swing dicts
        groups: list[list[dict[str, Any]]] = []

        for swing in swings:
            price = swing["price"]
            assigned = False
            for group in groups:
                group_avg = sum(s["price"] for s in group) / len(group)
                pct_diff = abs(price - group_avg) / group_avg * 100.0
                if pct_diff <= self._tolerance_pct:
                    group.append(swing)
                    assigned = True
                    break
            if not assigned:
                groups.append([swing])

        result: list[EqualHighLow] = []
        for group in groups:
            if len(group) < 2:
                continue
            avg_price = sum(s["price"] for s in group) / len(group)
            times = [s["time"] for s in group]
            result.append(EqualHighLow(
                symbol=symbol,
                timeframe=timeframe,
                price=avg_price,
                level_type=level_type,  # type: ignore[arg-type]
                touch_count=len(group),
                first_touch_time=min(times),
                last_touch_time=max(times),
                tolerance_pct=self._tolerance_pct,
                is_swept=False,
                swept_at_time=None,
            ))

        return result

    # ── Private: Sweep Detection ──────────────────────────────────────────

    def _detect_sweeps(
        self,
        df: pd.DataFrame,
        bsl_levels: list[LiquidityLevel],
        ssl_levels: list[LiquidityLevel],
        symbol: str,
        timeframe: str,
    ) -> list[LiquiditySweep]:
        """Detect candles that sweep through BSL or SSL levels.

        A BSL sweep: candle high exceeds the BSL price (price grabs buy-side
        liquidity). A SSL sweep: candle low drops below the SSL price.

        Marks swept levels as is_swept=True to avoid double-counting.

        Args:
            df: OHLCV DataFrame.
            bsl_levels: List of BSL LiquidityLevel objects (mutated in place).
            ssl_levels: List of SSL LiquidityLevel objects (mutated in place).
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.

        Returns:
            List of LiquiditySweep objects sorted by candle index ascending.
        """
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        index_vals = df.index
        n = len(df)

        sweeps: list[LiquiditySweep] = []

        for i in range(n):
            candle_high = float(highs[i])
            candle_low = float(lows[i])
            candle_close = float(closes[i])
            candle_open = float(opens[i])
            candle_time = self._to_datetime(index_vals[i])

            candle_range = candle_high - candle_low
            body_size = abs(candle_open - candle_close)
            imbalance_left = (
                candle_range > 0
                and body_size < candle_range * _IMBALANCE_BODY_RATIO
            )

            # ── BSL sweeps ─────────────────────────────────────────────
            for level in bsl_levels:
                if level.is_swept:
                    continue
                # Only check levels whose candle is before this candle
                if level.candle_index >= i:
                    continue
                if candle_high > level.price:
                    returned_inside = candle_close < level.price
                    sweeps.append(LiquiditySweep(
                        symbol=symbol,
                        timeframe=timeframe,
                        sweep_type="BSL_sweep",
                        swept_level=level,
                        sweep_candle_index=i,
                        sweep_candle_time=candle_time,
                        sweep_high=candle_high,
                        sweep_low=candle_low,
                        close_price=candle_close,
                        returned_inside=returned_inside,
                        imbalance_left=imbalance_left,
                    ))
                    level.is_swept = True
                    level.swept_at_time = candle_time

            # ── SSL sweeps ─────────────────────────────────────────────
            for level in ssl_levels:
                if level.is_swept:
                    continue
                if level.candle_index >= i:
                    continue
                if candle_low < level.price:
                    returned_inside = candle_close > level.price
                    sweeps.append(LiquiditySweep(
                        symbol=symbol,
                        timeframe=timeframe,
                        sweep_type="SSL_sweep",
                        swept_level=level,
                        sweep_candle_index=i,
                        sweep_candle_time=candle_time,
                        sweep_high=candle_high,
                        sweep_low=candle_low,
                        close_price=candle_close,
                        returned_inside=returned_inside,
                        imbalance_left=imbalance_left,
                    ))
                    level.is_swept = True
                    level.swept_at_time = candle_time

        return sweeps

    # ── Private: Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _to_datetime(val: Any) -> datetime:
        """Convert a pandas Timestamp or similar to a plain Python datetime.

        Args:
            val: A pandas Timestamp, numpy datetime64, or datetime.

        Returns:
            Python datetime object.
        """
        if hasattr(val, "to_pydatetime"):
            return val.to_pydatetime()
        if isinstance(val, datetime):
            return val
        return datetime.utcfromtimestamp(float(val))

    @staticmethod
    def _to_swing_dict(swing: Any) -> dict[str, Any]:
        """Normalize a SwingPoint model or dict to a plain dict.

        Accepts objects with .index/.time/.price attributes (SwingPoint)
        or plain dicts with the same keys.

        Args:
            swing: SwingPoint dataclass instance or dict.

        Returns:
            Dict with keys "index", "time", "price".
        """
        if isinstance(swing, dict):
            return {"index": swing["index"], "time": swing["time"], "price": swing["price"]}
        return {
            "index": swing.index,
            "time": swing.time,
            "price": swing.price,
        }

    def _empty_map(
        self, symbol: str, timeframe: str, candle_count: int
    ) -> LiquidityMap:
        """Build an empty LiquidityMap for fallback returns.

        Args:
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.
            candle_count: Number of candles in the input (may be 0).

        Returns:
            LiquidityMap with all empty lists and no recent sweep.
        """
        return LiquidityMap(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.utcnow(),
            candle_count=candle_count,
            bsl_levels=[],
            ssl_levels=[],
            equal_highs=[],
            equal_lows=[],
            sweeps=[],
            recent_sweep=None,
        )


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_engine(
    swing_length: int = DEFAULT_SWING_LENGTH,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> LiquidityEngine:
    """Factory function — create and return a configured LiquidityEngine.

    Args:
        swing_length: Pivot lookback on each side for swing detection. Must be >= 2.
        tolerance_pct: Maximum % price difference for EQH/EQL grouping. Must be > 0.

    Returns:
        A ready-to-use LiquidityEngine instance.

    Raises:
        LiquidityEngineError: If swing_length < 2 or tolerance_pct <= 0.
    """
    return LiquidityEngine(swing_length=swing_length, tolerance_pct=tolerance_pct)