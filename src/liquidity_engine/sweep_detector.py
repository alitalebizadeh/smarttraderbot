from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.liquidity_engine.levels import LiquidityLevel


@dataclass(frozen=True)
class LiquiditySweep:
    """A confirmed liquidity sweep event with a rejection and immediate confirmation."""

    level: LiquidityLevel
    sweep_candle_index: int
    sweep_time: pd.Timestamp
    rejection_confirmed: bool
    confirmation_candle_index: int
    wick_size: float
    strength: float


def detect_sweeps(
    df: pd.DataFrame,
    levels: list[LiquidityLevel],
    atr: pd.Series,
) -> list[LiquiditySweep]:
    """Detect valid sweeps only when wick, close-back, and next-candle confirmation are all present."""
    if df is None or df.empty or not {"high", "low", "close", "open"}.issubset(df.columns):
        return []
    if not levels:
        return []

    data = df.copy()
    data.index = pd.to_datetime(data.index, utc=True, errors="raise")
    results: list[LiquiditySweep] = []

    for idx in range(1, len(data) - 1):
        current_atr = float(atr.iloc[idx]) if idx < len(atr) else 0.0
        if current_atr <= 0:
            continue
        for level in levels:
            level_price = float(level.price)
            wick_size = 0.0
            close = float(data["close"].iloc[idx])
            high = float(data["high"].iloc[idx])
            low = float(data["low"].iloc[idx])
            next_close = float(data["close"].iloc[idx + 1])

            if level.level_type in {"PDH", "WH", "EQH"}:
                if high <= level_price:
                    continue
                wick_size = high - level_price
                if close >= level_price:
                    continue
                if next_close >= close:
                    continue
                strength = min(wick_size / current_atr, 1.0)
                results.append(
                    LiquiditySweep(
                        level=level,
                        sweep_candle_index=idx,
                        sweep_time=data.index[idx],
                        rejection_confirmed=True,
                        confirmation_candle_index=idx + 1,
                        wick_size=wick_size,
                        strength=strength,
                    )
                )
            elif level.level_type in {"PDL", "WL", "EQL"}:
                if low >= level_price:
                    continue
                wick_size = level_price - low
                if close <= level_price:
                    continue
                if next_close <= close:
                    continue
                strength = min(wick_size / current_atr, 1.0)
                results.append(
                    LiquiditySweep(
                        level=level,
                        sweep_candle_index=idx,
                        sweep_time=data.index[idx],
                        rejection_confirmed=True,
                        confirmation_candle_index=idx + 1,
                        wick_size=wick_size,
                        strength=strength,
                    )
                )
    return results
