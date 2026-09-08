from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class LiquidityLevel:
    """A completed liquidity level from a daily, weekly, or equal-price cluster."""

    level_type: str
    price: float
    formed_at: pd.Timestamp
    is_swept: bool = False


def detect_previous_day_levels(df: pd.DataFrame) -> list[LiquidityLevel]:
    """Return completed daily high/low levels for each full day in the provided dataset."""
    if df is None or df.empty or not {"high", "low"}.issubset(df.columns):
        return []

    data = df.copy()
    data.index = pd.to_datetime(data.index, utc=True, errors="raise")
    if not isinstance(data.index, pd.DatetimeIndex):
        return []

    day_groups = list(data.groupby(data.index.normalize()))
    if len(day_groups) < 2:
        return []

    levels: list[LiquidityLevel] = []
    for _, group in day_groups[:-1]:
        pdh = float(group["high"].max())
        pdl = float(group["low"].min())
        levels.append(LiquidityLevel("PDH", pdh, group.index.max(), False))
        levels.append(LiquidityLevel("PDL", pdl, group.index.max(), False))
    return levels


def detect_weekly_levels(df: pd.DataFrame) -> list[LiquidityLevel]:
    """Return completed weekly high/low levels for each ISO week in the provided dataset."""
    if df is None or df.empty or not {"high", "low"}.issubset(df.columns):
        return []

    data = df.copy()
    data.index = pd.to_datetime(data.index, utc=True, errors="raise")
    if not isinstance(data.index, pd.DatetimeIndex):
        return []

    week_groups = list(data.groupby([data.index.year, data.index.isocalendar().week]))
    if len(week_groups) < 2:
        return []

    levels: list[LiquidityLevel] = []
    for _, group in week_groups[:-1]:
        wh = float(group["high"].max())
        wl = float(group["low"].min())
        levels.append(LiquidityLevel("WH", wh, group.index.max(), False))
        levels.append(LiquidityLevel("WL", wl, group.index.max(), False))
    return levels


def _group_levels(
    values: list[float],
    timestamps: list[pd.Timestamp],
    threshold_pct: float,
    level_type: str,
) -> list[LiquidityLevel]:
    """Group nearby values and build equal-high / equal-low levels."""
    if len(values) < 2 or threshold_pct <= 0:
        return []

    groups: list[list[tuple[float, pd.Timestamp]]] = []
    for value, ts in zip(values, timestamps):
        assigned = False
        for group in groups:
            group_average = sum(item[0] for item in group) / len(group)
            pct = abs(value - group_average) / group_average * 100.0 if group_average else 0.0
            if pct <= threshold_pct * 100.0:
                group.append((value, ts))
                assigned = True
                break
        if not assigned:
            groups.append([(value, ts)])

    results: list[LiquidityLevel] = []
    for group in groups:
        if len(group) < 2:
            continue
        avg_price = sum(item[0] for item in group) / len(group)
        formed_at = max(ts for _, ts in group)
        results.append(LiquidityLevel(level_type, avg_price, formed_at, False))
    return results


def detect_equal_highs(
    df: pd.DataFrame,
    swing_highs: list[float],
    swing_high_times: list[pd.Timestamp],
    threshold_pct: float = 0.001,
) -> list[LiquidityLevel]:
    """Return equal-high clusters found from swing highs within the threshold."""
    del df
    return _group_levels(swing_highs, swing_high_times, threshold_pct, "EQH")


def detect_equal_lows(
    df: pd.DataFrame,
    swing_lows: list[float],
    swing_low_times: list[pd.Timestamp],
    threshold_pct: float = 0.001,
) -> list[LiquidityLevel]:
    """Return equal-low clusters found from swing lows within the threshold."""
    del df
    return _group_levels(swing_lows, swing_low_times, threshold_pct, "EQL")
