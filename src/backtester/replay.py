from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Optional

import pandas as pd

from src.decision_engine import TradeSignal
from src.core.instrument_config import get_instrument_config


@dataclass(frozen=True)
class ExecutionConfig:
    spread: float = 0.0
    commission_per_unit: float = 0.0
    slippage: float = 0.0
    entry_delay_candles: int = 0
    same_candle_policy: Literal["stop_loss", "take_profit"] = "stop_loss"

    def __post_init__(self) -> None:
        if min(self.spread, self.commission_per_unit, self.slippage) < 0:
            raise ValueError("execution costs cannot be negative")
        if self.entry_delay_candles < 0:
            raise ValueError("entry_delay_candles cannot be negative")


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    result: Literal["WIN", "LOSS", "EXPIRED"]
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: Literal["SL", "TP", "END"]


class BacktestError(ValueError):
    """Raised when a signal or replay frame cannot be simulated."""


class HistoricalReplay:
    """Replay one validated trade signal against completed OHLC candles."""

    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self.config = config or ExecutionConfig()

    def replay(self, signal: TradeSignal, candles: pd.DataFrame) -> BacktestTrade:
        if signal.direction not in {"BUY", "SELL"}:
            raise BacktestError("Only executable BUY or SELL signals can be replayed")
        required = {"open", "high", "low", "close"}
        if candles is None or candles.empty or not required.issubset(candles.columns):
            raise BacktestError("Replay requires non-empty OHLC candles")
        frame = candles.copy()
        frame.index = pd.to_datetime(frame.index, utc=True, errors="raise")
        frame = frame.sort_index()
        signal_time = pd.Timestamp(signal.timestamp)
        signal_time = signal_time.tz_localize("UTC") if signal_time.tzinfo is None else signal_time.tz_convert("UTC")
        eligible = frame.index > signal_time
        positions = [index for index, is_eligible in enumerate(eligible) if is_eligible]
        if not positions:
            raise BacktestError("No candle occurs after the signal timestamp")
        entry_position = positions[min(self.config.entry_delay_candles, len(positions) - 1)]
        entry_candle = frame.iloc[entry_position]
        entry_price = float(entry_candle["open"])
        if signal.direction == "BUY":
            entry_price += self.config.spread / 2 + self.config.slippage
        else:
            entry_price -= self.config.spread / 2 + self.config.slippage
        stop = float(signal.stop_loss)
        target = float(signal.take_profit)
        for position in range(entry_position, len(frame)):
            candle = frame.iloc[position]
            stop_hit, target_hit = self._hits(candle, signal.direction, stop, target)
            if not stop_hit and not target_hit:
                continue
            if stop_hit and target_hit:
                reason = "SL" if self.config.same_candle_policy == "stop_loss" else "TP"
            else:
                reason = "SL" if stop_hit else "TP"
            exit_price = stop if reason == "SL" else target
            gross = (exit_price - entry_price) if signal.direction == "BUY" else (entry_price - exit_price)
            costs = self.config.commission_per_unit + self.config.spread
            return self._trade(signal, frame.index[entry_position], entry_price, frame.index[position], exit_price, reason, gross, costs)
        last_index = frame.index[-1]
        close = float(frame.iloc[-1]["close"])
        gross = (close - entry_price) if signal.direction == "BUY" else (entry_price - close)
        costs = self.config.commission_per_unit + self.config.spread
        return self._trade(signal, frame.index[entry_position], entry_price, last_index, close, "END", gross, costs)

    @staticmethod
    def _hits(candle: pd.Series, direction: str, stop: float, target: float) -> tuple[bool, bool]:
        high = float(candle["high"])
        low = float(candle["low"])
        if direction == "BUY":
            return low <= stop, high >= target
        return high >= stop, low <= target

    @staticmethod
    def _trade(signal, entry_time, entry_price, exit_time, exit_price, reason, gross, costs):
        result = "WIN" if reason == "TP" else "LOSS" if reason == "SL" else "EXPIRED"
        return BacktestTrade(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_time=entry_time,
            entry_price=entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            result=result,
            gross_pnl=gross,
            costs=costs,
            net_pnl=gross - costs,
            exit_reason=reason,
        )


@dataclass(frozen=True)
class ReplayBacktestTrade:
    """Result of the approved signal-list backtest contract."""

    trade_id: str
    signal: object
    position_size: object
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    exit_reason: str
    pnl_pips: float
    pnl_pct: float
    rr_achieved: float


def run_backtest(
    df: pd.DataFrame,
    signals: list[object],
    position_sizer: Callable,
    account_balance: float,
    risk_pct: float,
    pip_value: float,
    partial_close_at_tp1: bool = True,
    breakeven_at_tp1: bool = True,
) -> list[ReplayBacktestTrade]:
    """Replay each signal only from candles after its formation timestamp."""
    if df is None or df.empty:
        return []
    frame = df.copy()
    frame.index = pd.to_datetime(frame.index, utc=True, errors="raise")
    results: list[ReplayBacktestTrade] = []
    for number, signal in enumerate(signals):
        direction = getattr(signal, "direction", "no_trade")
        if direction not in {"buy", "sell", "BUY", "SELL"}:
            continue
        signal_time = pd.Timestamp(getattr(signal, "formed_at"))
        eligible = frame.index > signal_time
        positions = [idx for idx, allowed in enumerate(eligible) if allowed]
        if not positions:
            continue
        entry_index = positions[0]
        entry_price = float(getattr(signal, "entry_price"))
        position_size = position_sizer(
            account_balance,
            risk_pct,
            entry_price,
            float(getattr(signal, "stop_loss")),
            pip_value,
            getattr(signal, "symbol", ""),
        )
        bullish = direction in {"buy", "BUY"}
        stop = float(getattr(signal, "stop_loss"))
        initial_risk = abs(entry_price - stop)
        tp1 = float(getattr(signal, "take_profit_1"))
        tp2 = float(getattr(signal, "take_profit_2"))
        exit_index: Optional[int] = None
        exit_price: Optional[float] = None
        exit_reason = "open"
        for index in range(entry_index, len(frame)):
            candle = frame.iloc[index]
            stop_hit = float(candle["low"]) <= stop if bullish else float(candle["high"]) >= stop
            tp1_hit = float(candle["high"]) >= tp1 if bullish else float(candle["low"]) <= tp1
            tp2_hit = float(candle["high"]) >= tp2 if bullish else float(candle["low"]) <= tp2
            if stop_hit:
                exit_index, exit_price, exit_reason = index, stop, "sl"
                break
            if tp2_hit and not partial_close_at_tp1:
                exit_index, exit_price, exit_reason = index, tp2, "tp2"
                break
            if tp1_hit:
                if breakeven_at_tp1:
                    stop = entry_price
                exit_index, exit_price, exit_reason = index, tp1, "tp1"
                break
        if exit_index is None:
            exit_time = None
            pnl_pips = 0.0
            pnl_pct = 0.0
            rr = 0.0
        else:
            exit_time = frame.index[exit_index]
            pnl = (exit_price - entry_price) if bullish else (entry_price - exit_price)
            pip_size = get_instrument_config(getattr(signal, "symbol", "XAUUSD")).pip_size
            pnl_pips = pnl / pip_size
            pnl_pct = pnl / entry_price * 100.0
            rr = pnl / initial_risk if initial_risk > 0 else 0.0
        results.append(
            ReplayBacktestTrade(
                trade_id=f"BT_{number}",
                signal=signal,
                position_size=position_size,
                entry_time=frame.index[entry_index],
                exit_time=exit_time,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_pips=pnl_pips,
                pnl_pct=pnl_pct,
                rr_achieved=rr,
            )
        )
    return results
