from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

import numpy as np
import pandas as pd

from src.models.market_structure import (
    MarketStructure,
    MarketStructureEvent,
    SwingPoint,
)

__all__ = ["MarketStructureEngine", "MarketStructureEngineError", "create_engine"]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_SWING_LENGTH: int = 5
MIN_CANDLES_REQUIRED: int = 20


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class MarketStructureEngineError(Exception):
    """Raised when market structure analysis cannot be performed.

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

class MarketStructureEngine:
    """Detects market structure from OHLCV candle data.

    Implements Smart Money Concepts (SMC) market structure analysis:
    - Swing High / Swing Low detection with configurable lookback
    - Break of Structure (BOS) — trend continuation signal
    - Change of Character (CHoCH) — potential trend reversal signal
    - Current market bias (bullish / bearish / neutral)

    The engine operates purely on close prices for BOS/CHoCH confirmation
    (body-based, not wick-based), consistent with ICT methodology.

    Example:
        engine = create_engine(swing_length=5)
        ms = engine.analyze(df, symbol="XAUUSD", timeframe="H1")
        print(ms.current_bias)
        print(ms.last_event)
    """

    def __init__(self, swing_length: int = DEFAULT_SWING_LENGTH) -> None:
        """Initialize the engine with a swing detection lookback length.

        Args:
            swing_length: Number of candles required on each side of a pivot
                for it to qualify as a Swing High or Swing Low. Must be >= 2.

        Raises:
            MarketStructureEngineError: If swing_length is less than 2.
        """
        if swing_length < 2:
            raise MarketStructureEngineError(
                f"swing_length must be >= 2, got {swing_length}."
            )
        self._swing_length = swing_length
        self._logger = logging.getLogger(__name__)

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> MarketStructure:
        """Analyze OHLCV data and return a complete MarketStructure result.

        Validates input data, detects swing points, identifies BOS/CHoCH
        events, and determines the current market bias.

        Args:
            df: OHLCV DataFrame with DatetimeIndex named "time".
                Must contain columns: open, high, low, close.
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "H1").

        Returns:
            MarketStructure dataclass with swing points, events, and bias.
            Returns a neutral empty MarketStructure if data is insufficient.
        """
        label = f"{symbol} {timeframe}"

        # ── Validate input ─────────────────────────────────────────────
        required_cols = {"open", "high", "low", "close"}
        if df is None or df.empty:
            self._logger.warning("%s: Empty DataFrame received — returning neutral structure.", label)
            return self._empty_structure(symbol, timeframe, candle_count=0)

        missing = required_cols - set(df.columns)
        if missing:
            self._logger.warning(
                "%s: Missing required columns %s — returning neutral structure.", label, missing
            )
            return self._empty_structure(symbol, timeframe, candle_count=len(df))

        if len(df) < MIN_CANDLES_REQUIRED:
            self._logger.warning(
                "%s: Insufficient candles (%d < %d) — returning neutral structure.",
                label, len(df), MIN_CANDLES_REQUIRED,
            )
            return self._empty_structure(symbol, timeframe, candle_count=len(df))

        # ── Analysis ───────────────────────────────────────────────────
        try:
            swing_highs, swing_lows = self._detect_swings(df)
            events, current_bias = self._detect_events(df, swing_highs, swing_lows, symbol=symbol, timeframe=timeframe)

            # Fall back to structural bias if no events found
            if not events and current_bias == "neutral":
                current_bias = self._determine_bias_from_swings(swing_highs, swing_lows)

            last_event: Optional[MarketStructureEvent] = events[-1] if events else None

            self._logger.info(
                "%s: Analysis complete — %d swing highs, %d swing lows, "
                "%d events, bias=%s.",
                label,
                len(swing_highs),
                len(swing_lows),
                len(events),
                current_bias,
            )

            return MarketStructure(
                symbol=symbol,
                timeframe=timeframe,
                analyzed_at=datetime.utcnow(),
                candle_count=len(df),
                swing_highs=swing_highs,
                swing_lows=swing_lows,
                events=events,
                current_bias=current_bias,
                last_event=last_event,
            )

        except Exception as exc:
            self._logger.warning(
                "%s: Analysis raised an unexpected error: %s — returning neutral structure.",
                label, exc,
            )
            return self._empty_structure(symbol, timeframe, candle_count=len(df))

    # ── Private: Swing Detection ──────────────────────────────────────────

    def _detect_swings(
        self,
        df: pd.DataFrame,
    ) -> tuple[list[SwingPoint], list[SwingPoint]]:
        """Detect confirmed Swing Highs and Swing Lows from OHLCV data.

        A candle at index i is a Swing High if its high is strictly greater
        than all highs within swing_length candles on both sides.
        A candle at index i is a Swing Low if its low is strictly less than
        all lows within swing_length candles on both sides.

        Only candles with swing_length confirmed right-side candles are
        eligible (all detected here are confirmed by construction).

        Args:
            df: Validated OHLCV DataFrame.

        Returns:
            Tuple of (swing_highs, swing_lows) — lists of SwingPoint objects
            sorted by their candle index ascending.
        """
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        index_vals = df.index
        n = len(df)

        swing_highs: list[SwingPoint] = []
        swing_lows: list[SwingPoint] = []

        sl = self._swing_length

        for i in range(sl, n - sl):
            left_slice_h = highs[i - sl: i]
            right_slice_h = highs[i + 1: i + sl + 1]
            left_slice_l = lows[i - sl: i]
            right_slice_l = lows[i + 1: i + sl + 1]

            pivot_high = highs[i]
            pivot_low = lows[i]

            # Swing High: strictly greater than all neighbours
            if (
                len(left_slice_h) == sl
                and len(right_slice_h) == sl
                and pivot_high > left_slice_h.max()
                and pivot_high > right_slice_h.max()
            ):
                raw_time = index_vals[i]
                ts = (
                    raw_time.to_pydatetime()
                    if hasattr(raw_time, "to_pydatetime")
                    else datetime.utcfromtimestamp(float(raw_time))
                )
                strength_score, scale = self._classify_swing_strength(df, i, float(pivot_high), "high")
                swing_highs.append(
                    SwingPoint(
                        index=i,
                        time=ts,
                        price=float(pivot_high),
                        swing_type="high",
                        is_confirmed=True,
                        strength_score=strength_score,
                        swing_scale=scale,
                    )
                )

            # Swing Low: strictly less than all neighbours
            if (
                len(left_slice_l) == sl
                and len(right_slice_l) == sl
                and pivot_low < left_slice_l.min()
                and pivot_low < right_slice_l.min()
            ):
                raw_time = index_vals[i]
                ts = (
                    raw_time.to_pydatetime()
                    if hasattr(raw_time, "to_pydatetime")
                    else datetime.utcfromtimestamp(float(raw_time))
                )
                strength_score, scale = self._classify_swing_strength(df, i, float(pivot_low), "low")
                swing_lows.append(
                    SwingPoint(
                        index=i,
                        time=ts,
                        price=float(pivot_low),
                        swing_type="low",
                        is_confirmed=True,
                        strength_score=strength_score,
                        swing_scale=scale,
                    )
                )

        return swing_highs, swing_lows

    def _calculate_atr(self, df: pd.DataFrame, lookback: int = 14) -> np.ndarray:
        """Calculate a rolling ATR array using the true range formula."""
        if df is None or df.empty or not {"high", "low", "close"}.issubset(df.columns):
            return np.zeros(len(df), dtype=float)

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        true_ranges: list[float] = []

        for idx in range(len(df)):
            if idx == 0:
                true_ranges.append(float(highs[idx] - lows[idx]))
                continue
            tr = max(
                float(highs[idx] - lows[idx]),
                abs(float(highs[idx] - closes[idx - 1])),
                abs(float(lows[idx] - closes[idx - 1])),
            )
            true_ranges.append(float(tr))

        atr = pd.Series(true_ranges, index=df.index).rolling(window=lookback, min_periods=1).mean().to_numpy(dtype=float)
        return atr

    def _estimate_atr(self, df: pd.DataFrame, index: int, lookback: int = 14) -> float:
        """Return ATR at the given index, minimal value of 1e-9 to avoid division by zero."""
        if df is None or df.empty or index < 0 or index >= len(df):
            return 0.0
        if {"high", "low", "close"}.difference(df.columns):
            return 0.0

        start = max(0, index - lookback)
        window = df.iloc[start:index + 1].copy()
        if window.empty:
            return 0.0

        high = window["high"].to_numpy(dtype=float)
        low = window["low"].to_numpy(dtype=float)
        close = window["close"].to_numpy(dtype=float)
        tr = []
        for i in range(len(window)):
            if i == 0:
                tr.append(float(high[i] - low[i]))
            else:
                tr.append(
                    max(
                        float(high[i] - low[i]),
                        abs(float(high[i] - close[i - 1])),
                        abs(float(low[i] - close[i - 1])),
                    )
                )
        if not tr:
            return 0.0
        return float(sum(tr) / len(tr))

    def _score_break_context(
        self,
        df: pd.DataFrame,
        index: int,
        level: float,
        close: float,
        direction: Literal["bullish", "bearish"],
    ) -> float:
        """Return a contextual BOS/CHoCH score based on the relative move and confirmation."""
        atr_value = self._estimate_atr(df, index)
        if atr_value <= 0:
            return 0.0

        score = 0.0
        distance = abs(close - level)
        ratio = distance / atr_value

        if direction == "bullish" and close > level:
            score += 30.0
        elif direction == "bearish" and close < level:
            score += 30.0

        score += min(25.0, max(0.0, ratio - 0.5) * 25.0)

        prev_close = float(df["close"].iloc[index - 1]) if index > 0 else close
        body = abs(close - prev_close)
        score += min(20.0, max(0.0, body / atr_value) * 15.0)

        follow_through = 0
        limit = min(len(df), index + 3)
        for j in range(index + 1, limit):
            next_close = float(df["close"].iloc[j])
            if direction == "bullish" and next_close > level:
                follow_through += 1
            elif direction == "bearish" and next_close < level:
                follow_through += 1
        score += min(15.0, follow_through * 10.0)

        if direction == "bullish":
            recent_trend = float(df["close"].iloc[max(0, index - 5):index].mean()) if index >= 1 else close
            if close > recent_trend:
                score += 10.0
        else:
            recent_trend = float(df["close"].iloc[max(0, index - 5):index].mean()) if index >= 1 else close
            if close < recent_trend:
                score += 10.0

        return score

    def _has_liquidity_grab(
        self,
        df: pd.DataFrame,
        index: int,
        level: float,
        direction: Literal["bullish", "bearish"],
    ) -> bool:
        """Detect a sweep beyond the relevant level before reversal."""
        start = max(0, index - 5)
        window = df.iloc[start:index + 1]
        if window.empty:
            return False

        if direction == "bullish":
            prior_low = float(window["low"].iloc[:-1].min()) if len(window) > 1 else float(window["low"].iloc[0])
            return prior_low < level and float(df["close"].iloc[index]) > level

        prior_high = float(window["high"].iloc[:-1].max()) if len(window) > 1 else float(window["high"].iloc[0])
        return prior_high > level and float(df["close"].iloc[index]) < level

    def _is_valid_bos_break(
        self,
        df: pd.DataFrame,
        index: int,
        close: float,
        level: float,
        atr_value: float,
        displacement: float,
        direction: Literal["bullish", "bearish"],
    ) -> bool:
        """Use a relative score model instead of a single hard threshold."""
        if index < 0 or atr_value <= 0:
            return False

        score = self._score_break_context(df, index, level, close, direction)
        if score < 70.0:
            return False

        if direction == "bullish":
            return close > level and displacement > atr_value * 0.35 and score >= 70.0
        return close < level and displacement > atr_value * 0.35 and score >= 70.0

    def _is_valid_choch_break(
        self,
        df: pd.DataFrame,
        index: int,
        close: float,
        level: float,
        atr_value: float,
        direction: Literal["bullish", "bearish"],
    ) -> bool:
        """CHoCH uses a separate reversal model: sweep + rejection + opposite structure break + confirmation."""
        if index <= 0 or atr_value <= 0:
            return False

        prev_close = float(df["close"].iloc[index - 1])
        displacement = abs(close - prev_close)
        if displacement <= atr_value * 0.25:
            return False

        sweep = self._has_liquidity_grab(df, index, level, direction)
        if not sweep:
            return False

        score = 0.0
        if direction == "bullish":
            if close > level:
                score += 30.0
            if close > max(float(df["close"].iloc[max(0, index - 3):index].max()), prev_close):
                score += 25.0
            if displacement > atr_value * 0.4:
                score += 20.0
            if index + 1 < len(df) and float(df["close"].iloc[index + 1]) > close:
                score += 15.0
            if close > float(df["close"].iloc[max(0, index - 5):index].mean()):
                score += 10.0
            return score >= 70.0

        if close < level:
            score += 30.0
        if close < min(float(df["close"].iloc[max(0, index - 3):index].min()), prev_close):
            score += 25.0
        if displacement > atr_value * 0.4:
            score += 20.0
        if index + 1 < len(df) and float(df["close"].iloc[index + 1]) < close:
            score += 15.0
        if close < float(df["close"].iloc[max(0, index - 5):index].mean()):
            score += 10.0
        return score >= 70.0

    def _classify_swing_strength(
        self,
        df: pd.DataFrame,
        index: int,
        price: float,
        swing_type: Literal["high", "low"],
    ) -> tuple[float, Literal["internal", "external"]]:
        """Classify swings as internal or external based on local relative strength."""
        atr_value = self._estimate_atr(df, index)
        if atr_value <= 0:
            return 0.0, "internal"

        start = max(0, index - 10)
        end = min(len(df), index + 11)
        local_window = df.iloc[start:end]
        if swing_type == "high":
            local_low = float(local_window["low"].min())
            strength = max(0.0, (price - local_low) / atr_value * 25.0)
        else:
            local_high = float(local_window["high"].max())
            strength = max(0.0, (local_high - price) / atr_value * 25.0)

        if strength >= 60.0:
            return min(100.0, strength), "external"
        return min(100.0, strength), "internal"

    # ── Private: Event Detection ──────────────────────────────────────────

    def _detect_events(
        self,
        df: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        symbol: str = "",
        timeframe: str = "",
    ) -> tuple[list[MarketStructureEvent], Literal["bullish", "bearish", "neutral"]]:
        """Detect BOS and CHoCH events with confirmation rules instead of simple breaks."""
        if not swing_highs and not swing_lows:
            return [], "neutral"

        closes = df["close"].to_numpy(dtype=float)
        index_vals = df.index
        n = len(df)
        atr_values = self._calculate_atr(df)

        events: list[MarketStructureEvent] = []
        current_bias: Literal["bullish", "bearish", "neutral"] = "neutral"

        high_by_idx: dict[int, SwingPoint] = {sp.index: sp for sp in swing_highs}
        low_by_idx: dict[int, SwingPoint] = {sp.index: sp for sp in swing_lows}

        last_confirmed_high: Optional[SwingPoint] = None
        last_confirmed_low: Optional[SwingPoint] = None

        for i in range(n):
            if i in high_by_idx:
                last_confirmed_high = high_by_idx[i]
            if i in low_by_idx:
                last_confirmed_low = low_by_idx[i]

            close = float(closes[i])
            raw_time = index_vals[i]
            candle_time = (
                raw_time.to_pydatetime()
                if hasattr(raw_time, "to_pydatetime")
                else datetime.utcfromtimestamp(float(raw_time))
            )
            atr_value = float(atr_values[i]) if i < len(atr_values) else 0.0

            if current_bias == "bullish":
                if last_confirmed_high is not None:
                    displacement = abs(close - closes[i - 1]) if i > 0 else 0.0
                    if self._is_valid_bos_break(df, i, close, last_confirmed_high.price, atr_value, displacement, "bullish"):
                        events.append(MarketStructureEvent(
                            event_type="BOS",
                            direction="bullish",
                            broken_swing=last_confirmed_high,
                            break_candle_index=i,
                            break_candle_time=candle_time,
                            break_price=close,
                            symbol=symbol,
                            timeframe=timeframe,
                        ))
                        current_bias = "bullish"
                        last_confirmed_high = None
                if last_confirmed_low is not None and self._is_valid_choch_break(df, i, close, last_confirmed_low.price, atr_value, "bearish"):
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bearish",
                        broken_swing=last_confirmed_low,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=symbol,
                        timeframe=timeframe,
                    ))
                    current_bias = "bearish"
                    last_confirmed_low = None

            elif current_bias == "bearish":
                if last_confirmed_low is not None:
                    displacement = abs(close - closes[i - 1]) if i > 0 else 0.0
                    if self._is_valid_bos_break(df, i, close, last_confirmed_low.price, atr_value, displacement, "bearish"):
                        events.append(MarketStructureEvent(
                            event_type="BOS",
                            direction="bearish",
                            broken_swing=last_confirmed_low,
                            break_candle_index=i,
                            break_candle_time=candle_time,
                            break_price=close,
                            symbol=symbol,
                            timeframe=timeframe,
                        ))
                        current_bias = "bearish"
                        last_confirmed_low = None
                if last_confirmed_high is not None and self._is_valid_choch_break(df, i, close, last_confirmed_high.price, atr_value, "bullish"):
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bullish",
                        broken_swing=last_confirmed_high,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=symbol,
                        timeframe=timeframe,
                    ))
                    current_bias = "bullish"
                    last_confirmed_high = None

            else:
                if last_confirmed_high is not None:
                    displacement = abs(close - closes[i - 1]) if i > 0 else 0.0
                    if self._is_valid_bos_break(df, i, close, last_confirmed_high.price, atr_value, displacement, "bullish"):
                        events.append(MarketStructureEvent(
                            event_type="BOS",
                            direction="bullish",
                            broken_swing=last_confirmed_high,
                            break_candle_index=i,
                            break_candle_time=candle_time,
                            break_price=close,
                            symbol=symbol,
                            timeframe=timeframe,
                        ))
                        current_bias = "bullish"
                        last_confirmed_high = None
                elif last_confirmed_low is not None and self._is_valid_choch_break(df, i, close, last_confirmed_low.price, atr_value, "bearish"):
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bearish",
                        broken_swing=last_confirmed_low,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=symbol,
                        timeframe=timeframe,
                    ))
                    current_bias = "bearish"
                    last_confirmed_low = None
                elif last_confirmed_low is not None:
                    displacement = abs(close - closes[i - 1]) if i > 0 else 0.0
                    if self._is_valid_bos_break(df, i, close, last_confirmed_low.price, atr_value, displacement, "bearish"):
                        events.append(MarketStructureEvent(
                            event_type="BOS",
                            direction="bearish",
                            broken_swing=last_confirmed_low,
                            break_candle_index=i,
                            break_candle_time=candle_time,
                            break_price=close,
                            symbol=symbol,
                            timeframe=timeframe,
                        ))
                        current_bias = "bearish"
                        last_confirmed_low = None
                if last_confirmed_high is not None and self._is_valid_choch_break(df, i, close, last_confirmed_high.price, atr_value, "bullish"):
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bullish",
                        broken_swing=last_confirmed_high,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=symbol,
                        timeframe=timeframe,
                    ))
                    current_bias = "bullish"
                    last_confirmed_high = None

        if not events:
            return [], self._determine_bias_from_swings(swing_highs, swing_lows)

        return events, current_bias

    # ── Private: Structural Bias Fallback ─────────────────────────────────

    def _determine_bias_from_swings(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> Literal["bullish", "bearish", "neutral"]:
        """Infer market bias from the last two swing highs and swing lows.

        Uses Higher High + Higher Low for bullish, Lower High + Lower Low
        for bearish. Returns neutral when the pattern is mixed or swings
        are insufficient.

        Args:
            swing_highs: List of confirmed Swing High points.
            swing_lows: List of confirmed Swing Low points.

        Returns:
            "bullish", "bearish", or "neutral".
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "neutral"

        last_two_highs = swing_highs[-2:]
        last_two_lows = swing_lows[-2:]

        higher_high = last_two_highs[1].price > last_two_highs[0].price
        higher_low = last_two_lows[1].price > last_two_lows[0].price
        lower_high = last_two_highs[1].price < last_two_highs[0].price
        lower_low = last_two_lows[1].price < last_two_lows[0].price

        if higher_high and higher_low:
            return "bullish"
        if lower_high and lower_low:
            return "bearish"
        return "neutral"

    # ── Private: Empty Result ─────────────────────────────────────────────

    def _empty_structure(
        self,
        symbol: str,
        timeframe: str,
        candle_count: int,
    ) -> MarketStructure:
        """Build a neutral, empty MarketStructure for fallback returns.

        Args:
            symbol: Instrument symbol.
            timeframe: Chart timeframe string.
            candle_count: Number of candles in the input (may be 0).

        Returns:
            MarketStructure with empty lists, neutral bias, and no last event.
        """
        return MarketStructure(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.utcnow(),
            candle_count=candle_count,
            swing_highs=[],
            swing_lows=[],
            events=[],
            current_bias="neutral",
            last_event=None,
        )


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_engine(swing_length: int = DEFAULT_SWING_LENGTH) -> MarketStructureEngine:
    """Factory function — create and return a configured MarketStructureEngine.

    Args:
        swing_length: Number of candles required on each side of a pivot
            for swing point confirmation. Must be >= 2.

    Returns:
        A ready-to-use MarketStructureEngine instance.

    Raises:
        MarketStructureEngineError: If swing_length is less than 2.
    """
    return MarketStructureEngine(swing_length=swing_length)