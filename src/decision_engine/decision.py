from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from src.mtf_engine.alignment import AlignmentResult

Decision = Literal["NO TRADE", "BUY", "SELL"]


@dataclass(frozen=True)
class TradeSignal:
    """Explainable trade decision produced only after all required confirmations."""

    symbol: str
    direction: Decision
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    confidence: float
    reasoning: tuple[str, ...]
    timeframe: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("TradeSignal.symbol must not be empty")
        if not 0.0 <= self.confidence <= 100.0:
            raise ValueError("TradeSignal.confidence must be between 0 and 100")
        if self.direction == "NO TRADE" and any(value is not None for value in (self.entry, self.stop_loss, self.take_profit)):
            raise ValueError("NO TRADE cannot contain executable prices")
        if self.direction != "NO TRADE" and any(value is None or value <= 0 for value in (self.entry, self.stop_loss, self.take_profit)):
            raise ValueError("Executable trade signals require positive prices")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "confidence": self.confidence,
            "reasoning": list(self.reasoning),
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
        }


class DecisionEngine:
    """Gate setups using HTF alignment and explicit market-event prerequisites."""

    def evaluate(
        self,
        *,
        symbol: str,
        timeframe: str,
        alignment: AlignmentResult,
        liquidity_confirmed: bool,
        structure_shift_confirmed: bool,
        poi_confirmed: bool,
        entry: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        timestamp: datetime | None = None,
    ) -> TradeSignal:
        reasons = [
            f"HTF bias: {alignment.htf_bias.direction}",
            f"alignment score: {alignment.alignment_score:.1f}",
        ]
        if alignment.counter_trend_warning:
            reasons.append(alignment.counter_trend_warning)
        prerequisites = {
            "liquidity event": liquidity_confirmed,
            "market structure shift": structure_shift_confirmed,
            "point of interest": poi_confirmed,
            "HTF/LTF alignment": alignment.decision in {"BUY", "SELL"},
        }
        missing = [name for name, present in prerequisites.items() if not present]
        if missing:
            reasons.append("Missing confirmation: " + ", ".join(missing))
            return self._no_trade(symbol, timeframe, reasons, timestamp)

        direction: Decision = alignment.decision  # type: ignore[assignment]
        if direction == "BUY" and not (entry and stop_loss and take_profit and stop_loss < entry < take_profit):
            reasons.append("Invalid bullish price geometry")
            return self._no_trade(symbol, timeframe, reasons, timestamp)
        if direction == "SELL" and not (entry and stop_loss and take_profit and take_profit < entry < stop_loss):
            reasons.append("Invalid bearish price geometry")
            return self._no_trade(symbol, timeframe, reasons, timestamp)

        risk_reward = abs(take_profit - entry) / abs(entry - stop_loss) if entry and stop_loss and take_profit else None
        reasons.append("All required confirmations are present")
        return TradeSignal(
            symbol=symbol,
            direction=direction,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            confidence=min(100.0, alignment.alignment_score),
            reasoning=tuple(reasons),
            timeframe=timeframe,
            timestamp=timestamp or datetime.now(timezone.utc),
        )

    @staticmethod
    def _no_trade(symbol: str, timeframe: str, reasons: list[str], timestamp: datetime | None) -> TradeSignal:
        return TradeSignal(
            symbol=symbol,
            direction="NO TRADE",
            entry=None,
            stop_loss=None,
            take_profit=None,
            risk_reward=None,
            confidence=0.0,
            reasoning=tuple(reasons),
            timeframe=timeframe,
            timestamp=timestamp or datetime.now(timezone.utc),
        )
