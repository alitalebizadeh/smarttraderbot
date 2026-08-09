from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

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
            events, current_bias = self._detect_events(df, swing_highs, swing_lows)

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
                swing_highs.append(
                    SwingPoint(
                        index=i,
                        time=ts,
                        price=float(pivot_high),
                        swing_type="high",
                        is_confirmed=True,
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
                swing_lows.append(
                    SwingPoint(
                        index=i,
                        time=ts,
                        price=float(pivot_low),
                        swing_type="low",
                        is_confirmed=True,
                    )
                )

        return swing_highs, swing_lows

    # ── Private: Event Detection ──────────────────────────────────────────

    def _detect_events(
        self,
        df: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> tuple[list[MarketStructureEvent], Literal["bullish", "bearish", "neutral"]]:
        """Detect BOS and CHoCH events by iterating candles chronologically.

        Tracks the most recent confirmed Swing High and Swing Low as price
        progresses. On each candle, checks whether the close has broken
        either level and classifies the break as BOS or CHoCH based on
        the current market bias.

        Args:
            df: Validated OHLCV DataFrame.
            swing_highs: Confirmed swing highs sorted by candle index.
            swing_lows: Confirmed swing lows sorted by candle index.

        Returns:
            Tuple of (events list, final bias string).
        """
        if not swing_highs and not swing_lows:
            return [], "neutral"

        closes = df["close"].to_numpy()
        index_vals = df.index
        n = len(df)

        events: list[MarketStructureEvent] = []
        current_bias: Literal["bullish", "bearish", "neutral"] = "neutral"

        # Build index-keyed lookups for O(1) access as we iterate
        # Maps candle_index → SwingPoint
        high_by_idx: dict[int, SwingPoint] = {sp.index: sp for sp in swing_highs}
        low_by_idx: dict[int, SwingPoint] = {sp.index: sp for sp in swing_lows}

        last_confirmed_high: Optional[SwingPoint] = None
        last_confirmed_low: Optional[SwingPoint] = None

        for i in range(n):
            # Update last known confirmed swing points up to this candle
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

            # ── Bullish bias checks ────────────────────────────────────
            if current_bias == "bullish":
                # BOS bullish: close above last confirmed high (trend continues)
                if last_confirmed_high is not None and close > last_confirmed_high.price:
                    events.append(MarketStructureEvent(
                        event_type="BOS",
                        direction="bullish",
                        broken_swing=last_confirmed_high,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    # Reset so same level doesn't trigger again
                    last_confirmed_high = None

                # CHoCH: close below last confirmed low (trend reversal)
                elif last_confirmed_low is not None and close < last_confirmed_low.price:
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bearish",
                        broken_swing=last_confirmed_low,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    current_bias = "bearish"
                    last_confirmed_low = None

            # ── Bearish bias checks ────────────────────────────────────
            elif current_bias == "bearish":
                # BOS bearish: close below last confirmed low (trend continues)
                if last_confirmed_low is not None and close < last_confirmed_low.price:
                    events.append(MarketStructureEvent(
                        event_type="BOS",
                        direction="bearish",
                        broken_swing=last_confirmed_low,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    last_confirmed_low = None

                # CHoCH: close above last confirmed high (trend reversal)
                elif last_confirmed_high is not None and close > last_confirmed_high.price:
                    events.append(MarketStructureEvent(
                        event_type="CHoCH",
                        direction="bullish",
                        broken_swing=last_confirmed_high,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    current_bias = "bullish"
                    last_confirmed_high = None

            # ── Neutral bias: first break sets the bias ────────────────
            else:
                if last_confirmed_high is not None and close > last_confirmed_high.price:
                    events.append(MarketStructureEvent(
                        event_type="BOS",
                        direction="bullish",
                        broken_swing=last_confirmed_high,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    current_bias = "bullish"
                    last_confirmed_high = None

                elif last_confirmed_low is not None and close < last_confirmed_low.price:
                    events.append(MarketStructureEvent(
                        event_type="BOS",
                        direction="bearish",
                        broken_swing=last_confirmed_low,
                        break_candle_index=i,
                        break_candle_time=candle_time,
                        break_price=close,
                        symbol=df.attrs.get("symbol", ""),
                        timeframe=df.attrs.get("timeframe", ""),
                    ))
                    current_bias = "bearish"
                    last_confirmed_low = None

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