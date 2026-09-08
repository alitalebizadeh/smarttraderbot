from __future__ import annotations

from dataclasses import dataclass

from src.decision_engine.signal import TradeSignal
from src.risk_engine.position_sizer import PositionSize


@dataclass
class TradeState:
    """Mutable execution state for one generated trade signal."""

    signal: TradeSignal
    position_size: PositionSize
    status: str
    current_price: float
    unrealized_pnl: float
    breakeven_activated: bool
    partial_close_done: bool


def _current_rr(state: TradeState) -> float:
    """Calculate current unrealized reward-to-risk from the signal geometry."""
    signal = state.signal
    initial_risk = abs(signal.entry_price - state.position_size.stop_loss)
    if initial_risk == 0:
        return 0.0
    favorable_move = state.current_price - signal.entry_price if signal.direction == "buy" else signal.entry_price - state.current_price
    return favorable_move / initial_risk


def apply_breakeven(state: TradeState, breakeven_trigger_rr: float = 1.0) -> TradeState:
    """Move stop to entry once the configured unrealized RR is reached."""
    if state.breakeven_activated:
        return state
    if _current_rr(state) >= breakeven_trigger_rr:
        state.signal.stop_loss = state.signal.entry_price
        state.breakeven_activated = True
        state.status = "breakeven"
    return state


def apply_trailing_stop(state: TradeState, trail_atr: float, atr_multiplier: float = 1.5) -> TradeState:
    """Move the stop only in the favorable direction behind current price."""
    if trail_atr <= 0 or atr_multiplier <= 0:
        raise ValueError("trail_atr and atr_multiplier must be positive")
    distance = trail_atr * atr_multiplier
    if state.signal.direction == "buy":
        candidate = state.current_price - distance
        if candidate > state.signal.stop_loss:
            state.signal.stop_loss = candidate
    else:
        candidate = state.current_price + distance
        if candidate < state.signal.stop_loss:
            state.signal.stop_loss = candidate
    state.status = "trailing"
    return state
