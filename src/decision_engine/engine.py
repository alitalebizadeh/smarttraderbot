from __future__ import annotations

from uuid import uuid4

import pandas as pd

from src.decision_engine.signal import TradeSignal
from src.liquidity_engine.sweep_detector import LiquiditySweep
from src.mtf_engine.alignment import MTFAlignment
from src.smc_engine.fvg import FairValueGap
from src.smc_engine.order_block import OrderBlock


def _no_trade(symbol: str, alignment: MTFAlignment, reasons: list[str]) -> TradeSignal:
    """Build a no-trade signal with no executable prices."""
    return TradeSignal(
        signal_id=f"SIG_{uuid4().hex}",
        symbol=symbol,
        direction="no_trade",
        entry_price=0.0,
        stop_loss=0.0,
        take_profit_1=0.0,
        take_profit_2=0.0,
        risk_reward_1=0.0,
        risk_reward_2=0.0,
        confidence=0.0,
        reasoning=reasons,
        formed_at=pd.Timestamp.now(tz="UTC"),
        ob_used=None,
        fvg_used=None,
        sweep_used=None,
        mtf_alignment=alignment,
    )


def _overlaps(ob: OrderBlock, fvg: FairValueGap) -> bool:
    """Return True when two price zones overlap."""
    return fvg.gap_bottom <= ob.zone_top and fvg.gap_top >= ob.zone_bottom


def generate_signal(
    symbol: str,
    df: pd.DataFrame,
    atr: pd.Series,
    order_blocks: list[OrderBlock],
    fvgs: list[FairValueGap],
    sweeps: list[LiquiditySweep],
    mtf_alignment: MTFAlignment,
    rr_minimum: float = 2.0,
) -> TradeSignal:
    """Generate a signal only when every approved SMC and MTF prerequisite passes."""
    del df, atr
    reasons: list[str] = []
    if not mtf_alignment.is_aligned or mtf_alignment.trade_direction == "no_trade":
        return _no_trade(symbol, mtf_alignment, ["MTF alignment is not valid"])

    direction = mtf_alignment.trade_direction
    candidates = [ob for ob in order_blocks if ob.direction == direction and ob.score >= 75.0]
    if not candidates:
        return _no_trade(symbol, mtf_alignment, ["No qualifying OrderBlock score >= 75"])

    for ob in candidates:
        matching_fvgs = [
            fvg for fvg in fvgs
            if fvg.direction == direction and fvg.fill_status == "none" and _overlaps(ob, fvg)
        ]
        if not matching_fvgs:
            continue
        prior_sweeps = [sweep for sweep in sweeps if sweep.sweep_candle_index < ob.formed_index]
        if not prior_sweeps:
            continue
        fvg = matching_fvgs[0]
        sweep = prior_sweeps[-1]
        entry = ob.zone_bottom if direction == "bullish" else ob.zone_top
        width = ob.zone_top - ob.zone_bottom
        stop = ob.zone_bottom - width * 0.1 if direction == "bullish" else ob.zone_top + width * 0.1
        risk = abs(entry - stop)
        sign = 1.0 if direction == "bullish" else -1.0
        tp1 = entry + sign * risk * 2.0
        tp2 = entry + sign * risk * 3.0
        rr1 = abs(tp1 - entry) / risk
        rr2 = abs(tp2 - entry) / risk
        if rr1 < rr_minimum:
            return _no_trade(symbol, mtf_alignment, ["Risk/reward is below minimum"])
        reasons.extend(["MTF alignment confirmed", "Qualified OrderBlock", "Unfilled overlapping FVG", "Prior liquidity sweep confirmed"])
        return TradeSignal(
            signal_id=f"SIG_{uuid4().hex}",
            symbol=symbol,
            direction="buy" if direction == "bullish" else "sell",
            entry_price=entry,
            stop_loss=stop,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward_1=rr1,
            risk_reward_2=rr2,
            confidence=(ob.score / 100.0) * mtf_alignment.alignment_score,
            reasoning=reasons,
            formed_at=pd.Timestamp.now(tz="UTC"),
            ob_used=ob,
            fvg_used=fvg,
            sweep_used=sweep,
            mtf_alignment=mtf_alignment,
        )

    return _no_trade(symbol, mtf_alignment, ["No unfilled overlapping FVG with prior sweep"])
