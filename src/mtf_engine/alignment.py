from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from src.mtf_engine.bias import Direction, MarketBias


@dataclass(frozen=True)
class MTFAlignment:
    """Alignment result for one higher/lower timeframe pair."""

    symbol: str
    higher_tf_bias: object
    lower_tf_bias: object
    is_aligned: bool
    alignment_score: float
    trade_direction: str


def check_alignment(higher_tf: object, lower_tf: object, symbol: str) -> MTFAlignment:
    """Require non-neutral matching directions, with higher timeframe control."""
    higher_direction = getattr(higher_tf, "direction", "neutral")
    lower_direction = getattr(lower_tf, "direction", "neutral")
    aligned = (
        higher_direction == lower_direction
        and higher_direction != "neutral"
        and lower_direction != "neutral"
    )
    score = (
        (float(getattr(higher_tf, "confidence", 0.0)) + float(getattr(lower_tf, "confidence", 0.0))) / 2.0
        if aligned
        else 0.0
    )
    return MTFAlignment(
        symbol=symbol,
        higher_tf_bias=higher_tf,
        lower_tf_bias=lower_tf,
        is_aligned=aligned,
        alignment_score=score,
        trade_direction=higher_direction if aligned else "no_trade",
    )


@dataclass(frozen=True)
class AlignmentResult:
    """Decision context for a setup across the supported timeframe hierarchy."""

    htf_bias: MarketBias
    h4_h1_context: dict[str, MarketBias]
    ltf_signal: Optional[MarketBias]
    alignment_score: float
    decision: str
    counter_trend_warning: Optional[str] = None

    @property
    def htf(self) -> MarketBias:
        return self.htf_bias

    def to_dict(self) -> dict[str, Any]:
        return {
            "htf_bias": self.htf_bias.to_dict(),
            "h4_h1_context": {
                timeframe: bias.to_dict()
                for timeframe, bias in self.h4_h1_context.items()
            },
            "ltf_signal": self.ltf_signal.to_dict() if self.ltf_signal else None,
            "alignment_score": self.alignment_score,
            "decision": self.decision,
            "counter_trend_warning": self.counter_trend_warning,
        }


def evaluate_alignment(biases: Mapping[str, MarketBias]) -> AlignmentResult:
    """Evaluate HTF control over H1, M15, and M5 signals.

    Daily and H4 establish the controlling direction. H1 confirms or weakens it;
    lower timeframes can provide a signal but can never reverse the decision.
    """
    normalized = {str(key).upper(): value for key, value in biases.items() if value is not None}
    daily = normalized.get("D1") or normalized.get("DAILY")
    h4 = normalized.get("H4")
    h1 = normalized.get("H1")
    m15 = normalized.get("M15")
    m5 = normalized.get("M5")

    primary = _primary_bias(daily, h4)
    h4_h1_context = {key: value for key, value in (("H4", h4), ("H1", h1)) if value is not None}
    ltf_signal = m5 or m15

    score = 0.0
    if daily and h4 and daily.direction == h4.direction and daily.direction != "neutral":
        score += 60.0
    elif primary.direction != "neutral":
        score += 35.0

    warning: Optional[str] = None
    if h1 is not None and primary.direction != "neutral":
        if h1.direction == primary.direction:
            score += 25.0
        elif h1.direction != "neutral":
            score -= 20.0
            warning = f"H1 {h1.direction} conflicts with {primary.direction} higher-timeframe bias"

    if ltf_signal is not None and primary.direction != "neutral":
        if ltf_signal.direction == primary.direction:
            score += 15.0
        elif ltf_signal.direction != "neutral":
            warning = warning or f"LTF {ltf_signal.direction} signal conflicts with {primary.direction} higher-timeframe bias"

    if primary.direction == "neutral":
        decision = "WAIT"
    elif warning and h1 is not None and h1.direction not in {"neutral", primary.direction}:
        decision = "WAIT"
    elif ltf_signal is None or ltf_signal.direction != primary.direction:
        decision = "WAIT"
    else:
        decision = "BUY" if primary.direction == "bullish" else "SELL"

    return AlignmentResult(
        htf_bias=primary,
        h4_h1_context=h4_h1_context,
        ltf_signal=ltf_signal,
        alignment_score=min(100.0, max(0.0, score)),
        decision=decision,
        counter_trend_warning=warning,
    )


def _primary_bias(daily: Optional[MarketBias], h4: Optional[MarketBias]) -> MarketBias:
    if daily and h4 and daily.direction == h4.direction and daily.direction != "neutral":
        return MarketBias(
            direction=daily.direction,
            timeframe="D1/H4",
            strength=(daily.strength + h4.strength) / 2.0,
            reason="Daily and H4 agree",
            timestamp=max(daily.timestamp, h4.timestamp),
        )
    if daily and daily.direction != "neutral":
        return MarketBias(
            direction=daily.direction,
            timeframe="D1",
            strength=daily.strength,
            reason="Daily controls while H4 is missing or non-confirming",
            timestamp=daily.timestamp,
        )
    if h4 and h4.direction != "neutral":
        return MarketBias(
            direction=h4.direction,
            timeframe="H4",
            strength=h4.strength,
            reason="H4 controls while Daily is missing or neutral",
            timestamp=h4.timestamp,
        )
    timestamp = max((bias.timestamp for bias in (daily, h4) if bias), default=datetime.now(timezone.utc))
    return MarketBias(
        direction="neutral",
        timeframe="D1/H4",
        strength=0.0,
        reason="Daily and H4 do not establish a directional bias",
        timestamp=timestamp,
    )
