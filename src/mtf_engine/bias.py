from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd

Direction = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class TimeframeBias:
    """Directional event-count bias for one timeframe."""

    timeframe: str
    direction: str
    bos_count: int
    choch_count: int
    last_event_time: pd.Timestamp
    confidence: float


def compute_bias(market_structure_events: list, timeframe: str) -> TimeframeBias:
    """Compute directional bias from causal BOS and CHoCH event objects."""
    bullish = 0
    bearish = 0
    latest = pd.Timestamp.min.tz_localize("UTC")
    for event in market_structure_events:
        direction = getattr(event, "direction", "neutral")
        event_type = getattr(event, "event_type", "")
        if direction == "bullish" and event_type in {"BOS", "CHoCH"}:
            bullish += 1
        elif direction == "bearish" and event_type in {"BOS", "CHoCH"}:
            bearish += 1
        raw_time = getattr(event, "break_candle_time", None)
        if raw_time is not None:
            event_time = pd.Timestamp(raw_time)
            if event_time.tzinfo is None:
                event_time = event_time.tz_localize("UTC")
            latest = max(latest, event_time)
    if bullish > bearish:
        direction = "bullish"
    elif bearish > bullish:
        direction = "bearish"
    else:
        direction = "neutral"
    total = bullish + bearish
    return TimeframeBias(
        timeframe=timeframe,
        direction=direction,
        bos_count=sum(getattr(event, "event_type", "") == "BOS" and getattr(event, "direction", "") == direction for event in market_structure_events),
        choch_count=sum(getattr(event, "event_type", "") == "CHoCH" and getattr(event, "direction", "") == direction for event in market_structure_events),
        last_event_time=latest,
        confidence=abs(bullish - bearish) / max(1, total),
    )


@dataclass(frozen=True)
class MarketBias:
    """Directional context produced for one timeframe."""

    direction: Direction
    timeframe: str
    strength: float
    reason: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.direction not in {"bullish", "bearish", "neutral"}:
            raise ValueError(f"Unsupported market bias direction: {self.direction}")
        if not self.timeframe:
            raise ValueError("MarketBias.timeframe must not be empty")
        if not 0.0 <= self.strength <= 100.0:
            raise ValueError("MarketBias.strength must be between 0 and 100")
        if not self.reason:
            raise ValueError("MarketBias.reason must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "timeframe": self.timeframe,
            "strength": self.strength,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


def bias_from_structure(structure: Any, timeframe: str | None = None) -> MarketBias:
    """Convert a MarketStructure-like object into a validated MarketBias."""
    resolved_timeframe = str(timeframe or getattr(structure, "timeframe", "")).upper()
    if structure is None or not resolved_timeframe:
        return MarketBias(
            direction="neutral",
            timeframe=resolved_timeframe or "UNKNOWN",
            strength=0.0,
            reason="Market structure data is unavailable",
            timestamp=datetime.now(timezone.utc),
        )

    direction = getattr(structure, "current_bias", "neutral")
    if direction not in {"bullish", "bearish", "neutral"}:
        direction = "neutral"

    event = getattr(structure, "last_event", None)
    timestamp = getattr(structure, "analyzed_at", None) or datetime.now(timezone.utc)
    if event is None:
        return MarketBias(
            direction=direction,
            timeframe=resolved_timeframe,
            strength=0.0 if direction == "neutral" else 35.0,
            reason="No confirmed structure event" if direction == "neutral" else "Bias inferred from structure",
            timestamp=timestamp,
        )

    swing = getattr(event, "broken_swing", None)
    strength = float(getattr(swing, "strength_score", 50.0) or 50.0)
    return MarketBias(
        direction=direction,
        timeframe=resolved_timeframe,
        strength=min(100.0, max(0.0, strength)),
        reason=f"{event.direction} {event.event_type} confirmed",
        timestamp=getattr(event, "break_candle_time", timestamp),
    )
