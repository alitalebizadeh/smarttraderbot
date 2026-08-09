from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["POIFactor", "PointOfInterest", "POIList"]


@dataclass(eq=True)
class POIFactor:
    """A single contributing factor to a POI's confluence score.

    A POIFactor is a lightweight record that represents one SMC/ICT concept
    that contributes to a Point of Interest.  It stores only what is needed
    for scoring and dashboard display — no references to the full source
    dataclass are kept.

    Attributes:
        factor_type: Category of the SMC concept this factor represents.
            One of ``"order_block"``, ``"fvg"``, ``"supply_demand"``,
            ``"liquidity_sweep"``, ``"bos"``, ``"premium_discount"``,
            or ``"htf_alignment"``.
        factor_id: Unique identifier of the source object, e.g. an ``ob_id``
            or ``fvg_id``, or a descriptive string for derived factors.
        direction: Directional bias of this factor — ``"bullish"`` or
            ``"bearish"``.
        strength: Quality score of this individual factor in ``[0.0, 1.0]``.
        description: Human-readable label shown on the dashboard, e.g.
            ``"Bullish OB at 2019.75 midpoint"``.
    """

    factor_type: Literal[
        "order_block",
        "fvg",
        "supply_demand",
        "liquidity_sweep",
        "bos",
        "premium_discount",
        "htf_alignment",
    ]
    factor_id: str
    direction: Literal["bullish", "bearish"]
    strength: float
    description: str

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``factor_id`` must not be empty.
                - ``description`` must not be empty.
                - ``strength`` must be in the range ``[0.0, 1.0]`` (inclusive).
        """
        if not self.factor_id:
            raise ValueError("POIFactor.factor_id must not be an empty string.")
        if not self.description:
            raise ValueError(
                "POIFactor.description must not be an empty string."
            )
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(
                f"POIFactor.strength must be between 0.0 and 1.0 (inclusive), "
                f"got {self.strength}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Strength is rounded to 4 decimal places.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "factor_type": self.factor_type,
            "factor_id": self.factor_id,
            "direction": self.direction,
            "strength": round(self.strength, 4),
            "description": self.description,
        }


@dataclass(eq=True)
class PointOfInterest:
    """A unified, scored price zone aggregating multiple SMC/ICT concepts.

    A Point of Interest (POI) is the primary output of the POI engine.  It
    combines Order Blocks, FVGs, Supply & Demand zones, liquidity sweeps, and
    market structure context into a single zone with a confluence score.

    ICT Premium / Discount classification:
        - **Bullish POI**: ideally located in the *discount* zone
          (below the 50 % equilibrium of the current price range).
        - **Bearish POI**: ideally located in the *premium* zone
          (above the 50 % equilibrium of the current price range).
        - Within ± 10 % of the midpoint → ``"equilibrium"``.

    Attributes:
        poi_id: Unique identifier,
            e.g. ``"POI_BULL_XAUUSD_M1_42_1705312800"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        direction: Expected directional move from this zone — ``"bullish"``
            (price expected to rise) or ``"bearish"`` (price expected to fall).
        zone_top: Upper price boundary of the POI zone.
        zone_bottom: Lower price boundary of the POI zone.
        zone_midpoint: Midpoint of the zone — ``(zone_top + zone_bottom) / 2``.
        zone_size: Width of the zone — ``zone_top - zone_bottom``.
        created_at: UTC timestamp when this POI was first identified.
        factors: All :class:`POIFactor` objects that contribute to this POI's
            confluence.  May be empty at creation; filled by the POI engine.
        factor_count: Number of factors in ``factors``.  Must match
            ``len(factors)`` at creation time.
        has_order_block: ``True`` when an Order Block overlaps this zone.
        has_fvg: ``True`` when a Fair Value Gap overlaps this zone.
        has_supply_demand: ``True`` when a Supply or Demand zone overlaps.
        has_liquidity_sweep: ``True`` when a preceding liquidity sweep was
            detected near this zone.
        has_bos: ``True`` when a BOS / CHoCH event supports this direction.
        in_premium_discount: ``True`` when the zone is in the correct
            premium / discount area for its direction.
        htf_aligned: ``True`` when the higher-timeframe bias matches
            ``direction``.
        premium_discount_zone: ICT classification of where this zone sits
            relative to the current range midpoint.
        raw_score: Confluence score before grade classification, in
            ``[0.0, 100.0]``.  Set by the scoring engine.
        is_active: ``False`` once price has moved through the zone and
            invalidated it.
        invalidated_at: UTC timestamp of invalidation, or ``None``.
        last_updated: UTC timestamp of the last field update, or ``None``.
    """

    poi_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    zone_size: float
    created_at: datetime
    factors: list[POIFactor]
    factor_count: int
    has_order_block: bool = field(default=False)
    has_fvg: bool = field(default=False)
    has_supply_demand: bool = field(default=False)
    has_liquidity_sweep: bool = field(default=False)
    has_bos: bool = field(default=False)
    in_premium_discount: bool = field(default=False)
    htf_aligned: bool = field(default=False)
    premium_discount_zone: Literal[
        "premium", "discount", "equilibrium", "unknown"
    ] = field(default="unknown")
    raw_score: float = field(default=0.0)
    is_active: bool = field(default=True)
    invalidated_at: Optional[datetime] = field(default=None)
    last_updated: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``poi_id`` must not be empty.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``zone_top`` must be > ``zone_bottom``.
                - ``zone_top`` and ``zone_bottom`` must each be > 0.
                - ``zone_midpoint`` must be in the range
                  ``[zone_bottom, zone_top]`` (inclusive).
                - ``zone_size`` must be > 0.
                - ``factor_count`` must be >= 0.
                - ``raw_score`` must be in the range ``[0.0, 100.0]``
                  (inclusive).
                - ``factors`` must be a list.
        """
        if not self.poi_id:
            raise ValueError(
                "PointOfInterest.poi_id must not be an empty string."
            )
        if not self.symbol:
            raise ValueError(
                "PointOfInterest.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "PointOfInterest.timeframe must not be an empty string."
            )
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"PointOfInterest.zone_top ({self.zone_top}) must be > "
                f"zone_bottom ({self.zone_bottom})."
            )
        if self.zone_top <= 0:
            raise ValueError(
                f"PointOfInterest.zone_top must be > 0, got {self.zone_top}."
            )
        if self.zone_bottom <= 0:
            raise ValueError(
                f"PointOfInterest.zone_bottom must be > 0, "
                f"got {self.zone_bottom}."
            )
        if not (self.zone_bottom <= self.zone_midpoint <= self.zone_top):
            raise ValueError(
                f"PointOfInterest.zone_midpoint ({self.zone_midpoint}) must "
                f"be between zone_bottom ({self.zone_bottom}) and zone_top "
                f"({self.zone_top}) inclusive."
            )
        if self.zone_size <= 0:
            raise ValueError(
                f"PointOfInterest.zone_size must be > 0, got {self.zone_size}."
            )
        if self.factor_count < 0:
            raise ValueError(
                f"PointOfInterest.factor_count must be >= 0, "
                f"got {self.factor_count}."
            )
        if not (0.0 <= self.raw_score <= 100.0):
            raise ValueError(
                f"PointOfInterest.raw_score must be between 0.0 and 100.0 "
                f"(inclusive), got {self.raw_score}."
            )
        if not isinstance(self.factors, list):
            raise ValueError("PointOfInterest.factors must be a list.")

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Score and strength fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`POIFactor` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "poi_id": self.poi_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "zone_size": round(self.zone_size, 6),
            "created_at": self.created_at.isoformat(),
            "factors": [f.to_dict() for f in self.factors],
            "factor_count": self.factor_count,
            "has_order_block": self.has_order_block,
            "has_fvg": self.has_fvg,
            "has_supply_demand": self.has_supply_demand,
            "has_liquidity_sweep": self.has_liquidity_sweep,
            "has_bos": self.has_bos,
            "in_premium_discount": self.in_premium_discount,
            "htf_aligned": self.htf_aligned,
            "premium_discount_zone": self.premium_discount_zone,
            "raw_score": round(self.raw_score, 4),
            "is_active": self.is_active,
            "invalidated_at": (
                self.invalidated_at.isoformat()
                if self.invalidated_at is not None
                else None
            ),
            "last_updated": (
                self.last_updated.isoformat()
                if self.last_updated is not None
                else None
            ),
        }


@dataclass(eq=False)
class POIList:
    """Container for all Points of Interest found in one symbol + timeframe scan.

    Created by ``src/engine/poi_engine.py`` and consumed by the confluence
    engine, scoring layer, scanner, and dashboard.  Provides both the
    complete POI list and pre-filtered directional views for efficient
    downstream access.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        scanned_at: UTC timestamp when the scan was executed.
        candle_count: Number of candles used in the scan.
        current_price: Last close price at scan time, used for proximity
            calculations and premium / discount classification.
        all_pois: All :class:`PointOfInterest` objects found, sorted by
            ``raw_score`` descending.
        bullish_pois: Subset of ``all_pois`` with ``direction == "bullish"``.
        bearish_pois: Subset of ``all_pois`` with ``direction == "bearish"``.
        top_poi: The highest-scored :class:`PointOfInterest` regardless of
            direction, or ``None`` when no POIs were found.
        total_count: Total number of POIs across all directions.
    """

    symbol: str
    timeframe: str
    scanned_at: datetime
    candle_count: int
    current_price: float
    all_pois: list[PointOfInterest] = field(default_factory=list)
    bullish_pois: list[PointOfInterest] = field(default_factory=list)
    bearish_pois: list[PointOfInterest] = field(default_factory=list)
    top_poi: Optional[PointOfInterest] = field(default=None)
    total_count: int = field(default=0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candle_count`` must be >= 0.
                - ``current_price`` must be > 0.
                - ``total_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError("POIList.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("POIList.timeframe must not be an empty string.")
        if self.candle_count < 0:
            raise ValueError(
                f"POIList.candle_count must be >= 0, got {self.candle_count}."
            )
        if self.current_price <= 0:
            raise ValueError(
                f"POIList.current_price must be > 0, got {self.current_price}."
            )
        if self.total_count < 0:
            raise ValueError(
                f"POIList.total_count must be >= 0, got {self.total_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`PointOfInterest` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.
        ``current_price`` is rounded to 6 decimal places.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "scanned_at": self.scanned_at.isoformat(),
            "candle_count": self.candle_count,
            "current_price": round(self.current_price, 6),
            "all_pois": [p.to_dict() for p in self.all_pois],
            "bullish_pois": [p.to_dict() for p in self.bullish_pois],
            "bearish_pois": [p.to_dict() for p in self.bearish_pois],
            "top_poi": (
                self.top_poi.to_dict() if self.top_poi is not None else None
            ),
            "total_count": self.total_count,
        }