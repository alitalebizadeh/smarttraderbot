from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

__all__ = ["LiquidityLevel", "LiquiditySweep", "LiquidityEngine"]


@dataclass(frozen=True)
class LiquidityLevel:
    """A price level associated with liquidity pools or prior swing extremes."""

    level: float
    level_type: Literal["external", "internal"]
    kind: Literal["high", "low"]
    index: int
    time: datetime
    strength: float = 0.0


@dataclass(frozen=True)
class LiquiditySweep:
    """A valid sweep of prior liquidity before rejection or reversal."""

    direction: Literal["bullish", "bearish"]
    level: float
    sweep_index: int
    rejection_index: int | None
    confirmed: bool = False
    reason: str = ""


class LiquidityEngine:
    """Detect external/internal liquidity and liquidity sweeps from OHLCV data."""

    def analyze(self, df: pd.DataFrame) -> dict[str, list]:
        if df is None or df.empty or not {"high", "low", "close"}.issubset(df.columns):
            return {"external": [], "internal": [], "sweeps": []}
        data = df.copy()
        data = data.sort_index()
        recent_high = float(data["high"].iloc[-20:].max()) if len(data) >= 20 else float(data["high"].max())
        recent_low = float(data["low"].iloc[-20:].min()) if len(data) >= 20 else float(data["low"].min())
        external = [
            LiquidityLevel(level=recent_high, level_type="external", kind="high", index=len(data) - 1, time=pd.Timestamp(data.index[-1]).to_pydatetime(), strength=1.0),
            LiquidityLevel(level=recent_low, level_type="external", kind="low", index=len(data) - 1, time=pd.Timestamp(data.index[-1]).to_pydatetime(), strength=1.0),
        ]
        internal = self._internal_levels(data)
        sweeps = self._detect_sweeps(data)
        return {"external": external, "internal": internal, "sweeps": sweeps}

    def _internal_levels(self, df: pd.DataFrame) -> list[LiquidityLevel]:
        levels: list[LiquidityLevel] = []
        for idx in range(5, len(df) - 1):
            window = df.iloc[max(0, idx - 5):idx + 1]
            local_high = float(window["high"].max())
            local_low = float(window["low"].min())
            if abs(float(df["close"].iloc[idx]) - local_high) < 1e-9:
                levels.append(LiquidityLevel(level=local_high, level_type="internal", kind="high", index=idx, time=pd.Timestamp(df.index[idx]).to_pydatetime(), strength=0.6))
            if abs(float(df["close"].iloc[idx]) - local_low) < 1e-9:
                levels.append(LiquidityLevel(level=local_low, level_type="internal", kind="low", index=idx, time=pd.Timestamp(df.index[idx]).to_pydatetime(), strength=0.6))
        return levels

    def _detect_sweeps(self, df: pd.DataFrame) -> list[LiquiditySweep]:
        sweeps: list[LiquiditySweep] = []
        for idx in range(1, len(df)):
            prior_high = float(df["high"].iloc[max(0, idx - 10):idx].max())
            prior_low = float(df["low"].iloc[max(0, idx - 10):idx].min())
            close = float(df["close"].iloc[idx])
            if close > prior_high and float(df["low"].iloc[idx]) <= prior_high:
                sweeps.append(LiquiditySweep(direction="bullish", level=prior_high, sweep_index=idx, rejection_index=idx, confirmed=True, reason="High sweep followed by close above prior high"))
            if close < prior_low and float(df["high"].iloc[idx]) >= prior_low:
                sweeps.append(LiquiditySweep(direction="bearish", level=prior_low, sweep_index=idx, rejection_index=idx, confirmed=True, reason="Low sweep followed by close below prior low"))
        return sweeps
