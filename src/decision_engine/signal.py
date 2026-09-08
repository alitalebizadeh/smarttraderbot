from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.liquidity_engine.sweep_detector import LiquiditySweep
from src.mtf_engine.alignment import MTFAlignment
from src.smc_engine.fvg import FairValueGap
from src.smc_engine.order_block import OrderBlock


@dataclass
class TradeSignal:
    """A generated executable signal or explainable no-trade decision."""

    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_1: float
    risk_reward_2: float
    confidence: float
    reasoning: list[str]
    formed_at: pd.Timestamp
    ob_used: Optional[OrderBlock]
    fvg_used: Optional[FairValueGap]
    sweep_used: Optional[LiquiditySweep]
    mtf_alignment: MTFAlignment
