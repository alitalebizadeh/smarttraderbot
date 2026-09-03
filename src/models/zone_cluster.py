from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["ClusterFactor", "ZoneCluster", "ClusterMap"]


@dataclass(eq=True)
class ClusterFactor:
    """A single SMC zone that contributed to a :class:`ZoneCluster`.

    Stores only what is needed for display and confluence scoring —
    no reference to the full source engine object is kept.

    Attributes:
        factor_type: Category of the SMC zone.
        direction: Directional bias of this zone.
        zone_top: Upper price boundary of the individual zone.
        zone_bottom: Lower price boundary of the individual zone.
        strength: Quality score of this factor in ``[0.0, 1.0]``.
        description: Human-readable label shown on the dashboard or report,
            e.g. ``"Bearish OB at 4390.60–4393.39"``.
    """

    factor_type: Literal[
        "order_block", "fvg", "supply_demand", "liquidity_sweep", "bos"
    ]
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    strength: float
    description: str

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``zone_top`` must be > ``zone_bottom``.
                - ``zone_top`` and ``zone_bottom`` must each be > 0.
                - ``strength`` must be in ``[0.0, 1.0]``.
                - ``description`` must not be empty.
        """
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"ClusterFactor.zone_top ({self.zone_top}) must be > "
                f"zone_bottom ({self.zone_bottom})."
            )
        if self.zone_top <= 0:
            raise ValueError(
                f"ClusterFactor.zone_top must be > 0, got {self.zone_top}."
            )
        if self.zone_bottom <= 0:
            raise ValueError(
                f"ClusterFactor.zone_bottom must be > 0, got {self.zone_bottom}."
            )
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(
                f"ClusterFactor.strength must be between 0.0 and 1.0 "
                f"(inclusive), got {self.strength}."
            )
        if not self.description:
            raise ValueError(
                "ClusterFactor.description must not be an empty string."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        ``strength`` is rounded to 4 decimal places.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "factor_type": self.factor_type,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "strength": round(self.strength, 4),
            "description": self.description,
        }


@dataclass(eq=True)
class ZoneCluster:
    """A merged zone that aggregates multiple overlapping SMC zones.

    A ZoneCluster is the primary output of the zone cluster engine.
    It supersedes individual POI objects for display purposes by combining
    overlapping Order Blocks, FVGs, and Supply/Demand zones into a single
    unified, scored trade setup.

    The ``entry_zone_top`` / ``entry_zone_bottom`` fields define the tighter
    price area where a reaction is most likely:

    - **Bearish cluster**: entry zone is the *bottom* of the cluster
      (price approaches the zone from below).
    - **Bullish cluster**: entry zone is the *top* of the cluster
      (price approaches the zone from above).

    Attributes:
        cluster_id: Unique identifier, e.g.
            ``"CLUSTER_BEAR_XAUUSD_M1_001"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        direction: Expected directional reaction — ``"bullish"`` or
            ``"bearish"``.  Must match the prevailing market bias.
        zone_top: Highest top boundary across all merged zones.
        zone_bottom: Lowest bottom boundary across all merged zones.
        zone_midpoint: Midpoint of the full cluster zone.
        zone_size: Width of the full cluster zone.
        entry_zone_top: Upper boundary of the tighter entry sub-zone
            (proximal line).
        entry_zone_bottom: Lower boundary of the tighter entry sub-zone
            (distal line).
        factors: All :class:`ClusterFactor` objects merged into this
            cluster.
        factor_count: Number of factors.  Must equal ``len(factors)``.
        has_order_block: ``True`` when an OB contributed.
        has_fvg: ``True`` when an FVG contributed.
        has_supply_demand: ``True`` when a Supply/Demand zone contributed.
        has_liquidity_sweep: ``True`` when a liquidity sweep contributed.
        has_bos: ``True`` when a BOS / CHoCH contributed.
        premium_discount_zone: ICT classification of the cluster's position
            within the current price range.
        confluence_score: Aggregate score in ``[0.0, 100.0]`` set by the
            engine.
        grade: Letter grade derived from ``confluence_score``.
        grade_label: Human-readable grade label (may be in Persian for the
            report layer), e.g. ``"سیگنال قوی"``.
        grade_color: Hex colour code for the grade badge.
        is_tradeable: ``True`` when ``confluence_score >= 60``.
        created_at: UTC timestamp when this cluster was assembled.
        invalidated: ``True`` once price has traded through the zone,
            rendering it consumed.
    """

    cluster_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    zone_size: float
    entry_zone_top: float
    entry_zone_bottom: float
    factors: list[ClusterFactor]
    factor_count: int
    has_order_block: bool = field(default=False)
    has_fvg: bool = field(default=False)
    has_supply_demand: bool = field(default=False)
    has_liquidity_sweep: bool = field(default=False)
    has_bos: bool = field(default=False)
    premium_discount_zone: Literal[
        "premium", "discount", "equilibrium", "unknown"
    ] = field(default="unknown")
    confluence_score: float = field(default=0.0)
    grade: Literal["A+", "A", "B", "C", "D"] = field(default="D")
    grade_label: str = field(default="")
    grade_color: str = field(default="#6c757d")
    is_tradeable: bool = field(default=False)
    created_at: datetime = field(default_factory=datetime.utcnow)
    invalidated: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``cluster_id`` must not be empty.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``zone_top`` must be > ``zone_bottom``.
                - ``zone_top`` and ``zone_bottom`` must each be > 0.
                - ``zone_midpoint`` must be in
                  ``[zone_bottom, zone_top]`` (inclusive).
                - ``zone_size`` must be > 0.
                - ``entry_zone_top`` must be > ``entry_zone_bottom``.
                - ``factor_count`` must be >= 1.
                - ``confluence_score`` must be in ``[0.0, 100.0]``.
                - ``factors`` must not be empty.
        """
        if not self.cluster_id:
            raise ValueError(
                "ZoneCluster.cluster_id must not be an empty string."
            )
        if not self.symbol:
            raise ValueError(
                "ZoneCluster.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "ZoneCluster.timeframe must not be an empty string."
            )
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"ZoneCluster.zone_top ({self.zone_top}) must be > "
                f"zone_bottom ({self.zone_bottom})."
            )
        if self.zone_top <= 0:
            raise ValueError(
                f"ZoneCluster.zone_top must be > 0, got {self.zone_top}."
            )
        if self.zone_bottom <= 0:
            raise ValueError(
                f"ZoneCluster.zone_bottom must be > 0, got {self.zone_bottom}."
            )
        if not (self.zone_bottom <= self.zone_midpoint <= self.zone_top):
            raise ValueError(
                f"ZoneCluster.zone_midpoint ({self.zone_midpoint}) must be "
                f"between zone_bottom ({self.zone_bottom}) and zone_top "
                f"({self.zone_top}) inclusive."
            )
        if self.zone_size <= 0:
            raise ValueError(
                f"ZoneCluster.zone_size must be > 0, got {self.zone_size}."
            )
        if self.entry_zone_top <= self.entry_zone_bottom:
            raise ValueError(
                f"ZoneCluster.entry_zone_top ({self.entry_zone_top}) must be "
                f"> entry_zone_bottom ({self.entry_zone_bottom})."
            )
        if self.factor_count < 1:
            raise ValueError(
                f"ZoneCluster.factor_count must be >= 1, got {self.factor_count}."
            )
        if not (0.0 <= self.confluence_score <= 100.0):
            raise ValueError(
                f"ZoneCluster.confluence_score must be between 0.0 and 100.0 "
                f"(inclusive), got {self.confluence_score}."
            )
        if not self.factors:
            raise ValueError(
                "ZoneCluster.factors must not be empty — at least one "
                "ClusterFactor is required."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Score and strength fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`ClusterFactor` objects are serialised via their own
        ``to_dict()`` methods.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "cluster_id": self.cluster_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "zone_size": round(self.zone_size, 6),
            "entry_zone_top": round(self.entry_zone_top, 6),
            "entry_zone_bottom": round(self.entry_zone_bottom, 6),
            "factors": [f.to_dict() for f in self.factors],
            "factor_count": self.factor_count,
            "has_order_block": self.has_order_block,
            "has_fvg": self.has_fvg,
            "has_supply_demand": self.has_supply_demand,
            "has_liquidity_sweep": self.has_liquidity_sweep,
            "has_bos": self.has_bos,
            "premium_discount_zone": self.premium_discount_zone,
            "confluence_score": round(self.confluence_score, 4),
            "grade": self.grade,
            "grade_label": self.grade_label,
            "grade_color": self.grade_color,
            "is_tradeable": self.is_tradeable,
            "created_at": self.created_at.isoformat(),
            "invalidated": self.invalidated,
        }


@dataclass(eq=False)
class ClusterMap:
    """All :class:`ZoneCluster` objects for one symbol / timeframe scan.

    The primary container consumed by the dashboard, report generator, and
    MT5 display layer.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        market_bias: Overall directional bias detected by the market
            structure engine.
        scanned_at: UTC timestamp when the scan completed.
        clusters: All detected :class:`ZoneCluster` objects, sorted by
            ``confluence_score`` descending.
        top_cluster: The highest-scored :class:`ZoneCluster`, or ``None``
            when no clusters were found.
        total_count: Total number of clusters detected.
        tradeable_count: Number of clusters where ``is_tradeable`` is
            ``True``.
    """

    symbol: str
    timeframe: str
    market_bias: Literal["bullish", "bearish", "neutral"]
    scanned_at: datetime
    clusters: list[ZoneCluster] = field(default_factory=list)
    top_cluster: Optional[ZoneCluster] = field(default=None)
    total_count: int = field(default=0)
    tradeable_count: int = field(default=0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``total_count`` must be >= 0.
                - ``tradeable_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError(
                "ClusterMap.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "ClusterMap.timeframe must not be an empty string."
            )
        if self.total_count < 0:
            raise ValueError(
                f"ClusterMap.total_count must be >= 0, got {self.total_count}."
            )
        if self.tradeable_count < 0:
            raise ValueError(
                f"ClusterMap.tradeable_count must be >= 0, "
                f"got {self.tradeable_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`ZoneCluster` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market_bias": self.market_bias,
            "scanned_at": self.scanned_at.isoformat(),
            "clusters": [c.to_dict() for c in self.clusters],
            "top_cluster": (
                self.top_cluster.to_dict()
                if self.top_cluster is not None
                else None
            ),
            "total_count": self.total_count,
            "tradeable_count": self.tradeable_count,
        }