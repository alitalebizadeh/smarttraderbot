from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["SwingPoint", "MarketStructureEvent", "MarketStructure"]


@dataclass(eq=True)
class SwingPoint:
    """A confirmed Swing High or Swing Low on the price chart.

    Attributes:
        index: Zero-based candle index in the source DataFrame.
        time: UTC timestamp of the candle.
        price: Exact price of the swing — High for swing highs, Low for swing lows.
        swing_type: ``"high"`` for a Swing High, ``"low"`` for a Swing Low.
        is_confirmed: ``True`` when at least two subsequent candles have confirmed the swing.
    """

    index: int
    time: datetime
    price: float
    swing_type: Literal["high", "low"]
    is_confirmed: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If ``price`` is not positive or ``index`` is negative.
        """
        if self.price <= 0:
            raise ValueError(
                f"SwingPoint.price must be > 0, got {self.price}."
            )
        if self.index < 0:
            raise ValueError(
                f"SwingPoint.index must be >= 0, got {self.index}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat dictionary with all fields serialised to JSON-safe types.
            ``datetime`` values are converted to ISO 8601 strings.
        """
        return {
            "index": self.index,
            "time": self.time.isoformat(),
            "price": self.price,
            "swing_type": self.swing_type,
            "is_confirmed": self.is_confirmed,
        }


@dataclass(eq=True)
class MarketStructureEvent:
    """A single BOS (Break of Structure) or CHoCH (Change of Character) event.

    Directional semantics:
        - ``bullish BOS``:   price closed above a previous confirmed Swing High
          (bullish trend continuation).
        - ``bearish BOS``:   price closed below a previous confirmed Swing Low
          (bearish trend continuation).
        - ``bullish CHoCH``: in a downtrend, price closes above the last Swing High
          (potential reversal to upside).
        - ``bearish CHoCH``: in an uptrend, price closes below the last Swing Low
          (potential reversal to downside).

    Attributes:
        event_type: ``"BOS"`` or ``"CHoCH"``.
        direction: ``"bullish"`` or ``"bearish"``.
        broken_swing: The SwingPoint whose level was violated.
        break_candle_index: DataFrame index of the candle that caused the break.
        break_candle_time: UTC timestamp of the break candle.
        break_price: Close price of the break candle.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
    """

    event_type: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    broken_swing: SwingPoint
    break_candle_index: int
    break_candle_time: datetime
    break_price: float
    symbol: str
    timeframe: str

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``break_price`` must be > 0.
                - ``symbol`` must be a non-empty string.
                - ``timeframe`` must be a non-empty string.
                - ``break_candle_index`` must be strictly greater than
                  ``broken_swing.index`` (the break must occur after the swing).
        """
        if self.break_price <= 0:
            raise ValueError(
                f"MarketStructureEvent.break_price must be > 0, got {self.break_price}."
            )
        if not self.symbol:
            raise ValueError(
                "MarketStructureEvent.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "MarketStructureEvent.timeframe must not be an empty string."
            )
        if self.break_candle_index <= self.broken_swing.index:
            raise ValueError(
                f"MarketStructureEvent.break_candle_index ({self.break_candle_index}) "
                f"must be > broken_swing.index ({self.broken_swing.index}). "
                "The break candle must occur after the swing point."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat dictionary with all fields serialised to JSON-safe types.
            ``datetime`` values are converted to ISO 8601 strings.
            The nested ``broken_swing`` is serialised via its own ``to_dict()``.
        """
        return {
            "event_type": self.event_type,
            "direction": self.direction,
            "broken_swing": self.broken_swing.to_dict(),
            "break_candle_index": self.break_candle_index,
            "break_candle_time": self.break_candle_time.isoformat(),
            "break_price": self.break_price,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }


@dataclass(eq=False)
class MarketStructure:
    """Full market structure analysis result for one symbol and timeframe.

    Created exclusively by ``src/engine/market_structure_engine.py``.
    Consumed by the POI layer, confluence engine, scanner, and dashboard.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Number of candles that were analysed.
        swing_highs: All confirmed Swing Highs in chronological order.
        swing_lows: All confirmed Swing Lows in chronological order.
        events: All BOS / CHoCH events found, in chronological order.
        current_bias: Overall directional bias set by the engine.

            - ``"bullish"``:  last event was a bullish BOS or bullish CHoCH.
            - ``"bearish"``:  last event was a bearish BOS or bearish CHoCH.
            - ``"neutral"``:  no events were found.

        last_event: The most recent ``MarketStructureEvent``, or ``None`` when
            no events were detected.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    swing_highs: list[SwingPoint]
    swing_lows: list[SwingPoint]
    events: list[MarketStructureEvent]
    current_bias: Literal["bullish", "bearish", "neutral"]
    last_event: Optional[MarketStructureEvent] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``candle_count`` must be >= 0.
                - ``symbol`` must be a non-empty string.
                - ``timeframe`` must be a non-empty string.
        """
        if self.candle_count < 0:
            raise ValueError(
                f"MarketStructure.candle_count must be >= 0, got {self.candle_count}."
            )
        if not self.symbol:
            raise ValueError(
                "MarketStructure.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "MarketStructure.timeframe must not be an empty string."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A dictionary with all fields serialised to JSON-safe types.

            - ``datetime`` values → ISO 8601 strings.
            - Nested dataclasses → serialised via their own ``to_dict()``.
            - Lists of dataclasses → lists of dicts.
            - ``None`` optional fields → ``None`` (not omitted).
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "swing_highs": [sh.to_dict() for sh in self.swing_highs],
            "swing_lows": [sl.to_dict() for sl in self.swing_lows],
            "events": [ev.to_dict() for ev in self.events],
            "current_bias": self.current_bias,
            "last_event": (
                self.last_event.to_dict() if self.last_event is not None else None
            ),
        }