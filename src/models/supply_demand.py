from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["SupplyZone", "DemandZone", "SupplyDemandMap"]


# ---------------------------------------------------------------------------
# Shared validation helper
# ---------------------------------------------------------------------------

def _validate_zone_fields(
    zone_id: str,
    symbol: str,
    timeframe: str,
    zone_top: float,
    zone_bottom: float,
    zone_midpoint: float,
    proximal_line: float,
    distal_line: float,
    base_start_index: int,
    base_end_index: int,
    explosion_candle_index: int,
    base_candle_count: int,
    touch_count: int,
    strength: float,
    status: str,
    broken_at_time: Optional[datetime],
    broken_at_price: Optional[float],
    class_name: str,
) -> None:
    """Validate fields shared by both SupplyZone and DemandZone.

    Args:
        zone_id: Unique zone identifier.
        symbol: Instrument name.
        timeframe: Timeframe string.
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.
        zone_midpoint: Midpoint of the zone.
        proximal_line: Boundary closest to current price.
        distal_line: Boundary furthest from current price.
        base_start_index: Index of the first base candle.
        base_end_index: Index of the last base candle.
        explosion_candle_index: Index of the first explosion candle.
        base_candle_count: Number of base candles.
        touch_count: Number of zone retests.
        strength: Zone strength score.
        status: Zone lifecycle status.
        broken_at_time: Timestamp of zone break (or None).
        broken_at_price: Price at which zone was broken (or None).
        class_name: Name of the calling dataclass, used in error messages.

    Raises:
        ValueError: On any validation failure.
    """
    if not zone_id:
        raise ValueError(f"{class_name}.zone_id must not be an empty string.")
    if not symbol:
        raise ValueError(f"{class_name}.symbol must not be an empty string.")
    if not timeframe:
        raise ValueError(f"{class_name}.timeframe must not be an empty string.")
    if zone_top <= zone_bottom:
        raise ValueError(
            f"{class_name}.zone_top ({zone_top}) must be > "
            f"zone_bottom ({zone_bottom})."
        )
    if zone_top <= 0:
        raise ValueError(
            f"{class_name}.zone_top must be > 0, got {zone_top}."
        )
    if zone_bottom <= 0:
        raise ValueError(
            f"{class_name}.zone_bottom must be > 0, got {zone_bottom}."
        )
    if not (zone_bottom <= zone_midpoint <= zone_top):
        raise ValueError(
            f"{class_name}.zone_midpoint ({zone_midpoint}) must be between "
            f"zone_bottom ({zone_bottom}) and zone_top ({zone_top}) inclusive."
        )
    if not (zone_bottom <= proximal_line <= zone_top):
        raise ValueError(
            f"{class_name}.proximal_line ({proximal_line}) must be between "
            f"zone_bottom ({zone_bottom}) and zone_top ({zone_top}) inclusive."
        )
    if not (zone_bottom <= distal_line <= zone_top):
        raise ValueError(
            f"{class_name}.distal_line ({distal_line}) must be between "
            f"zone_bottom ({zone_bottom}) and zone_top ({zone_top}) inclusive."
        )
    if base_end_index < base_start_index:
        raise ValueError(
            f"{class_name}.base_end_index ({base_end_index}) must be >= "
            f"base_start_index ({base_start_index})."
        )
    if explosion_candle_index <= base_end_index:
        raise ValueError(
            f"{class_name}.explosion_candle_index ({explosion_candle_index}) "
            f"must be > base_end_index ({base_end_index})."
        )
    if base_candle_count < 1:
        raise ValueError(
            f"{class_name}.base_candle_count must be >= 1, "
            f"got {base_candle_count}."
        )
    if touch_count < 0:
        raise ValueError(
            f"{class_name}.touch_count must be >= 0, got {touch_count}."
        )
    if not (0.0 <= strength <= 1.0):
        raise ValueError(
            f"{class_name}.strength must be between 0.0 and 1.0 (inclusive), "
            f"got {strength}."
        )
    if status == "broken":
        if broken_at_time is None:
            raise ValueError(
                f"{class_name}.broken_at_time must not be None "
                "when status is \"broken\"."
            )
        if broken_at_price is None:
            raise ValueError(
                f"{class_name}.broken_at_price must not be None "
                "when status is \"broken\"."
            )


# ---------------------------------------------------------------------------
# SupplyZone
# ---------------------------------------------------------------------------

@dataclass(eq=True)
class SupplyZone:
    """A single institutional Supply Zone.

    A Supply Zone marks a price area where institutional selling created a
    strong bearish displacement move away.  It consists of base candles
    (consolidation) followed by an explosive bearish move.  When price
    returns to this zone it is expected to encounter selling pressure.

    Zone boundaries:
        - ``proximal_line``: the zone bottom — the boundary price approaches
          first when rallying up into the zone.
        - ``distal_line``: the zone top — the extreme boundary furthest from
          the approach direction.

    Attributes:
        zone_id: Unique identifier, e.g. ``"SUPPLY_XAUUSD_M1_200"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        zone_top: Upper price boundary of the zone.
        zone_bottom: Lower price boundary of the zone.
        zone_midpoint: Midpoint of the zone — ``(zone_top + zone_bottom) / 2``.
        proximal_line: Closest boundary to approaching price — equals
            ``zone_bottom`` for supply zones (price approaches from below).
        distal_line: Furthest boundary from approaching price — equals
            ``zone_top`` for supply zones.
        base_start_index: Zero-based DataFrame index of the first base candle.
        base_end_index: Zero-based DataFrame index of the last base candle.
        base_start_time: UTC timestamp of the first base candle.
        base_end_time: UTC timestamp of the last base candle.
        explosion_candle_index: Index of the first candle of the explosive
            bearish move that defines the zone.
        explosion_direction: Always ``"bearish"`` for supply zones.
        base_candle_count: Number of consolidation candles forming the base.
        status: Lifecycle status — ``"active"``, ``"tested"``, or ``"broken"``.
        touch_count: Number of times price has returned into the zone.
        strength: Zone quality score in ``[0.0, 1.0]``, set by the engine.
        broken_at_time: UTC timestamp when the zone was broken, or ``None``.
        broken_at_price: Price at which the zone was broken, or ``None``.
    """

    zone_id: str
    symbol: str
    timeframe: str
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    proximal_line: float
    distal_line: float
    base_start_index: int
    base_end_index: int
    base_start_time: datetime
    base_end_time: datetime
    explosion_candle_index: int
    explosion_direction: Literal["bearish"]
    base_candle_count: int
    status: Literal["active", "tested", "broken"] = field(default="active")
    touch_count: int = field(default=0)
    strength: float = field(default=0.0)
    broken_at_time: Optional[datetime] = field(default=None)
    broken_at_price: Optional[float] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: On any validation failure — see module docstring for
                full rules.
        """
        _validate_zone_fields(
            zone_id=self.zone_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            zone_top=self.zone_top,
            zone_bottom=self.zone_bottom,
            zone_midpoint=self.zone_midpoint,
            proximal_line=self.proximal_line,
            distal_line=self.distal_line,
            base_start_index=self.base_start_index,
            base_end_index=self.base_end_index,
            explosion_candle_index=self.explosion_candle_index,
            base_candle_count=self.base_candle_count,
            touch_count=self.touch_count,
            strength=self.strength,
            status=self.status,
            broken_at_time=self.broken_at_time,
            broken_at_price=self.broken_at_price,
            class_name="SupplyZone",
        )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Strength / ratio fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "zone_id": self.zone_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "proximal_line": round(self.proximal_line, 6),
            "distal_line": round(self.distal_line, 6),
            "base_start_index": self.base_start_index,
            "base_end_index": self.base_end_index,
            "base_start_time": self.base_start_time.isoformat(),
            "base_end_time": self.base_end_time.isoformat(),
            "explosion_candle_index": self.explosion_candle_index,
            "explosion_direction": self.explosion_direction,
            "base_candle_count": self.base_candle_count,
            "status": self.status,
            "touch_count": self.touch_count,
            "strength": round(self.strength, 4),
            "broken_at_time": (
                self.broken_at_time.isoformat()
                if self.broken_at_time is not None
                else None
            ),
            "broken_at_price": (
                round(self.broken_at_price, 6)
                if self.broken_at_price is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# DemandZone
# ---------------------------------------------------------------------------

@dataclass(eq=True)
class DemandZone:
    """A single institutional Demand Zone.

    A Demand Zone marks a price area where institutional buying created a
    strong bullish displacement move away.  It consists of base candles
    (consolidation) followed by an explosive bullish move.  When price
    returns to this zone it is expected to encounter buying pressure.

    Zone boundaries:
        - ``proximal_line``: the zone top — the boundary price approaches
          first when declining down into the zone.
        - ``distal_line``: the zone bottom — the extreme boundary furthest
          from the approach direction.

    Attributes:
        zone_id: Unique identifier, e.g. ``"DEMAND_XAUUSD_M1_150"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        zone_top: Upper price boundary of the zone.
        zone_bottom: Lower price boundary of the zone.
        zone_midpoint: Midpoint of the zone — ``(zone_top + zone_bottom) / 2``.
        proximal_line: Closest boundary to approaching price — equals
            ``zone_top`` for demand zones (price approaches from above).
        distal_line: Furthest boundary from approaching price — equals
            ``zone_bottom`` for demand zones.
        base_start_index: Zero-based DataFrame index of the first base candle.
        base_end_index: Zero-based DataFrame index of the last base candle.
        base_start_time: UTC timestamp of the first base candle.
        base_end_time: UTC timestamp of the last base candle.
        explosion_candle_index: Index of the first candle of the explosive
            bullish move that defines the zone.
        explosion_direction: Always ``"bullish"`` for demand zones.
        base_candle_count: Number of consolidation candles forming the base.
        status: Lifecycle status — ``"active"``, ``"tested"``, or ``"broken"``.
        touch_count: Number of times price has returned into the zone.
        strength: Zone quality score in ``[0.0, 1.0]``, set by the engine.
        broken_at_time: UTC timestamp when the zone was broken, or ``None``.
        broken_at_price: Price at which the zone was broken, or ``None``.
    """

    zone_id: str
    symbol: str
    timeframe: str
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    proximal_line: float
    distal_line: float
    base_start_index: int
    base_end_index: int
    base_start_time: datetime
    base_end_time: datetime
    explosion_candle_index: int
    explosion_direction: Literal["bullish"]
    base_candle_count: int
    status: Literal["active", "tested", "broken"] = field(default="active")
    touch_count: int = field(default=0)
    strength: float = field(default=0.0)
    broken_at_time: Optional[datetime] = field(default=None)
    broken_at_price: Optional[float] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: On any validation failure — see module docstring for
                full rules.
        """
        _validate_zone_fields(
            zone_id=self.zone_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            zone_top=self.zone_top,
            zone_bottom=self.zone_bottom,
            zone_midpoint=self.zone_midpoint,
            proximal_line=self.proximal_line,
            distal_line=self.distal_line,
            base_start_index=self.base_start_index,
            base_end_index=self.base_end_index,
            explosion_candle_index=self.explosion_candle_index,
            base_candle_count=self.base_candle_count,
            touch_count=self.touch_count,
            strength=self.strength,
            status=self.status,
            broken_at_time=self.broken_at_time,
            broken_at_price=self.broken_at_price,
            class_name="DemandZone",
        )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Strength / ratio fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "zone_id": self.zone_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "proximal_line": round(self.proximal_line, 6),
            "distal_line": round(self.distal_line, 6),
            "base_start_index": self.base_start_index,
            "base_end_index": self.base_end_index,
            "base_start_time": self.base_start_time.isoformat(),
            "base_end_time": self.base_end_time.isoformat(),
            "explosion_candle_index": self.explosion_candle_index,
            "explosion_direction": self.explosion_direction,
            "base_candle_count": self.base_candle_count,
            "status": self.status,
            "touch_count": self.touch_count,
            "strength": round(self.strength, 4),
            "broken_at_time": (
                self.broken_at_time.isoformat()
                if self.broken_at_time is not None
                else None
            ),
            "broken_at_price": (
                round(self.broken_at_price, 6)
                if self.broken_at_price is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# SupplyDemandMap
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class SupplyDemandMap:
    """Complete Supply and Demand analysis result for one symbol and timeframe.

    Created by ``src/engine/supply_demand_engine.py`` and consumed by the POI
    engine, confluence engine, scanner, and dashboard.  Acts as the single
    source of truth for all Supply and Demand zone data on a given instrument /
    timeframe combination.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Total number of candles that were analysed.
        supply_zones: All active and tested :class:`SupplyZone` objects in
            chronological order.
        demand_zones: All active and tested :class:`DemandZone` objects in
            chronological order.
        broken_supply: All broken :class:`SupplyZone` objects kept for
            historical reference, in chronological order.
        broken_demand: All broken :class:`DemandZone` objects kept for
            historical reference, in chronological order.
        nearest_supply: The :class:`SupplyZone` closest above the current
            price, or ``None`` when none exist.
        nearest_demand: The :class:`DemandZone` closest below the current
            price, or ``None`` when none exist.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    supply_zones: list[SupplyZone] = field(default_factory=list)
    demand_zones: list[DemandZone] = field(default_factory=list)
    broken_supply: list[SupplyZone] = field(default_factory=list)
    broken_demand: list[DemandZone] = field(default_factory=list)
    nearest_supply: Optional[SupplyZone] = field(default=None)
    nearest_demand: Optional[DemandZone] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candle_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError(
                "SupplyDemandMap.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "SupplyDemandMap.timeframe must not be an empty string."
            )
        if self.candle_count < 0:
            raise ValueError(
                f"SupplyDemandMap.candle_count must be >= 0, "
                f"got {self.candle_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested zone objects are serialised via their own ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "supply_zones": [z.to_dict() for z in self.supply_zones],
            "demand_zones": [z.to_dict() for z in self.demand_zones],
            "broken_supply": [z.to_dict() for z in self.broken_supply],
            "broken_demand": [z.to_dict() for z in self.broken_demand],
            "nearest_supply": (
                self.nearest_supply.to_dict()
                if self.nearest_supply is not None
                else None
            ),
            "nearest_demand": (
                self.nearest_demand.to_dict()
                if self.nearest_demand is not None
                else None
            ),
        }