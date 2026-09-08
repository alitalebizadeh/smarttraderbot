from types import SimpleNamespace

import pandas as pd

from src.decision_engine.engine import generate_signal
from src.decision_engine.signal import TradeSignal
from src.liquidity_engine.levels import LiquidityLevel
from src.liquidity_engine.sweep_detector import LiquiditySweep
from src.mtf_engine import check_alignment, compute_bias
from src.smc_engine.fvg import FairValueGap
from src.smc_engine.order_block import OrderBlock


def _alignment(direction: str = "bullish", aligned: bool = True):
    higher = compute_bias([SimpleNamespace(direction=direction, event_type="BOS", break_candle_time=pd.Timestamp("2024-01-01", tz="UTC"))], "H4")
    lower_direction = direction if aligned else ("bearish" if direction == "bullish" else "bullish")
    lower = compute_bias([SimpleNamespace(direction=lower_direction, event_type="BOS", break_candle_time=pd.Timestamp("2024-01-01", tz="UTC"))], "M15")
    return check_alignment(higher, lower, "XAUUSD")


def _objects():
    timestamp = pd.Timestamp("2024-01-01", tz="UTC")
    ob = OrderBlock("ob-1", "bullish", 101.0, 100.0, timestamp, 2, True, True, True, True, False, 100.0)
    fvg = FairValueGap("fvg-1", "bullish", 101.0, 100.0, timestamp, 2, 1.0, 1.0, "none", False, 60.0)
    level = LiquidityLevel("PDL", 99.0, timestamp)
    sweep = LiquiditySweep(level, 1, timestamp, True, 2, 1.0, 1.0)
    return ob, fvg, sweep


def test_signal_generated_all_conditions_met() -> None:
    """All alignment, confluence, sweep, and risk conditions generate a buy signal."""
    ob, fvg, sweep = _objects()
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [ob], [fvg], [sweep], _alignment())
    assert signal.direction == "buy"
    assert signal.risk_reward_1 == 2.0
    assert signal.confidence == 1.0


def test_no_trade_mtf_not_aligned() -> None:
    """A conflicting MTF alignment blocks signal generation."""
    ob, fvg, sweep = _objects()
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [ob], [fvg], [sweep], _alignment(aligned=False))
    assert signal.direction == "no_trade"


def test_no_trade_ob_score_too_low() -> None:
    """An order block below the score threshold cannot create a signal."""
    _, fvg, sweep = _objects()
    ob = OrderBlock("ob-1", "bullish", 101.0, 100.0, pd.Timestamp("2024-01-01", tz="UTC"), 2, True, True, True, True, False, 70.0)
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [ob], [fvg], [sweep], _alignment())
    assert signal.direction == "no_trade"


def test_no_trade_no_fvg_overlap() -> None:
    """A non-overlapping unfilled FVG blocks the setup."""
    ob, _, sweep = _objects()
    fvg = FairValueGap("fvg-1", "bullish", 103.0, 102.0, pd.Timestamp("2024-01-01", tz="UTC"), 2, 1.0, 1.0, "none", False, 60.0)
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [ob], [fvg], [sweep], _alignment())
    assert signal.direction == "no_trade"


def test_no_trade_rr_below_minimum() -> None:
    """A requested minimum above the prescribed TP1 reward rejects the signal."""
    ob, fvg, sweep = _objects()
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [ob], [fvg], [sweep], _alignment(), rr_minimum=3.0)
    assert signal.direction == "no_trade"


def test_reasoning_list_populated_on_rejection() -> None:
    """Rejected signals explain the failed prerequisite in ordered reasoning."""
    signal = generate_signal("XAUUSD", pd.DataFrame(), pd.Series(dtype=float), [], [], [], _alignment())
    assert signal.direction == "no_trade"
    assert signal.reasoning
    assert any("OrderBlock" in reason for reason in signal.reasoning)
