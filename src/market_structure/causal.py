from __future__ import annotations

from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd

from src.models.market_structure import MarketStructureEvent, SwingPoint


def _is_valid_bos(
    df: pd.DataFrame,
    break_index: int,
    swing_level: float,
    direction: str,
    atr: pd.Series,
) -> bool:
    """Return True only when a true BOS break is confirmed without look-ahead data.

    Conditions required by the specification:
    1. The close at ``break_index`` breaks beyond ``swing_level``.
    2. The break distance exceeds 0.5 * ATR at that index.
    3. A prior displacement candle exists in the three bars before the break.
    4. The check uses only information available at or before ``break_index``.
    """
    if break_index < 0 or break_index >= len(df):
        return False
    if direction not in {"bullish", "bearish"}:
        return False

    close = float(df["close"].iloc[break_index])
    current_atr = float(atr.iloc[break_index]) if break_index < len(atr) else 0.0
    if current_atr <= 0:
        return False

    if direction == "bullish":
        beyond = close > swing_level
        break_distance = close - swing_level
    else:
        beyond = close < swing_level
        break_distance = swing_level - close

    if not beyond:
        return False
    if break_distance <= 0.5 * current_atr:
        return False
    if not _has_displacement(df, max(0, break_index - 3), break_index, atr):
        return False
    return True


def _has_displacement(
    df: pd.DataFrame,
    start_index: int,
    end_index: int,
    atr: pd.Series,
) -> bool:
    """Return True if any candle in the past window had body > 1.5 * ATR.

    ``end_index`` is exclusive, so the break candle itself is not treated as
    displacement. The scan only uses indices less than ``end_index``.
    """
    if start_index < 0:
        start_index = 0
    if end_index <= start_index:
        return False

    for idx in range(start_index, end_index):
        if idx >= len(df):
            continue
        current_atr = float(atr.iloc[idx]) if idx < len(atr) else 0.0
        if current_atr <= 0:
            continue
        body = abs(float(df["close"].iloc[idx]) - float(df["open"].iloc[idx]))
        if body > 1.5 * current_atr:
            return True
    return False


def _has_confirmation_candle(
    df: pd.DataFrame,
    after_index: int,
    direction: str,
    atr: pd.Series,
) -> bool:
    """Return True if the immediate confirmation candle moves in the same direction.

    The candle at ``after_index`` is checked only. No future data is used.
    """
    if after_index < 0 or after_index >= len(df):
        return False
    if direction not in {"bullish", "bearish"}:
        return False

    current_atr = float(atr.iloc[after_index]) if after_index < len(atr) else 0.0
    if current_atr <= 0:
        return False

    open_price = float(df["open"].iloc[after_index])
    close_price = float(df["close"].iloc[after_index])
    body = abs(close_price - open_price)

    if direction == "bullish":
        same_direction = close_price > open_price
    else:
        same_direction = close_price < open_price

    return same_direction and body > 0.3 * current_atr


def _is_valid_choch(
    df: pd.DataFrame,
    event_index: int,
    swing_level: float,
    direction: str,
    atr: pd.Series,
    liquidity_swept: bool,
) -> bool:
    """Return True only if a valid CHoCH sequence is fully present.

    Required sequence:
    1. ``liquidity_swept`` is True and the sweep happened before this event.
    2. The close at ``event_index`` breaks beyond the swing level.
    3. A confirmation candle exists at ``event_index + 1`` in the same direction.
    4. The check uses only data available at or before the event + confirmation candle.
    """
    if event_index < 0 or event_index >= len(df) - 1:
        return False
    if direction not in {"bullish", "bearish"}:
        return False
    if not liquidity_swept:
        return False

    close = float(df["close"].iloc[event_index])
    current_atr = float(atr.iloc[event_index]) if event_index < len(atr) else 0.0
    if current_atr <= 0:
        return False

    if direction == "bullish":
        beyond = close > swing_level
        break_distance = close - swing_level
    else:
        beyond = close < swing_level
        break_distance = swing_level - close

    if not beyond:
        return False
    if break_distance <= 0.5 * current_atr:
        return False
    if not _has_confirmation_candle(df, event_index + 1, direction, atr):
        return False
    return True


class CausalMarketStructureEngine:
    """Detect structure using only candles available at each evaluation bar."""

    def __init__(self, swing_length: int = 2) -> None:
        if swing_length < 2:
            raise ValueError("swing_length must be at least 2")
        self.swing_length = swing_length

    def analyze(self, frame: pd.DataFrame, symbol: str, timeframe: str) -> list[MarketStructureEvent]:
        required = {"high", "low", "close"}
        if frame is None or len(frame) < self.swing_length * 2 + 2 or not required.issubset(frame.columns):
            return []
        data = frame.copy()
        data.index = pd.to_datetime(data.index, utc=True, errors="raise")
        highs = data["high"].to_numpy(dtype=float)
        lows = data["low"].to_numpy(dtype=float)
        closes = data["close"].to_numpy(dtype=float)
        atr = self._atr(data)
        confirmed_high: SwingPoint | None = None
        confirmed_low: SwingPoint | None = None
        bias: Literal["bullish", "bearish", "neutral"] = "neutral"
        events: list[MarketStructureEvent] = []

        for current in range(self.swing_length * 2, len(data)):
            pivot = current - self.swing_length
            if self._is_pivot_high(highs, pivot):
                confirmed_high = self._swing(data, pivot, current, "high", highs[pivot])
            if self._is_pivot_low(lows, pivot):
                confirmed_low = self._swing(data, pivot, current, "low", lows[pivot])
            current_atr = float(atr.iloc[current])
            if current_atr <= 0:
                continue
            close = closes[current]
            body = abs(close - closes[current - 1])
            if bias in {"neutral", "bearish"} and confirmed_high and self._valid_break(close, confirmed_high.price, body, current_atr, "bullish"):
                event = self._event(data, current, confirmed_high, "BOS" if bias == "neutral" else "CHoCH", "bullish", symbol, timeframe)
                events.append(event)
                bias = "bullish"
                confirmed_high = None
            elif bias in {"neutral", "bullish"} and confirmed_low and self._valid_break(close, confirmed_low.price, body, current_atr, "bearish"):
                event = self._event(data, current, confirmed_low, "BOS" if bias == "neutral" else "CHoCH", "bearish", symbol, timeframe)
                events.append(event)
                bias = "bearish"
                confirmed_low = None
        return events

    def _is_pivot_high(self, highs: np.ndarray, pivot: int) -> bool:
        sl = self.swing_length
        return highs[pivot] > highs[pivot - sl:pivot].max() and highs[pivot] > highs[pivot + 1:pivot + sl + 1].max()

    def _is_pivot_low(self, lows: np.ndarray, pivot: int) -> bool:
        sl = self.swing_length
        return lows[pivot] < lows[pivot - sl:pivot].min() and lows[pivot] < lows[pivot + 1:pivot + sl + 1].min()

    @staticmethod
    def _atr(data: pd.DataFrame, lookback: int = 14) -> pd.Series:
        previous = data["close"].shift(1)
        true_range = pd.concat(
            [data["high"] - data["low"], (data["high"] - previous).abs(), (data["low"] - previous).abs()],
            axis=1,
        ).max(axis=1)
        return true_range.rolling(lookback, min_periods=1).mean()

    @staticmethod
    def _valid_break(close: float, level: float, body: float, atr: float, direction: str) -> bool:
        beyond = close > level if direction == "bullish" else close < level
        return beyond and abs(close - level) >= atr * 0.35 and body >= atr * 0.25

    @staticmethod
    def _swing(data, pivot, confirmation, swing_type, price):
        return SwingPoint(
            index=pivot,
            time=data.index[pivot].to_pydatetime(),
            price=float(price),
            swing_type=swing_type,
            is_confirmed=True,
            strength_score=50.0,
            swing_scale="external",
            confirmation_index=confirmation,
        )

    @staticmethod
    def _event(data, index, swing, event_type, direction, symbol, timeframe):
        return MarketStructureEvent(
            event_type=event_type,
            direction=direction,
            broken_swing=swing,
            break_candle_index=index,
            break_candle_time=data.index[index].to_pydatetime(),
            break_price=float(data["close"].iloc[index]),
            symbol=symbol,
            timeframe=timeframe,
        )
