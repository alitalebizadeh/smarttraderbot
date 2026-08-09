from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["FactorScore", "ConfluenceResult", "ConfluenceMap"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPECTED_FACTOR_COUNT: int = 6


@dataclass(eq=True)
class FactorScore:
    """Score contribution of a single confluence factor for one POI.

    Each :class:`ConfluenceResult` contains exactly six ``FactorScore``
    objects — one per factor type.  Together they record which SMC signals
    were detected, how many points they awarded, and a brief human-readable
    summary of the evidence.

    Attributes:
        factor_type: Category of the SMC signal being scored.  One of
            ``"order_block"``, ``"fvg"``, ``"liquidity_sweep"``, ``"bos"``,
            ``"premium_discount"``, or ``"htf_alignment"``.
        is_present: ``True`` when this factor was detected for the POI.
        points_awarded: Points contributed by this factor.  Zero when the
            factor is absent; equal to ``max_points`` when fully present.
        max_points: Maximum points available for this factor type.
        evidence: Brief description of what was found, or ``"Not detected"``
            when the factor is absent.  Examples:

            - ``"Bullish OB at 2019.75, strength 0.82"``
            - ``"SSL sweep at 2018.00, returned inside"``
            - ``"In discount zone (38% of range)"``
            - ``"Not detected"``
    """

    factor_type: Literal[
        "order_block",
        "fvg",
        "liquidity_sweep",
        "bos",
        "premium_discount",
        "htf_alignment",
    ]
    is_present: bool
    points_awarded: float
    max_points: float
    evidence: str

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``points_awarded`` must be >= 0.
                - ``max_points`` must be > 0.
                - ``points_awarded`` must be <= ``max_points``.
                - ``evidence`` must not be empty.
                - When ``is_present`` is ``True``, ``points_awarded``
                  must be > 0.
        """
        if self.points_awarded < 0:
            raise ValueError(
                f"FactorScore.points_awarded must be >= 0, "
                f"got {self.points_awarded}."
            )
        if self.max_points <= 0:
            raise ValueError(
                f"FactorScore.max_points must be > 0, got {self.max_points}."
            )
        if self.points_awarded > self.max_points:
            raise ValueError(
                f"FactorScore.points_awarded ({self.points_awarded}) must be "
                f"<= max_points ({self.max_points})."
            )
        if not self.evidence:
            raise ValueError(
                "FactorScore.evidence must not be an empty string."
            )
        if self.is_present and self.points_awarded <= 0:
            raise ValueError(
                "FactorScore.points_awarded must be > 0 when is_present is True, "
                f"got {self.points_awarded}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Score fields are rounded to 4 decimal places.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "factor_type": self.factor_type,
            "is_present": self.is_present,
            "points_awarded": round(self.points_awarded, 4),
            "max_points": round(self.max_points, 4),
            "evidence": self.evidence,
        }


@dataclass(eq=True)
class ConfluenceResult:
    """Complete confluence evaluation for a single Point of Interest.

    Created by ``src/engine/confluence_engine.py`` after evaluating all six
    scoring factors for a POI.  Provides both the raw per-factor breakdown
    and aggregated metrics (total score, grade, tradeability flag) for
    downstream scoring and dashboard rendering.

    Scoring weights:
        - Order Block:       20 pts
        - FVG:               20 pts
        - Liquidity Sweep:   25 pts
        - BOS / CHoCH:       15 pts
        - Premium / Discount: 10 pts
        - HTF Alignment:     10 pts
        - **Total possible: 100 pts**

    Grade thresholds:
        - ``"A+"`` → ``total_score`` >= 80
        - ``"A"``  → ``total_score`` >= 65
        - ``"B"``  → ``total_score`` >= 50
        - ``"C"``  → ``total_score`` >= 35
        - ``"D"``  → ``total_score`` < 35

    Attributes:
        poi_id: Matches the ``poi_id`` of the evaluated
            :class:`~src.models.poi.PointOfInterest`.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        direction: Directional bias of the POI — ``"bullish"`` or
            ``"bearish"``.
        evaluated_at: UTC timestamp when confluence was calculated.
        factor_scores: Exactly six :class:`FactorScore` objects, one per
            factor type.
        total_score: Sum of all ``points_awarded`` values, in
            ``[0.0, 100.0]``.
        max_possible: Sum of all ``max_points`` values — always ``100.0``.
        score_pct: ``total_score / max_possible * 100``; numerically equal
            to ``total_score`` when ``max_possible`` is 100.
        factors_present: Count of factors where ``is_present`` is ``True``,
            in ``[0, 6]``.
        order_block_score: Points awarded by the Order Block factor.
        fvg_score: Points awarded by the FVG factor.
        liquidity_sweep_score: Points awarded by the Liquidity Sweep factor.
        bos_score: Points awarded by the BOS factor.
        premium_discount_score: Points awarded by the Premium/Discount factor.
        htf_alignment_score: Points awarded by the HTF Alignment factor.
        grade: Letter grade derived from ``total_score``.
        is_tradeable: ``True`` when ``total_score`` >= 60.
        zone_top: Upper boundary of the POI zone (copied for convenience).
        zone_bottom: Lower boundary of the POI zone (copied for convenience).
        zone_midpoint: Midpoint of the POI zone (copied for convenience).
    """

    poi_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    evaluated_at: datetime
    factor_scores: list[FactorScore]
    total_score: float
    max_possible: float
    score_pct: float
    factors_present: int
    order_block_score: float
    fvg_score: float
    liquidity_sweep_score: float
    bos_score: float
    premium_discount_score: float
    htf_alignment_score: float
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    grade: Literal["A+", "A", "B", "C", "D"] = field(default="D")
    is_tradeable: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``poi_id`` must not be empty.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``total_score`` must be in ``[0.0, 100.0]``.
                - ``max_possible`` must be > 0.
                - ``score_pct`` must be in ``[0.0, 100.0]``.
                - ``factors_present`` must be in ``[0, 6]``.
                - ``factor_scores`` must contain exactly 6 elements.
                - All individual score fields must be >= 0.
                - ``zone_top`` must be > ``zone_bottom``.
                - ``zone_top`` and ``zone_bottom`` must each be > 0.
        """
        if not self.poi_id:
            raise ValueError(
                "ConfluenceResult.poi_id must not be an empty string."
            )
        if not self.symbol:
            raise ValueError(
                "ConfluenceResult.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "ConfluenceResult.timeframe must not be an empty string."
            )
        if not (0.0 <= self.total_score <= 100.0):
            raise ValueError(
                f"ConfluenceResult.total_score must be between 0.0 and 100.0 "
                f"(inclusive), got {self.total_score}."
            )
        if self.max_possible <= 0:
            raise ValueError(
                f"ConfluenceResult.max_possible must be > 0, "
                f"got {self.max_possible}."
            )
        if not (0.0 <= self.score_pct <= 100.0):
            raise ValueError(
                f"ConfluenceResult.score_pct must be between 0.0 and 100.0 "
                f"(inclusive), got {self.score_pct}."
            )
        if not (0 <= self.factors_present <= _EXPECTED_FACTOR_COUNT):
            raise ValueError(
                f"ConfluenceResult.factors_present must be between 0 and "
                f"{_EXPECTED_FACTOR_COUNT} (inclusive), "
                f"got {self.factors_present}."
            )
        if len(self.factor_scores) != _EXPECTED_FACTOR_COUNT:
            raise ValueError(
                f"ConfluenceResult.factor_scores must contain exactly "
                f"{_EXPECTED_FACTOR_COUNT} elements, "
                f"got {len(self.factor_scores)}."
            )
        for name, value in (
            ("order_block_score", self.order_block_score),
            ("fvg_score", self.fvg_score),
            ("liquidity_sweep_score", self.liquidity_sweep_score),
            ("bos_score", self.bos_score),
            ("premium_discount_score", self.premium_discount_score),
            ("htf_alignment_score", self.htf_alignment_score),
        ):
            if value < 0:
                raise ValueError(
                    f"ConfluenceResult.{name} must be >= 0, got {value}."
                )
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"ConfluenceResult.zone_top ({self.zone_top}) must be > "
                f"zone_bottom ({self.zone_bottom})."
            )
        if self.zone_top <= 0:
            raise ValueError(
                f"ConfluenceResult.zone_top must be > 0, got {self.zone_top}."
            )
        if self.zone_bottom <= 0:
            raise ValueError(
                f"ConfluenceResult.zone_bottom must be > 0, "
                f"got {self.zone_bottom}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        All score and price fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`FactorScore` objects are serialised via their own
        ``to_dict()`` methods.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "poi_id": self.poi_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "evaluated_at": self.evaluated_at.isoformat(),
            "factor_scores": [fs.to_dict() for fs in self.factor_scores],
            "total_score": round(self.total_score, 4),
            "max_possible": round(self.max_possible, 4),
            "score_pct": round(self.score_pct, 4),
            "factors_present": self.factors_present,
            "order_block_score": round(self.order_block_score, 4),
            "fvg_score": round(self.fvg_score, 4),
            "liquidity_sweep_score": round(self.liquidity_sweep_score, 4),
            "bos_score": round(self.bos_score, 4),
            "premium_discount_score": round(self.premium_discount_score, 4),
            "htf_alignment_score": round(self.htf_alignment_score, 4),
            "grade": self.grade,
            "is_tradeable": self.is_tradeable,
            "zone_top": round(self.zone_top, 4),
            "zone_bottom": round(self.zone_bottom, 4),
            "zone_midpoint": round(self.zone_midpoint, 4),
        }


@dataclass(eq=False)
class ConfluenceMap:
    """All confluence results for one full symbol + timeframe scan.

    Created by ``src/engine/confluence_engine.py`` after evaluating every POI
    found in the scan.  Consumed by the scoring layer, scanner, and dashboard.
    Provides both the complete result list and pre-filtered tradeable views for
    efficient downstream access.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        scanned_at: UTC timestamp when the scan was executed.
        results: All :class:`ConfluenceResult` objects, sorted by
            ``total_score`` descending.
        tradeable: Subset of ``results`` where ``is_tradeable`` is ``True``,
            sorted by ``total_score`` descending.
        top_result: The highest-scored :class:`ConfluenceResult`, or ``None``
            when no POIs were evaluated.
        avg_score: Mean ``total_score`` across all results, in
            ``[0.0, 100.0]``.
        total_evaluated: Total number of POIs evaluated in this scan.
    """

    symbol: str
    timeframe: str
    scanned_at: datetime
    results: list[ConfluenceResult] = field(default_factory=list)
    tradeable: list[ConfluenceResult] = field(default_factory=list)
    top_result: Optional[ConfluenceResult] = field(default=None)
    avg_score: float = field(default=0.0)
    total_evaluated: int = field(default=0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``avg_score`` must be in ``[0.0, 100.0]``.
                - ``total_evaluated`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError(
                "ConfluenceMap.symbol must not be an empty string."
            )
        if not self.timeframe:
            raise ValueError(
                "ConfluenceMap.timeframe must not be an empty string."
            )
        if not (0.0 <= self.avg_score <= 100.0):
            raise ValueError(
                f"ConfluenceMap.avg_score must be between 0.0 and 100.0 "
                f"(inclusive), got {self.avg_score}."
            )
        if self.total_evaluated < 0:
            raise ValueError(
                f"ConfluenceMap.total_evaluated must be >= 0, "
                f"got {self.total_evaluated}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`ConfluenceResult` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.
        Score fields are rounded to 4 decimal places.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "scanned_at": self.scanned_at.isoformat(),
            "results": [r.to_dict() for r in self.results],
            "tradeable": [r.to_dict() for r in self.tradeable],
            "top_result": (
                self.top_result.to_dict()
                if self.top_result is not None
                else None
            ),
            "avg_score": round(self.avg_score, 4),
            "total_evaluated": self.total_evaluated,
        }