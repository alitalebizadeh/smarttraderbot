from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["OrderBlock", "OrderBlockMap"]


@dataclass(eq=True)
class OrderBlock:
    """A single institutional Order Block zone.

    An Order Block is the last opposing candle before a significant displacement
    move, marking a price area where institutions accumulated directional orders.

    Zone definitions:
        - **Bullish OB**: the last *bearish* candle before a strong bullish
          displacement.  The zone spans from the candle's ``low`` to its ``high``.
          Price returning to this zone is expected to find demand.
        - **Bearish OB**: the last *bullish* candle before a strong bearish
          displacement.  The zone spans from the candle's ``low`` to its ``high``.
          Price returning to this zone is expected to find supply.

    The ``zone_midpoint`` (50 % level) is a key reaction reference within the zone.

    Attributes:
        ob_id: Unique identifier, e.g. ``"OB_BULL_XAUUSD_M1_42"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        ob_type: ``"bullish"`` for a demand OB, ``"bearish"`` for a supply OB.
        candle_index: Zero-based DataFrame index of the OB candle.
        candle_time: UTC timestamp of the OB candle.
        open: Open price of the OB candle.
        high: High price of the OB candle (defines ``zone_top``).
        low: Low price of the OB candle (defines ``zone_bottom``).
        close: Close price of the OB candle.
        zone_top: Upper boundary of the OB zone (equals ``high``).
        zone_bottom: Lower boundary of the OB zone (equals ``low``).
        zone_midpoint: Midpoint of the zone — ``(zone_top + zone_bottom) / 2``.
        displacement_start_index: DataFrame index of the first candle of the
            displacement that follows this OB.  Must be > ``candle_index``.
        displacement_direction: Direction of the displacement that validated this OB.
        is_mitigated: ``True`` when price has closed through the OB zone,
            rendering it consumed.
        mitigated_at_time: UTC timestamp of mitigation, or ``None``.
        mitigated_at_price: Price at which mitigation occurred, or ``None``.
        touch_count: Number of times price has returned into the zone.
        strength: OB quality score in ``[0.0, 1.0]``, set by the engine.
            Factors include displacement strength, candle cleanliness, and
            distance from current price.
    """

    ob_id: str
    symbol: str
    timeframe: str
    ob_type: Literal["bullish", "bearish"]
    candle_index: int
    candle_time: datetime
    open: float
    high: float
    low: float
    close: float
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    displacement_start_index: int
    displacement_direction: Literal["bullish", "bearish"]
    is_mitigated: bool = field(default=False)
    is_broken_retested: bool = field(default=False)
    mitigated_at_time: Optional[datetime] = field(default=None)
    mitigated_at_price: Optional[float] = field(default=None)
    touch_count: int = field(default=0)
    strength: float = field(default=0.0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``high`` must be >= ``low``.
                - ``high``, ``low``, ``open``, and ``close`` must each be > 0.
                - ``zone_top`` must be >= ``zone_bottom``.
                - ``zone_midpoint`` must be in the range
                  ``[zone_bottom, zone_top]`` (inclusive).
                - ``displacement_start_index`` must be > ``candle_index``.
                - ``touch_count`` must be >= 0.
                - ``strength`` must be in the range ``[0.0, 1.0]`` (inclusive).
                - ``ob_id`` must not be empty.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - When ``is_mitigated`` is ``True``, both ``mitigated_at_time``
                  and ``mitigated_at_price`` must not be ``None``.
        """
        if self.high < self.low:
            raise ValueError(
                f"OrderBlock.high ({self.high}) must be >= low ({self.low})."
            )
        for name, value in (
            ("high", self.high),
            ("low", self.low),
            ("open", self.open),
            ("close", self.close),
        ):
            if value <= 0:
                raise ValueError(
                    f"OrderBlock.{name} must be > 0, got {value}."
                )
        if self.zone_top < self.zone_bottom:
            raise ValueError(
                f"OrderBlock.zone_top ({self.zone_top}) must be >= "
                f"zone_bottom ({self.zone_bottom})."
            )
        if not (self.zone_bottom <= self.zone_midpoint <= self.zone_top):
            raise ValueError(
                f"OrderBlock.zone_midpoint ({self.zone_midpoint}) must be between "
                f"zone_bottom ({self.zone_bottom}) and zone_top ({self.zone_top}) "
                "inclusive."
            )
        if self.displacement_start_index <= self.candle_index:
            raise ValueError(
                f"OrderBlock.displacement_start_index "
                f"({self.displacement_start_index}) must be > "
                f"candle_index ({self.candle_index})."
            )
        if self.touch_count < 0:
            raise ValueError(
                f"OrderBlock.touch_count must be >= 0, got {self.touch_count}."
            )
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(
                f"OrderBlock.strength must be between 0.0 and 1.0 (inclusive), "
                f"got {self.strength}."
            )
        if not self.ob_id:
            raise ValueError("OrderBlock.ob_id must not be an empty string.")
        if not self.symbol:
            raise ValueError("OrderBlock.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("OrderBlock.timeframe must not be an empty string.")
        if self.is_mitigated:
            if self.mitigated_at_time is None:
                raise ValueError(
                    "OrderBlock.mitigated_at_time must not be None "
                    "when is_mitigated is True."
                )
            if self.mitigated_at_price is None:
                raise ValueError(
                    "OrderBlock.mitigated_at_price must not be None "
                    "when is_mitigated is True."
                )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Score / ratio fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "ob_id": self.ob_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "ob_type": self.ob_type,
            "candle_index": self.candle_index,
            "candle_time": self.candle_time.isoformat(),
            "open": round(self.open, 6),
            "high": round(self.high, 6),
            "low": round(self.low, 6),
            "close": round(self.close, 6),
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "displacement_start_index": self.displacement_start_index,
            "displacement_direction": self.displacement_direction,
            "is_mitigated": self.is_mitigated,
            "is_broken_retested": self.is_broken_retested,
            "mitigated_at_time": (
                self.mitigated_at_time.isoformat()
                if self.mitigated_at_time is not None
                else None
            ),
            "mitigated_at_price": (
                round(self.mitigated_at_price, 6)
                if self.mitigated_at_price is not None
                else None
            ),
            "touch_count": self.touch_count,
            "strength": round(self.strength, 4),
        }


@dataclass(eq=False)
class OrderBlockMap:
    """Complete Order Block analysis result for one symbol and timeframe.

    Created by ``src/engine/order_block_engine.py`` and consumed by the POI
    engine, confluence engine, scanner, and dashboard.  Acts as the single
    source of truth for all Order Block data on a given instrument / timeframe
    combination.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Total number of candles that were analysed.
        bullish_obs: All active (unmitigated) bullish Order Blocks in
            chronological order.
        bearish_obs: All active (unmitigated) bearish Order Blocks in
            chronological order.
        mitigated_obs: All mitigated Order Blocks kept for historical reference,
            in chronological order.
        last_bullish_ob: The most recent unmitigated bullish :class:`OrderBlock`,
            or ``None`` when none exist.
        last_bearish_ob: The most recent unmitigated bearish :class:`OrderBlock`,
            or ``None`` when none exist.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    bullish_obs: list[OrderBlock] = field(default_factory=list)
    bearish_obs: list[OrderBlock] = field(default_factory=list)
    mitigated_obs: list[OrderBlock] = field(default_factory=list)
    last_bullish_ob: Optional[OrderBlock] = field(default=None)
    last_bearish_ob: Optional[OrderBlock] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candle_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError("OrderBlockMap.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("OrderBlockMap.timeframe must not be an empty string.")
        if self.candle_count < 0:
            raise ValueError(
                f"OrderBlockMap.candle_count must be >= 0, got {self.candle_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`OrderBlock` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "bullish_obs": [ob.to_dict() for ob in self.bullish_obs],
            "bearish_obs": [ob.to_dict() for ob in self.bearish_obs],
            "mitigated_obs": [ob.to_dict() for ob in self.mitigated_obs],
            "last_bullish_ob": (
                self.last_bullish_ob.to_dict()
                if self.last_bullish_ob is not None
                else None
            ),
            "last_bearish_ob": (
                self.last_bearish_ob.to_dict()
                if self.last_bearish_ob is not None
                else None
            ),
        }