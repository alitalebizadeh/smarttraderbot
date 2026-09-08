from __future__ import annotations

import pandas as pd

from src.database.repository import TradeRepository
from src.decision_engine.engine import generate_signal
from src.decision_engine.signal import TradeSignal
from src.liquidity_engine.levels import detect_equal_highs, detect_equal_lows, detect_previous_day_levels, detect_weekly_levels
from src.liquidity_engine.sweep_detector import detect_sweeps
from src.market_structure.causal import CausalMarketStructureEngine
from src.mtf_engine import check_alignment, compute_bias
from src.risk_engine.position_sizer import calculate_position_size
from src.smc_engine.fvg import detect_fvgs
from src.smc_engine.order_block import detect_order_blocks


def _atr(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
    """Calculate point-in-time rolling ATR for a clean OHLC frame."""
    previous = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - previous).abs(), (df["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(lookback, min_periods=1).mean()


def run_full_pipeline(
    symbol: str,
    df_ltf: pd.DataFrame,
    df_htf: pd.DataFrame,
    account_balance: float,
    risk_pct: float,
    pip_value: float,
    db_path: str,
) -> TradeSignal:
    """Run causal structure, confluence, decision, sizing, and persistence in order."""
    htf_events = CausalMarketStructureEngine().analyze(df_htf, symbol, "H4")
    ltf_events = CausalMarketStructureEngine().analyze(df_ltf, symbol, "M15")
    htf_bias = compute_bias(htf_events, "H4")
    ltf_bias = compute_bias(ltf_events, "M15")
    alignment = check_alignment(htf_bias, ltf_bias, symbol)
    if alignment.trade_direction == "no_trade":
        return generate_signal(symbol, df_ltf, _atr(df_ltf), [], [], [], alignment)

    atr = _atr(df_ltf)
    levels = detect_previous_day_levels(df_ltf) + detect_weekly_levels(df_ltf)
    high_prices = [float(event.broken_swing.price) for event in ltf_events if getattr(event.broken_swing, "swing_type", "") == "high"]
    low_prices = [float(event.broken_swing.price) for event in ltf_events if getattr(event.broken_swing, "swing_type", "") == "low"]
    high_times = [pd.Timestamp(event.break_candle_time) for event in ltf_events if getattr(event.broken_swing, "swing_type", "") == "high"]
    low_times = [pd.Timestamp(event.break_candle_time) for event in ltf_events if getattr(event.broken_swing, "swing_type", "") == "low"]
    levels.extend(detect_equal_highs(df_ltf, high_prices, high_times))
    levels.extend(detect_equal_lows(df_ltf, low_prices, low_times))
    sweeps = detect_sweeps(df_ltf, levels, atr)
    direction = alignment.trade_direction
    order_blocks = detect_order_blocks(df_ltf, atr, sweeps, direction)
    fvgs = detect_fvgs(df_ltf, atr, direction)
    signal = generate_signal(symbol, df_ltf, atr, order_blocks, fvgs, sweeps, alignment)
    if signal.direction != "no_trade":
        calculate_position_size(account_balance, risk_pct, signal.entry_price, signal.stop_loss, pip_value, symbol)
        repository = TradeRepository(db_path)
        try:
            repository.save_setup(signal)
        finally:
            repository.close()
    return signal
