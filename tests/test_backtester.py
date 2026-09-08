from datetime import datetime, timezone

import pandas as pd
import pytest

from src.backtester import ExecutionConfig, HistoricalReplay
from src.decision_engine import TradeSignal


def _signal() -> TradeSignal:
    return TradeSignal(
        symbol="XAUUSD",
        direction="BUY",
        entry=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        risk_reward=2.0,
        confidence=80.0,
        reasoning=("test",),
        timeframe="M5",
        timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
    )


def test_replay_uses_candle_after_signal_and_hits_target() -> None:
    candles = pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [101, 105, 103],
            "low": [99, 100, 101],
            "close": [100, 104, 102],
        },
        index=pd.to_datetime([
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:05:00Z",
            "2024-01-01T00:10:00Z",
        ]),
    )

    trade = HistoricalReplay(ExecutionConfig(commission_per_unit=0.1)).replay(_signal(), candles)

    assert trade.result == "WIN"
    assert trade.exit_reason == "TP"
    assert trade.entry_time == candles.index[1]
    assert trade.net_pnl == pytest.approx(2.9)


def test_same_candle_sl_and_tp_uses_conservative_stop() -> None:
    candles = pd.DataFrame(
        {"open": [100], "high": [105], "low": [95], "close": [100]},
        index=pd.to_datetime(["2024-01-01T00:05:00Z"]),
    )
    signal = _signal()
    trade = HistoricalReplay().replay(signal, candles.loc[candles.index > signal.timestamp])

    assert trade.result == "LOSS"
    assert trade.exit_reason == "SL"
