from types import SimpleNamespace

import pandas as pd

from src.backtester.metrics import calculate_metrics
from src.backtester.replay import run_backtest
from src.risk_engine.position_sizer import calculate_position_size


def _signal(formed_at: str = "2024-01-01T00:00:00Z") -> SimpleNamespace:
    """Create a synthetic executable buy signal."""
    return SimpleNamespace(
        direction="buy", symbol="XAUUSD", formed_at=pd.Timestamp(formed_at),
        entry_price=100.0, stop_loss=99.0, take_profit_1=102.0, take_profit_2=103.0,
    )


def _frame() -> pd.DataFrame:
    """Create deterministic post-signal candles."""
    return pd.DataFrame(
        {"open": [99.5, 100.0, 100.5], "high": [100.5, 102.5, 104.0], "low": [99.2, 99.8, 100.4], "close": [100.0, 102.0, 103.5]},
        index=pd.date_range("2024-01-01T00:00:00Z", periods=3, freq="5min"),
    )


def test_trade_entry_not_before_signal_time() -> None:
    """The replay must select only candles strictly after signal formation."""
    trades = run_backtest(_frame(), [_signal()], calculate_position_size, 10000.0, 1.0, 10.0)
    assert trades[0].entry_time == _frame().index[1]


def test_sl_taken_when_candle_hits_both_sl_and_tp() -> None:
    """A same-candle stop and target collision resolves conservatively to SL."""
    frame = _frame()
    frame.iloc[1, frame.columns.get_loc("high")] = 102.5
    frame.iloc[1, frame.columns.get_loc("low")] = 98.5
    signal = _signal()
    signal.take_profit_1 = 102.0
    trades = run_backtest(frame, [signal], calculate_position_size, 10000.0, 1.0, 10.0)
    assert trades[0].exit_reason == "sl"


def test_tp1_exit_recorded_correctly() -> None:
    """A target-one hit records TP1 and its realized reward."""
    trades = run_backtest(_frame(), [_signal()], calculate_position_size, 10000.0, 1.0, 10.0)
    assert trades[0].exit_reason == "tp1"
    assert trades[0].rr_achieved == 2.0


def test_win_rate_calculated_correctly() -> None:
    """Metrics count positive and negative replay returns accurately."""
    trades = [SimpleNamespace(pnl_pct=2.0, rr_achieved=2.0), SimpleNamespace(pnl_pct=-1.0, rr_achieved=-1.0)]
    assert calculate_metrics(trades, 10000.0).win_rate == 0.5


def test_profit_factor_calculated_correctly() -> None:
    """Profit factor equals gross winning percentage divided by gross losses."""
    trades = [SimpleNamespace(pnl_pct=2.0, rr_achieved=2.0), SimpleNamespace(pnl_pct=-1.0, rr_achieved=-1.0)]
    assert calculate_metrics(trades, 10000.0).profit_factor == 2.0


def test_max_drawdown_calculated_correctly() -> None:
    """Maximum drawdown is measured peak to subsequent equity trough."""
    trades = [SimpleNamespace(pnl_pct=10.0, rr_achieved=2.0), SimpleNamespace(pnl_pct=-20.0, rr_achieved=-1.0)]
    report = calculate_metrics(trades, 10000.0)
    assert report.max_drawdown_pct == 20.0
