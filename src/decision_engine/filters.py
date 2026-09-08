from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal


@dataclass(frozen=True)
class SessionConfig:
    london_start: time = time(7, 0)
    london_end: time = time(11, 0)
    new_york_start: time = time(13, 0)
    new_york_end: time = time(17, 0)
    asian_start: time = time(0, 0)
    asian_end: time = time(6, 0)


class SessionFilter:
    def __init__(self, config: SessionConfig | None = None) -> None:
        self.config = config or SessionConfig()

    def session_at(self, timestamp: datetime) -> Literal["london", "new_york", "asian", "off_session"]:
        current = timestamp.time()
        if self.config.london_start <= current < self.config.london_end:
            return "london"
        if self.config.new_york_start <= current < self.config.new_york_end:
            return "new_york"
        if self.config.asian_start <= current < self.config.asian_end:
            return "asian"
        return "off_session"


@dataclass(frozen=True)
class NewsEvent:
    name: str
    timestamp: datetime
    impact: Literal["low", "medium", "high"]


class NewsFilter:
    def __init__(self, before_minutes: int = 30, after_minutes: int = 30) -> None:
        if before_minutes < 0 or after_minutes < 0:
            raise ValueError("news windows cannot be negative")
        self.before_minutes = before_minutes
        self.after_minutes = after_minutes

    def blocks(self, timestamp: datetime, events: list[NewsEvent]) -> bool:
        for event in events:
            if event.impact != "high":
                continue
            delta = (timestamp - event.timestamp).total_seconds() / 60.0
            if -self.before_minutes <= delta <= self.after_minutes:
                return True
        return False
