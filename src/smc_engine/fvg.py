from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

__all__ = [
    "FairValueGap",
    "FVGEngine",
    "detect_fvgs",
    "_calculate_fvg_score",
    "_classify_fill_status",
    "_is_inverted",
]


@dataclass(frozen=True)
class FairValueGap:
    """A three-candle fair-value gap with causal fill classification."""

    fvg_id: str
    direction: Literal["bullish", "bearish"]
    gap_top: float
    gap_bottom: float
    formed_at: pd.Timestamp
    formed_index: int
    gap_size: float
    gap_size_atr_ratio: float
    fill_status: Literal["none", "partial", "full"]
    is_inverted: bool
    score: float


class FVGEngine:
    """Compatibility facade for callers that use the prior engine name."""

    def __init__(self, min_atr_ratio: float = 0.01) -> None:
        """Configure the compatibility facade's detection threshold."""
        if min_atr_ratio <= 0:
            raise ValueError("min_atr_ratio must be positive")
        self.min_atr_ratio = min_atr_ratio

    def detect(self, df: pd.DataFrame) -> list[FairValueGap]:
        """Return causal bullish and bearish gaps using rolling ATR."""
        atr = _atr(df)
        return detect_fvgs(df, atr, "bullish", min_atr_ratio=self.min_atr_ratio) + detect_fvgs(
            df, atr, "bearish", min_atr_ratio=self.min_atr_ratio
        )


def _classify_fill_status(
    df: pd.DataFrame,
    gap_top: float,
    gap_bottom: float,
    formed_index: int,
    direction: str = "bullish",
) -> str:
    """Classify later price interaction as none, partial, or full fill."""
    for _, candle in df.iloc[formed_index + 2:].iterrows():
        low = float(candle["low"])
        high = float(candle["high"])
        close = float(candle["close"])
        if low <= gap_top and high >= gap_bottom:
            fully_closed = close <= gap_bottom if direction == "bullish" else close >= gap_top
            if fully_closed:
                return "full"
            return "partial"
    return "none"


def _atr(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
    """Calculate a causal rolling true-range average for compatibility calls."""
    previous = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - previous).abs(), (df["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(lookback, min_periods=1).mean()


def _is_inverted(
    df: pd.DataFrame,
    gap_top: float,
    gap_bottom: float,
    formed_index: int,
    direction: str,
    fill_status: str = "full",
) -> bool:
    """Return True when a full fill is followed by rejection from the gap."""
    if fill_status != "full":
        return False
    later = df.iloc[formed_index + 2:]
    full_position: int | None = None
    for position, (_, candle) in enumerate(later.iterrows(), start=formed_index + 2):
        close = float(candle["close"])
        if close <= gap_bottom or close >= gap_top:
            full_position = position
            break
    if full_position is None:
        return False
    post_fill = df.iloc[full_position + 1:]
    if direction == "bullish":
        return bool((post_fill["close"] > gap_bottom).any())
    if direction == "bearish":
        return bool((post_fill["close"] < gap_top).any())
    return False


def _calculate_fvg_score(
    gap_size_atr_ratio: float,
    fill_status: str,
    has_nearby_bos: bool,
    has_nearby_sweep: bool,
) -> float:
    """Calculate the required weighted FVG score."""
    score = 0.0
    score += 30.0 if gap_size_atr_ratio > 1.0 else 0.0
    score += 30.0 if fill_status == "none" else 0.0
    score += 20.0 if has_nearby_bos else 0.0
    score += 20.0 if has_nearby_sweep else 0.0
    return min(100.0, score)


def detect_fvgs(
    df: pd.DataFrame,
    atr: pd.Series,
    direction: str,
    min_atr_ratio: float = 0.3,
) -> list[FairValueGap]:
    """Detect three-candle FVGs whose gap exceeds the ATR-relative threshold."""
    if df is None or df.empty or not {"high", "low", "close"}.issubset(df.columns):
        return []
    if direction not in {"bullish", "bearish"} or min_atr_ratio <= 0:
        return []

    results: list[FairValueGap] = []
    for index in range(1, len(df) - 1):
        current_atr = float(atr.iloc[index]) if index < len(atr) else 0.0
        if current_atr <= 0:
            continue
        if direction == "bullish":
            gap_bottom = float(df["high"].iloc[index - 1])
            gap_top = float(df["low"].iloc[index + 1])
        else:
            gap_top = float(df["low"].iloc[index - 1])
            gap_bottom = float(df["high"].iloc[index + 1])
        gap_size = gap_top - gap_bottom
        ratio = gap_size / current_atr
        if gap_size <= 0 or ratio <= min_atr_ratio:
            continue
        fill_status = _classify_fill_status(df, gap_top, gap_bottom, index, direction)
        results.append(
            FairValueGap(
                fvg_id=f"FVG_{direction.upper()}_{index}",
                direction=direction,  # type: ignore[arg-type]
                gap_top=gap_top,
                gap_bottom=gap_bottom,
                formed_at=pd.Timestamp(df.index[index]),
                formed_index=index,
                gap_size=gap_size,
                gap_size_atr_ratio=ratio,
                fill_status=fill_status,  # type: ignore[arg-type]
                is_inverted=_is_inverted(
                    df, gap_top, gap_bottom, index, direction, fill_status
                ),
                score=_calculate_fvg_score(ratio, fill_status, False, False),
            )
        )
    return results
