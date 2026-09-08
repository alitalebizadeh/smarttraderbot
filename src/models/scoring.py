from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

__all__ = ["ScoreResult", "ScanSummary", "ScoringOutput"]


@dataclass(eq=True)
class ScoreResult:
    """A fully enriched, display-ready result for a single scored POI.

    Produced by :class:`~src.scoring.zone_scorer.ZoneScorer` from a
    :class:`~src.models.confluence.ConfluenceResult`.  Contains every field
    the dashboard layer needs to render a setup card.

    Attributes:
        poi_id: Unique POI identifier.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        direction: ``"bullish"`` or ``"bearish"``.
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.
        zone_midpoint: Midpoint of the zone.
        zone_size: Width of the zone.
        total_score: Numeric confluence score in ``[0.0, 100.0]``.
        grade: Letter grade — ``"A+"``, ``"A"``, ``"B"``, ``"C"``, or
            ``"D"``.
        grade_label: Human-readable grade label.
        grade_color: Hex colour for the grade badge.
        show_on_dashboard: ``True`` when this result should appear on the
            HTML dashboard.
        is_tradeable: ``True`` when ``total_score >= 60``.
        direction_emoji: Emoji representing the direction.
        premium_discount_zone: ICT zone classification.
        scored_at: UTC timestamp when scoring occurred.
        order_block_score: Points from the Order Block factor.
        fvg_score: Points from the FVG factor.
        liquidity_sweep_score: Points from the Liquidity Sweep factor.
        bos_score: Points from the BOS factor.
        premium_discount_score: Points from the Premium/Discount factor.
        htf_alignment_score: Points from the HTF Alignment factor.
        has_order_block: Whether an OB contributed.
        has_fvg: Whether an FVG contributed.
        has_liquidity_sweep: Whether a liquidity sweep was detected.
        has_bos: Whether a BOS was confirmed.
        htf_aligned: Whether HTF bias aligns with direction.
        summary: One-line human-readable summary string.
    """

    poi_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    zone_size: float
    total_score: float
    grade: Literal["A+", "A", "B", "C", "D"]
    grade_label: str
    grade_color: str
    show_on_dashboard: bool
    is_tradeable: bool
    direction_emoji: str
    premium_discount_zone: Literal["premium", "discount", "equilibrium", "unknown"]
    scored_at: datetime
    order_block_score: float
    fvg_score: float
    liquidity_sweep_score: float
    bos_score: float
    premium_discount_score: float
    htf_alignment_score: float
    has_order_block: bool
    has_fvg: bool
    has_liquidity_sweep: bool
    has_bos: bool
    htf_aligned: bool
    summary: str

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
            ``datetime`` values are ISO 8601 strings.
            Price and score fields are rounded to 4 decimal places.
        """
        return {
            "poi_id": self.poi_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 4),
            "zone_bottom": round(self.zone_bottom, 4),
            "zone_midpoint": round(self.zone_midpoint, 4),
            "zone_size": round(self.zone_size, 4),
            "total_score": round(self.total_score, 4),
            "grade": self.grade,
            "grade_label": self.grade_label,
            "grade_color": self.grade_color,
            "show_on_dashboard": self.show_on_dashboard,
            "is_tradeable": self.is_tradeable,
            "direction_emoji": self.direction_emoji,
            "premium_discount_zone": self.premium_discount_zone,
            "scored_at": self.scored_at.isoformat(),
            "order_block_score": round(self.order_block_score, 4),
            "fvg_score": round(self.fvg_score, 4),
            "liquidity_sweep_score": round(self.liquidity_sweep_score, 4),
            "bos_score": round(self.bos_score, 4),
            "premium_discount_score": round(self.premium_discount_score, 4),
            "htf_alignment_score": round(self.htf_alignment_score, 4),
            "has_order_block": self.has_order_block,
            "has_fvg": self.has_fvg,
            "has_liquidity_sweep": self.has_liquidity_sweep,
            "has_bos": self.has_bos,
            "htf_aligned": self.htf_aligned,
            "summary": self.summary,
        }


@dataclass(eq=True)
class ScanSummary:
    """Aggregate statistics for one complete symbol / timeframe scan.

    Attributes:
        symbol: Instrument name.
        timeframe: Timeframe label.
        current_price: Last close price at scan time.
        scan_duration_ms: Wall-clock time taken to complete the scan.
        total_pois_found: Total POIs returned by the POI engine.
        total_scored: Number of POIs with a score > 0.
        avg_score: Mean score across all scored results.
        top_score: Highest score found.
        top_poi_id: POI ID of the highest-scored result, or ``None``.
        aplus_count: Count of ``"A+"`` grades.
        a_count: Count of ``"A"`` grades.
        b_count: Count of ``"B"`` grades.
        c_count: Count of ``"C"`` grades.
        d_count: Count of ``"D"`` grades.
        bullish_count: Count of bullish results.
        bearish_count: Count of bearish results.
        generated_at: UTC timestamp of this summary.
    """

    symbol: str
    timeframe: str
    current_price: float
    scan_duration_ms: float
    total_pois_found: int
    total_scored: int
    avg_score: float
    top_score: float
    top_poi_id: Optional[str]
    aplus_count: int
    a_count: int
    b_count: int
    c_count: int
    d_count: int
    bullish_count: int
    bearish_count: int
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "current_price": round(self.current_price, 6),
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "total_pois_found": self.total_pois_found,
            "total_scored": self.total_scored,
            "avg_score": round(self.avg_score, 4),
            "top_score": round(self.top_score, 4),
            "top_poi_id": self.top_poi_id,
            "aplus_count": self.aplus_count,
            "a_count": self.a_count,
            "b_count": self.b_count,
            "c_count": self.c_count,
            "d_count": self.d_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(eq=False)
class ScoringOutput:
    """Complete scoring output for one symbol / timeframe scan.

    Produced by :class:`~src.scoring.zone_scorer.ZoneScorer` and consumed
    by the scanner and dashboard layers.

    Attributes:
        symbol: Instrument name.
        timeframe: Timeframe label.
        generated_at: UTC timestamp when scoring was completed.
        summary: Aggregate :class:`ScanSummary` for this scan.
        all_results: All :class:`ScoreResult` objects, sorted by
            ``total_score`` descending.
        dashboard_results: Subset of ``all_results`` where
            ``show_on_dashboard`` is ``True``.
        top_result: Highest-scored :class:`ScoreResult` eligible for the
            dashboard, or the overall highest if none qualify, or ``None``
            when no results exist.
    """

    symbol: str
    timeframe: str
    generated_at: datetime
    summary: ScanSummary
    all_results: list[ScoreResult] = field(default_factory=list)
    dashboard_results: list[ScoreResult] = field(default_factory=list)
    top_result: Optional[ScoreResult] = field(default=None)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary.to_dict(),
            "all_results": [r.to_dict() for r in self.all_results],
            "dashboard_results": [r.to_dict() for r in self.dashboard_results],
            "top_result": (
                self.top_result.to_dict() if self.top_result is not None else None
            ),
        }