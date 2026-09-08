from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class MonteCarloResult:
    simulations: int
    probability_of_drawdown: float
    probability_of_ruin: float
    worst_final_equity: float
    median_final_equity: float


class MonteCarloAnalyzer:
    """Estimate ordering risk from observed trade outcomes without changing them."""

    def simulate(
        self,
        trade_pnls: list[float],
        *,
        initial_equity: float,
        simulations: int = 1000,
        drawdown_limit: float = 0.2,
        ruin_equity: float = 0.0,
        seed: int | None = None,
    ) -> MonteCarloResult:
        if not trade_pnls or initial_equity <= 0 or simulations <= 0:
            raise ValueError("valid trades, equity, and simulation count are required")
        if not 0 < drawdown_limit <= 1:
            raise ValueError("drawdown_limit must be in (0, 1]")
        rng = random.Random(seed)
        drawdown_count = 0
        ruin_count = 0
        final_values: list[float] = []
        for _ in range(simulations):
            equity = initial_equity
            peak = equity
            breached_drawdown = False
            breached_ruin = False
            outcomes = list(trade_pnls)
            rng.shuffle(outcomes)
            for pnl in outcomes:
                equity += pnl
                peak = max(peak, equity)
                if peak > 0 and (peak - equity) / peak >= drawdown_limit:
                    breached_drawdown = True
                if equity <= ruin_equity:
                    breached_ruin = True
            drawdown_count += int(breached_drawdown)
            ruin_count += int(breached_ruin)
            final_values.append(equity)
        final_values.sort()
        return MonteCarloResult(
            simulations=simulations,
            probability_of_drawdown=drawdown_count / simulations,
            probability_of_ruin=ruin_count / simulations,
            worst_final_equity=final_values[0],
            median_final_equity=final_values[len(final_values) // 2],
        )
