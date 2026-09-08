from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.backtester import BacktestTrade


@dataclass(frozen=True)
class PerformanceMetrics:
    trade_count: int
    win_rate: float
    profit_factor: float | None
    net_profit: float
    max_drawdown: float
    average_pnl: float
    equity_curve: tuple[float, ...]


class PerformanceAnalyzer:
    """Calculate descriptive metrics from completed replay trades."""

    def summarize(self, trades: Iterable[BacktestTrade], initial_equity: float = 0.0) -> PerformanceMetrics:
        if initial_equity < 0:
            raise ValueError("initial_equity cannot be negative")
        trade_list = list(trades)
        equity = initial_equity
        curve = [equity]
        gross_profit = 0.0
        gross_loss = 0.0
        wins = 0
        peak = equity
        max_drawdown = 0.0
        for trade in trade_list:
            equity += trade.net_pnl
            curve.append(equity)
            if trade.net_pnl > 0:
                gross_profit += trade.net_pnl
                wins += 1
            elif trade.net_pnl < 0:
                gross_loss += abs(trade.net_pnl)
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return PerformanceMetrics(
            trade_count=len(trade_list),
            win_rate=wins / len(trade_list) if trade_list else 0.0,
            profit_factor=(gross_profit / gross_loss) if gross_loss else None,
            net_profit=equity - initial_equity,
            max_drawdown=max_drawdown,
            average_pnl=(equity - initial_equity) / len(trade_list) if trade_list else 0.0,
            equity_curve=tuple(curve),
        )
