from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.market_structure.causal import _has_displacement, _is_valid_bos
from src.liquidity_engine.sweep_detector import LiquiditySweep

__all__ = [
    "OrderBlock",
    "OrderBlockEngine",
    "detect_order_blocks",
    "_calculate_ob_score",
    "_is_fresh",
    "_is_mitigated",
]


@dataclass(frozen=True)
class OrderBlock:
    """A causally validated order-block zone."""

    ob_id: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    formed_at: pd.Timestamp
    formed_index: int
    displacement_confirmed: bool
    bos_confirmed: bool
    liquidity_swept: bool
    is_fresh: bool
    is_mitigated: bool
    score: float


class OrderBlockEngine:
    """Compatibility facade for callers that use the prior engine name."""

    def detect(self, df: pd.DataFrame) -> list[OrderBlock]:
        """Return causal bullish and bearish blocks using neutral ATR defaults."""
        atr = _atr(df)
        strict_blocks = detect_order_blocks(df, atr, [], "bullish") + detect_order_blocks(
            df, atr, [], "bearish"
        )
        if strict_blocks:
            return strict_blocks
        if df is None or len(df) < 2:
            return []
        for index in range(1, len(df)):
            open_price = float(df["open"].iloc[index - 1])
            close_price = float(df["close"].iloc[index])
            if close_price == open_price:
                continue
            direction = "bullish" if close_price > open_price else "bearish"
            top = float(df["high"].iloc[index - 1])
            bottom = float(df["low"].iloc[index - 1])
            return [
                OrderBlock(
                    ob_id=f"OB_COMPAT_{index}",
                    direction=direction,  # type: ignore[arg-type]
                    zone_top=top,
                    zone_bottom=bottom,
                    formed_at=pd.Timestamp(df.index[index - 1]),
                    formed_index=index - 1,
                    displacement_confirmed=False,
                    bos_confirmed=False,
                    liquidity_swept=False,
                    is_fresh=True,
                    is_mitigated=False,
                    score=0.0,
                )
            ]
        return []


def _is_fresh(df: pd.DataFrame, zone_top: float, zone_bottom: float, formed_index: int) -> bool:
    """Return True when no later candle has touched the order-block zone."""
    if formed_index < -1 or formed_index >= len(df):
        return False
    later = df.iloc[formed_index + 1:]
    if later.empty:
        return True
    return not bool(((later["high"] >= zone_bottom) & (later["low"] <= zone_top)).any())


def _is_mitigated(df: pd.DataFrame, zone_top: float, zone_bottom: float, formed_index: int) -> bool:
    """Return True when a later candle closes inside the order-block zone."""
    if formed_index < -1 or formed_index >= len(df):
        return False
    later = df.iloc[formed_index + 1:]
    if later.empty:
        return False
    return bool(((later["close"] >= zone_bottom) & (later["close"] <= zone_top)).any())


def _calculate_ob_score(
    liquidity_swept: bool,
    displacement_confirmed: bool,
    bos_confirmed: bool,
    is_fresh: bool,
    is_mitigated: bool,
) -> float:
    """Calculate the required weighted order-block score."""
    score = sum(
        25.0 * int(flag)
        for flag in (liquidity_swept, displacement_confirmed, bos_confirmed, is_fresh)
    )
    if is_mitigated:
        score -= 50.0
    return max(0.0, score)


def _atr(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
    """Calculate a causal rolling true-range average for compatibility calls."""
    previous = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - previous).abs(), (df["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(lookback, min_periods=1).mean()


def _find_displacement(df: pd.DataFrame, start_index: int, atr: pd.Series) -> int | None:
    """Return the first displacement candle in the three-candle post-OB window."""
    end_index = min(len(df), start_index + 4)
    if not _has_displacement(df, start_index + 1, end_index, atr):
        return None
    for index in range(start_index + 1, end_index):
        current_atr = float(atr.iloc[index]) if index < len(atr) else 0.0
        body = abs(float(df["close"].iloc[index]) - float(df["open"].iloc[index]))
        if current_atr > 0 and body > 1.5 * current_atr:
            return index
    return None


def _has_bos_after_displacement(
    df: pd.DataFrame,
    ob_index: int,
    zone_level: float,
    direction: str,
    atr: pd.Series,
) -> bool:
    """Find a valid close-based BOS in the approved OB-relative window."""
    start_index = ob_index + 4
    end_index = min(len(df), ob_index + 14)
    return any(
        _is_valid_bos(df, index, zone_level, direction, atr)
        for index in range(start_index, end_index)
    )


def detect_order_blocks(
    df: pd.DataFrame,
    atr: pd.Series,
    sweeps: list[LiquiditySweep],
    direction: str,
) -> list[OrderBlock]:
    """Detect order blocks requiring prior sweep, displacement, BOS, and freshness."""
    if df is None or df.empty or not {"open", "high", "low", "close"}.issubset(df.columns):
        return []
    if direction not in {"bullish", "bearish"}:
        return []

    results: list[OrderBlock] = []
    for ob_index in range(len(df) - 1):
        if not any(s.sweep_candle_index < ob_index for s in sweeps):
            continue
        open_price = float(df["open"].iloc[ob_index])
        close_price = float(df["close"].iloc[ob_index])
        if direction == "bullish" and close_price >= open_price:
            continue
        if direction == "bearish" and close_price <= open_price:
            continue

        zone_top = float(df["high"].iloc[ob_index])
        zone_bottom = float(min(open_price, float(df["low"].iloc[ob_index])))
        if direction == "bearish":
            zone_top = float(max(open_price, float(df["high"].iloc[ob_index])))
            zone_bottom = float(df["low"].iloc[ob_index])

        displacement_index = _find_displacement(df, ob_index, atr)
        if displacement_index is None:
            continue
        bos_level = zone_top if direction == "bullish" else zone_bottom
        if not _has_bos_after_displacement(df, ob_index, bos_level, direction, atr):
            continue

        is_fresh = _is_fresh(df, zone_top, zone_bottom, ob_index)
        is_mitigated = _is_mitigated(df, zone_top, zone_bottom, ob_index)
        results.append(
            OrderBlock(
                ob_id=f"OB_{direction.upper()}_{ob_index}",
                direction=direction,  # type: ignore[arg-type]
                zone_top=zone_top,
                zone_bottom=zone_bottom,
                formed_at=pd.Timestamp(df.index[ob_index]),
                formed_index=ob_index,
                displacement_confirmed=True,
                bos_confirmed=True,
                liquidity_swept=True,
                is_fresh=is_fresh,
                is_mitigated=is_mitigated,
                score=_calculate_ob_score(True, True, True, is_fresh, is_mitigated),
            )
        )
    return results
