from datetime import datetime, timezone

from src.analytics import PerformanceAnalyzer
from src.backtester import BacktestTrade
from src.database import SQLiteStore


def _trade(pnl: float, result: str) -> BacktestTrade:
    now = datetime.now(timezone.utc)
    return BacktestTrade(
        symbol="XAUUSD",
        direction="BUY",
        entry_time=now,
        entry_price=100.0,
        exit_time=now,
        exit_price=101.0,
        result=result,
        gross_pnl=pnl,
        costs=0.0,
        net_pnl=pnl,
        exit_reason="TP" if result == "WIN" else "SL",
    )


def test_performance_metrics_are_derived_from_trades() -> None:
    metrics = PerformanceAnalyzer().summarize([_trade(2.0, "WIN"), _trade(-1.0, "LOSS")], initial_equity=100.0)

    assert metrics.trade_count == 2
    assert metrics.win_rate == 0.5
    assert metrics.profit_factor == 2.0
    assert metrics.net_profit == 1.0
    assert metrics.max_drawdown == 1.0
    assert metrics.equity_curve == (100.0, 102.0, 101.0)


def test_sqlite_store_persists_trades(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "trades.sqlite")
    store.save_trade(_trade(1.0, "WIN"))
    store.save_backtest_run({"source": "test"})

    assert store.count("trades") == 1
    assert store.count("backtest_runs") == 1
