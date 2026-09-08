from __future__ import annotations

from typing import Literal

import pandas as pd

Regime = Literal["trending", "ranging", "high_volatility", "low_volatility"]


def classify_regime(
    candles: pd.DataFrame,
    *,
    return_window: int = 20,
    volatility_threshold: float = 0.02,
    trend_threshold: float = 0.01,
) -> Regime:
    """Classify the latest completed window using returns and realized volatility."""
    if candles is None or "close" not in candles or len(candles) < return_window + 1:
        raise ValueError("regime classification requires a sufficient close series")
    close = pd.to_numeric(candles["close"], errors="raise").tail(return_window + 1)
    returns = close.pct_change().dropna()
    volatility = float(returns.std(ddof=0))
    displacement = abs(float(close.iloc[-1] / close.iloc[0] - 1.0))
    if volatility >= volatility_threshold:
        return "high_volatility"
    if displacement >= trend_threshold:
        return "trending"
    return "low_volatility" if volatility < volatility_threshold / 2 else "ranging"
