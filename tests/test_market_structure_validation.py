from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.engine.market_structure_engine import MarketStructureEngine
from src.models.market_structure import SwingPoint


def _build_df_with_step(base: float = 100.0, start: int = 0, size: int = 30, step: float = 0.2) -> pd.DataFrame:
    rows = []
    for idx in range(size):
        current = base + step * (idx - start)
        rows.append(
            {
                "open": current,
                "high": current + 0.35,
                "low": current - 0.35,
                "close": current,
                "volume": 1,
            }
        )
    return pd.DataFrame(rows)


def test_bos_requires_real_break_beyond_atr_threshold() -> None:
    engine = MarketStructureEngine(swing_length=2)
    df = _build_df_with_step(base=100.0, size=20, step=0.05)
    swing = SwingPoint(
        index=5,
        time=datetime.now(tz=timezone.utc),
        price=100.0,
        swing_type="high",
        is_confirmed=True,
    )

    events, bias = engine._detect_events(df, [swing], [], symbol="XAUUSD", timeframe="H1")

    assert events == []
    assert bias in {"neutral", "bullish"}


def test_valid_bos_is_accepted_when_break_exceeds_atr_and_displacement() -> None:
    engine = MarketStructureEngine(swing_length=2)
    df = _build_df_with_step(base=100.0, size=30, step=0.01)
    df.loc[15, "close"] = 101.5
    df.loc[15, "high"] = 101.6
    df.loc[15, "low"] = 101.4
    df.loc[16, "close"] = 101.7
    df.loc[16, "high"] = 101.8
    df.loc[16, "low"] = 101.5
    swing = SwingPoint(index=5, time=datetime.now(tz=timezone.utc), price=100.0, swing_type="high", is_confirmed=True)

    events, bias = engine._detect_events(df, [swing], [], symbol="XAUUSD", timeframe="H1")

    assert any(event.event_type == "BOS" and event.direction == "bullish" for event in events)
    assert bias in {"bullish", "neutral"}


def test_fake_breakout_is_rejected() -> None:
    engine = MarketStructureEngine(swing_length=2)
    df = _build_df_with_step(base=100.0, size=20, step=0.005)
    df.loc[10, "close"] = 100.04
    df.loc[10, "high"] = 100.05
    df.loc[10, "low"] = 100.03
    swing = SwingPoint(index=5, time=datetime.now(tz=timezone.utc), price=100.0, swing_type="high", is_confirmed=True)

    events, _ = engine._detect_events(df, [swing], [], symbol="XAUUSD", timeframe="H1")

    assert events == []


def test_liquidity_grab_can_trigger_choch() -> None:
    engine = MarketStructureEngine(swing_length=2)
    df = _build_df_with_step(base=100.0, size=25, step=0.04)
    for idx in range(12, 16):
        df.loc[idx, "low"] = 99.1
    df.loc[18, "close"] = 101.1
    df.loc[18, "high"] = 101.2
    df.loc[18, "low"] = 100.8
    df.loc[19, "close"] = 101.3
    df.loc[19, "high"] = 101.4
    df.loc[19, "low"] = 101.0
    swing_high = SwingPoint(index=4, time=datetime.now(tz=timezone.utc), price=101.0, swing_type="high", is_confirmed=True)
    swing_low = SwingPoint(index=10, time=datetime.now(tz=timezone.utc), price=99.3, swing_type="low", is_confirmed=True)

    events, bias = engine._detect_events(df, [swing_high], [swing_low], symbol="XAUUSD", timeframe="H1")

    assert any(event.event_type == "CHoCH" and event.direction == "bullish" for event in events)
    assert bias in {"bullish", "neutral"}


def test_weak_break_rejected_even_if_close_is_above_level() -> None:
    engine = MarketStructureEngine(swing_length=2)
    df = _build_df_with_step(base=100.0, size=25, step=0.01)
    df.loc[12, "close"] = 100.02
    df.loc[12, "high"] = 100.03
    df.loc[12, "low"] = 100.01
    swing = SwingPoint(index=5, time=datetime.now(tz=timezone.utc), price=100.0, swing_type="high", is_confirmed=True)

    events, _ = engine._detect_events(df, [swing], [], symbol="XAUUSD", timeframe="H1")

    assert events == []
