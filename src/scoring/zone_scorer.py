from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src.models.scoring import ScanSummary, ScoreResult, ScoringOutput
from src.scoring.score_rules import (
    assign_grade,
    build_summary,
    get_direction_emoji,
    get_grade_color,
    get_grade_label,
    is_tradeable,
    show_on_dashboard,
    validate_score,
)

__all__ = ["ZoneScorer", "ZoneScorerError", "create_scorer"]

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ZoneScorerError(Exception):
    """Raised when ZoneScorer encounters an unrecoverable error."""


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class ZoneScorer:
    """Converts ConfluenceResult objects into display-ready ScoreResult objects.

    Acts as the bridge between the engine layer and the dashboard / scanner
    layer.  Applies all grade, label, colour, and visibility rules from
    :mod:`src.scoring.score_rules` and aggregates per-scan statistics into a
    :class:`~src.models.scoring.ScanSummary`.

    This class never raises from its public method — it always returns a
    valid :class:`~src.models.scoring.ScoringOutput`.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_confluence_map(
        self,
        confluence_map: Any,
        current_price: float,
        scan_duration_ms: float = 0.0,
    ) -> ScoringOutput:
        """Convert a ConfluenceMap into a fully scored ScoringOutput.

        Parameters
        ----------
        confluence_map:
            A ``ConfluenceMap`` produced by the confluence engine, or
            ``None``.  When ``None`` or empty, an empty
            :class:`~src.models.scoring.ScoringOutput` is returned.
        current_price:
            Last close price at scan time — stored in
            :class:`~src.models.scoring.ScanSummary`.
        scan_duration_ms:
            Wall-clock milliseconds taken by the upstream scan, for
            reporting purposes.  Default ``0.0``.

        Returns
        -------
        ScoringOutput
            Always a valid, non-raising result.
        """
        symbol    = _safe_get(confluence_map, "symbol", "")
        timeframe = _safe_get(confluence_map, "timeframe", "")

        if confluence_map is None or not hasattr(confluence_map, "results"):
            self._log.info(
                "[%s/%s] confluence_map is None or missing .results — "
                "returning empty ScoringOutput.",
                symbol, timeframe,
            )
            return self._empty_output(symbol, timeframe, current_price, scan_duration_ms)

        raw_results: list[Any] = getattr(confluence_map, "results", []) or []

        if not raw_results:
            self._log.info(
                "[%s/%s] No ConfluenceResults to score.",
                symbol, timeframe,
            )
            return self._empty_output(symbol, timeframe, current_price, scan_duration_ms)

        all_results: list[ScoreResult] = []

        for cr in raw_results:
            try:
                sr = self._convert_result(cr)
                all_results.append(sr)
            except Exception as exc:
                self._log.warning(
                    "[%s/%s] Failed to convert ConfluenceResult %s: %s",
                    symbol, timeframe,
                    _safe_get(cr, "poi_id", "unknown"), exc,
                )

        all_results.sort(key=lambda r: r.total_score, reverse=True)

        dashboard_results = [r for r in all_results if r.show_on_dashboard]

        top_result: Optional[ScoreResult] = None
        if dashboard_results:
            top_result = dashboard_results[0]
        elif all_results:
            top_result = all_results[0]

        summary = self._build_scan_summary(
            symbol=symbol,
            timeframe=timeframe,
            all_results=all_results,
            current_price=current_price,
            scan_duration_ms=scan_duration_ms,
        )

        self._log.info(
            "[%s/%s] Scoring complete — total=%d  dashboard=%d  "
            "top_score=%.1f",
            symbol, timeframe,
            len(all_results), len(dashboard_results),
            summary.top_score,
        )

        return ScoringOutput(
            symbol=symbol,
            timeframe=timeframe,
            generated_at=datetime.utcnow(),
            summary=summary,
            all_results=all_results,
            dashboard_results=dashboard_results,
            top_result=top_result,
        )

    # ------------------------------------------------------------------
    # Private: result conversion
    # ------------------------------------------------------------------

    def _convert_result(self, cr: Any) -> ScoreResult:
        """Convert a single ConfluenceResult to a ScoreResult.

        Parameters
        ----------
        cr:
            A ``ConfluenceResult`` object from the confluence engine.

        Returns
        -------
        ScoreResult
            Fully enriched, display-ready result.
        """
        raw_score = float(_safe_get(cr, "total_score", 0.0))
        total_score = validate_score(raw_score)

        grade      = str(_safe_get(cr, "grade", assign_grade(total_score)))
        grade_label = get_grade_label(grade)
        grade_color = get_grade_color(grade)
        tradeable   = is_tradeable(total_score)
        on_dash     = show_on_dashboard(grade)

        direction: str = str(_safe_get(cr, "direction", "bullish"))
        symbol:    str = str(_safe_get(cr, "symbol", ""))
        timeframe: str = str(_safe_get(cr, "timeframe", ""))
        emoji          = get_direction_emoji(direction)
        summary_str    = build_summary(
            symbol, timeframe, direction, total_score, grade_label
        )

        zone_top     = float(_safe_get(cr, "zone_top", 0.0))
        zone_bottom  = float(_safe_get(cr, "zone_bottom", 0.0))
        zone_midpoint = float(_safe_get(cr, "zone_midpoint", 0.0))
        zone_size    = max(zone_top - zone_bottom, 0.0)

        pd_zone: str = str(_safe_get(cr, "premium_discount_zone", "unknown"))

        # Per-factor scores
        ob_score   = float(_safe_get(cr, "order_block_score", 0.0))
        fvg_score  = float(_safe_get(cr, "fvg_score", 0.0))
        liq_score  = float(_safe_get(cr, "liquidity_sweep_score", 0.0))
        bos_score  = float(_safe_get(cr, "bos_score", 0.0))
        pd_score   = float(_safe_get(cr, "premium_discount_score", 0.0))
        htf_score  = float(_safe_get(cr, "htf_alignment_score", 0.0))

        # Factor presence flags
        factor_scores_list = _safe_get(cr, "factor_scores", []) or []
        flags = self._extract_factor_flags(factor_scores_list)

        return ScoreResult(
            poi_id=str(_safe_get(cr, "poi_id", "")),
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,  # type: ignore[arg-type]
            zone_top=zone_top,
            zone_bottom=zone_bottom,
            zone_midpoint=zone_midpoint,
            zone_size=zone_size,
            total_score=total_score,
            grade=grade,  # type: ignore[arg-type]
            grade_label=grade_label,
            grade_color=grade_color,
            show_on_dashboard=on_dash,
            is_tradeable=tradeable,
            direction_emoji=emoji,
            premium_discount_zone=pd_zone,  # type: ignore[arg-type]
            scored_at=datetime.utcnow(),
            order_block_score=ob_score,
            fvg_score=fvg_score,
            liquidity_sweep_score=liq_score,
            bos_score=bos_score,
            premium_discount_score=pd_score,
            htf_alignment_score=htf_score,
            has_order_block=flags["order_block"],
            has_fvg=flags["fvg"],
            has_liquidity_sweep=flags["liquidity_sweep"],
            has_bos=flags["bos"],
            htf_aligned=flags["htf_alignment"],
            summary=summary_str,
        )

    # ------------------------------------------------------------------
    # Private: factor flag extraction
    # ------------------------------------------------------------------

    def _extract_factor_flags(
        self, factor_scores: list[Any]
    ) -> dict[str, bool]:
        """Extract ``is_present`` flags from a list of FactorScore objects.

        Parameters
        ----------
        factor_scores:
            List of ``FactorScore`` objects (may be empty or ``None``).

        Returns
        -------
        dict[str, bool]
            Keys: ``"order_block"``, ``"fvg"``, ``"liquidity_sweep"``,
            ``"bos"``, ``"premium_discount"``, ``"htf_alignment"``.
            All values default to ``False`` when the list is empty or a
            factor type is not found.
        """
        flags: dict[str, bool] = {
            "order_block":     False,
            "fvg":             False,
            "liquidity_sweep": False,
            "bos":             False,
            "premium_discount": False,
            "htf_alignment":   False,
        }

        if not factor_scores:
            return flags

        for fs in factor_scores:
            factor_type = str(_safe_get(fs, "factor_type", ""))
            is_present  = bool(_safe_get(fs, "is_present", False))
            if factor_type in flags:
                flags[factor_type] = is_present

        return flags

    # ------------------------------------------------------------------
    # Private: scan summary
    # ------------------------------------------------------------------

    def _build_scan_summary(
        self,
        symbol: str,
        timeframe: str,
        all_results: list[ScoreResult],
        current_price: float,
        scan_duration_ms: float,
    ) -> ScanSummary:
        """Build a :class:`~src.models.scoring.ScanSummary` from scored results.

        Parameters
        ----------
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.
        all_results:
            All scored results for this scan.
        current_price:
            Last close price at scan time.
        scan_duration_ms:
            Wall-clock scan duration in milliseconds.

        Returns
        -------
        ScanSummary
            Aggregated statistics.
        """
        total_pois_found = len(all_results)
        total_scored     = sum(1 for r in all_results if r.total_score > 0)

        avg_score = (
            sum(r.total_score for r in all_results) / total_pois_found
            if total_pois_found > 0
            else 0.0
        )
        top_score  = max((r.total_score for r in all_results), default=0.0)
        top_poi_id = (
            max(all_results, key=lambda r: r.total_score).poi_id
            if all_results
            else None
        )

        aplus_count   = sum(1 for r in all_results if r.grade == "A+")
        a_count       = sum(1 for r in all_results if r.grade == "A")
        b_count       = sum(1 for r in all_results if r.grade == "B")
        c_count       = sum(1 for r in all_results if r.grade == "C")
        d_count       = sum(1 for r in all_results if r.grade == "D")
        bullish_count = sum(1 for r in all_results if r.direction == "bullish")
        bearish_count = sum(1 for r in all_results if r.direction == "bearish")

        return ScanSummary(
            symbol=symbol,
            timeframe=timeframe,
            current_price=current_price,
            scan_duration_ms=scan_duration_ms,
            total_pois_found=total_pois_found,
            total_scored=total_scored,
            avg_score=avg_score,
            top_score=top_score,
            top_poi_id=top_poi_id,
            aplus_count=aplus_count,
            a_count=a_count,
            b_count=b_count,
            c_count=c_count,
            d_count=d_count,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            generated_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Private: empty output helper
    # ------------------------------------------------------------------

    def _empty_output(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        scan_duration_ms: float,
    ) -> ScoringOutput:
        """Build an empty :class:`~src.models.scoring.ScoringOutput`.

        Parameters
        ----------
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.
        current_price:
            Last close price.
        scan_duration_ms:
            Scan duration in milliseconds.

        Returns
        -------
        ScoringOutput
            Output with no results.
        """
        summary = ScanSummary(
            symbol=symbol,
            timeframe=timeframe,
            current_price=current_price,
            scan_duration_ms=scan_duration_ms,
            total_pois_found=0,
            total_scored=0,
            avg_score=0.0,
            top_score=0.0,
            top_poi_id=None,
            aplus_count=0,
            a_count=0,
            b_count=0,
            c_count=0,
            d_count=0,
            bullish_count=0,
            bearish_count=0,
        )
        return ScoringOutput(
            symbol=symbol,
            timeframe=timeframe,
            generated_at=datetime.utcnow(),
            summary=summary,
            all_results=[],
            dashboard_results=[],
            top_result=None,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely retrieve an attribute from an object or a dict.

    Parameters
    ----------
    obj:
        Source object or dictionary.
    attr:
        Attribute / key name.
    default:
        Fallback value when the attribute is missing.

    Returns
    -------
    Any
        Resolved value or *default*.
    """
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_scorer() -> ZoneScorer:
    """Factory — return a configured :class:`ZoneScorer`.

    Returns
    -------
    ZoneScorer
        Ready-to-use scorer instance.
    """
    return ZoneScorer()