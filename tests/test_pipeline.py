from types import SimpleNamespace

import pandas as pd

from src.core.pipeline import run_full_pipeline
from src.liquidity_engine.levels import LiquidityLevel
from src.liquidity_engine.sweep_detector import LiquiditySweep
from src.smc_engine.fvg import FairValueGap
from src.smc_engine.order_block import OrderBlock


def _frame() -> pd.DataFrame:
    """Create a synthetic OHLC frame for pipeline execution."""
    return pd.DataFrame(
        {"open": [100.0] * 30, "high": [101.0] * 30, "low": [99.0] * 30, "close": [100.0] * 30},
        index=pd.date_range("2024-01-01", periods=30, freq="5min", tz="UTC"),
    )


def test_pipeline_returns_no_trade_on_neutral_htf(tmp_path) -> None:
    """A neutral higher timeframe must stop the pipeline before setup generation."""
    signal = run_full_pipeline("XAUUSD", _frame(), _frame(), 10000.0, 1.0, 10.0, str(tmp_path / "neutral.sqlite"))
    assert signal.direction == "no_trade"


def _event(direction: str) -> SimpleNamespace:
    """Build a synthetic structure event for aligned pipeline tests."""
    return SimpleNamespace(
        direction=direction,
        event_type="BOS",
        break_candle_time=pd.Timestamp("2024-01-01", tz="UTC"),
        broken_swing=SimpleNamespace(price=100.0, swing_type="high"),
    )


def test_pipeline_returns_signal_on_aligned_setup(monkeypatch, tmp_path) -> None:
    """An aligned synthetic confluence setup produces an executable signal."""
    import src.core.pipeline as pipeline

    monkeypatch.setattr(pipeline.CausalMarketStructureEngine, "analyze", lambda self, frame, symbol, timeframe: [_event("bullish")])
    sweep = LiquiditySweep(LiquidityLevel("PDL", 99.0, pd.Timestamp("2024-01-01", tz="UTC")), 1, pd.Timestamp("2024-01-01", tz="UTC"), True, 2, 1.0, 1.0)
    ob = OrderBlock("ob", "bullish", 101.0, 100.0, pd.Timestamp("2024-01-01", tz="UTC"), 3, True, True, True, True, False, 100.0)
    fvg = FairValueGap("fvg", "bullish", 101.0, 100.0, pd.Timestamp("2024-01-01", tz="UTC"), 3, 1.0, 1.0, "none", False, 60.0)
    monkeypatch.setattr(pipeline, "detect_sweeps", lambda df, levels, atr: [sweep])
    monkeypatch.setattr(pipeline, "detect_order_blocks", lambda df, atr, sweeps, direction: [ob])
    monkeypatch.setattr(pipeline, "detect_fvgs", lambda df, atr, direction: [fvg])
    signal = run_full_pipeline("XAUUSD", _frame(), _frame(), 10000.0, 1.0, 10.0, str(tmp_path / "aligned.sqlite"))
    assert signal.direction == "buy"


def test_pipeline_saves_to_database_when_signal_generated(monkeypatch, tmp_path) -> None:
    """Executable pipeline signals are persisted as trade setups."""
    import src.core.pipeline as pipeline

    monkeypatch.setattr(pipeline.CausalMarketStructureEngine, "analyze", lambda self, frame, symbol, timeframe: [_event("bullish")])
    sweep = LiquiditySweep(LiquidityLevel("PDL", 99.0, pd.Timestamp("2024-01-01", tz="UTC")), 1, pd.Timestamp("2024-01-01", tz="UTC"), True, 2, 1.0, 1.0)
    ob = OrderBlock("ob", "bullish", 101.0, 100.0, pd.Timestamp("2024-01-01", tz="UTC"), 3, True, True, True, True, False, 100.0)
    fvg = FairValueGap("fvg", "bullish", 101.0, 100.0, pd.Timestamp("2024-01-01", tz="UTC"), 3, 1.0, 1.0, "none", False, 60.0)
    monkeypatch.setattr(pipeline, "detect_sweeps", lambda df, levels, atr: [sweep])
    monkeypatch.setattr(pipeline, "detect_order_blocks", lambda df, atr, sweeps, direction: [ob])
    monkeypatch.setattr(pipeline, "detect_fvgs", lambda df, atr, direction: [fvg])
    db_path = tmp_path / "pipeline.sqlite"
    signal = run_full_pipeline("XAUUSD", _frame(), _frame(), 10000.0, 1.0, 10.0, str(db_path))
    assert signal.direction == "buy"
    import sqlite3
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trade_setups").fetchone()[0] == 1
