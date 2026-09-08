from types import SimpleNamespace

import pandas as pd
import pytest

from src.decision_engine.signal import TradeSignal
from src.mtf_engine import check_alignment, compute_bias
from src.risk_engine.position_sizer import PositionSize, calculate_position_size
from src.risk_engine.trade_manager import TradeState, apply_breakeven, apply_trailing_stop


def _signal(direction: str = "buy") -> TradeSignal:
    """Build a minimal mutable signal for trade-state tests."""
    higher = compute_bias([SimpleNamespace(direction="bullish", event_type="BOS", break_candle_time=pd.Timestamp("2024-01-01", tz="UTC"))], "H4")
    alignment = check_alignment(higher, higher, "XAUUSD")
    return TradeSignal("sig", "XAUUSD", direction, 100.0, 99.0, 102.0, 103.0, 2.0, 3.0, 0.8, [], pd.Timestamp("2024-01-01", tz="UTC"), None, None, None, alignment)


def test_position_size_correct_calculation() -> None:
    """Percentage risk and pip distance produce the expected rounded lot size."""
    result = calculate_position_size(10000.0, 1.0, 100.0, 98.0, 10.0, "XAUUSD")
    assert result.risk_amount == 100.0
    assert result.pip_risk == 200.0
    assert result.lot_size == 0.05


def test_position_size_raises_on_zero_balance() -> None:
    """Non-positive account balance is rejected."""
    with pytest.raises(ValueError):
        calculate_position_size(0.0, 1.0, 100.0, 98.0, 10.0, "XAUUSD")


def test_position_size_raises_on_high_risk_pct() -> None:
    """Risk percentages above ten percent are rejected."""
    with pytest.raises(ValueError):
        calculate_position_size(10000.0, 10.1, 100.0, 98.0, 10.0, "XAUUSD")


def test_breakeven_activates_at_correct_rr() -> None:
    """Breakeven activates once current price reaches the configured RR."""
    state = TradeState(_signal(), PositionSize("XAUUSD", 10000.0, 1.0, 100.0, 100.0, 99.0, 100.0, 0.1, 10.0), "open", 101.0, 100.0, False, False)
    updated = apply_breakeven(state)
    assert updated.breakeven_activated is True
    assert updated.signal.stop_loss == 100.0


def test_trailing_stop_moves_in_favorable_direction() -> None:
    """A bullish trailing stop moves upward behind a favorable price move."""
    state = TradeState(_signal(), PositionSize("XAUUSD", 10000.0, 1.0, 100.0, 100.0, 99.0, 100.0, 0.1, 10.0), "open", 103.0, 300.0, False, False)
    updated = apply_trailing_stop(state, 1.0)
    assert updated.signal.stop_loss == 101.5


def test_trailing_stop_never_moves_against_trade() -> None:
    """A trailing stop never lowers an already higher bullish stop."""
    signal = _signal()
    signal.stop_loss = 102.0
    state = TradeState(signal, PositionSize("XAUUSD", 10000.0, 1.0, 100.0, 100.0, 102.0, 100.0, 0.1, 10.0), "open", 103.0, 300.0, False, False)
    updated = apply_trailing_stop(state, 1.0)
    assert updated.signal.stop_loss == 102.0
