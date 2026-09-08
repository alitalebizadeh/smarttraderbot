from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BacktestReport:
    """Performance summary calculated from completed replay trades."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    average_rr: float
    expectancy: float
    equity_curve: list[float]


def calculate_metrics(trades: list, initial_balance: float) -> BacktestReport:
    """Calculate performance metrics from actual trade PnL values."""
    if not trades:
        return BacktestReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [initial_balance])
    pnls = [float(getattr(trade, "pnl_pct", 0.0)) for trade in trades]
    winners = [value for value in pnls if value > 0]
    losers = [value for value in pnls if value < 0]
    equity = [initial_balance]
    for value in pnls:
        equity.append(equity[-1] * (1.0 + value / 100.0))
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak * 100.0)
    mean = sum(pnls) / len(pnls)
    variance = sum((value - mean) ** 2 for value in pnls) / len(pnls)
    deviation = math.sqrt(variance)
    sharpe = mean / deviation * math.sqrt(252.0) if deviation else 0.0
    win_rate = len(winners) / len(pnls)
    average_win = sum(winners) / len(winners) if winners else 0.0
    average_loss = abs(sum(losers) / len(losers)) if losers else 0.0
    expectancy = win_rate * average_win - (1.0 - win_rate) * average_loss
    return BacktestReport(
        total_trades=len(pnls),
        winning_trades=len(winners),
        losing_trades=len(losers),
        win_rate=win_rate,
        profit_factor=sum(winners) / abs(sum(losers)) if losers else float("inf") if winners else 0.0,
        max_drawdown_pct=drawdown,
        sharpe_ratio=sharpe,
        average_rr=sum(float(getattr(trade, "rr_achieved", 0.0)) for trade in trades) / len(trades),
        expectancy=expectancy,
        equity_curve=equity,
    )
