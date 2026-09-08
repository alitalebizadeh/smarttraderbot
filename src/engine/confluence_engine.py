from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from src.models.confluence import ConfluenceMap, ConfluenceResult, FactorScore

__all__ = ["ConfluenceEngine", "ConfluenceEngineError", "create_engine"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCORE_OB: float = 20.0
SCORE_FVG: float = 20.0
SCORE_LIQUIDITY: float = 25.0
SCORE_BOS: float = 15.0
SCORE_PREMIUM_DISCOUNT: float = 10.0
SCORE_HTF: float = 10.0
MAX_SCORE: float = 100.0

GRADE_THRESHOLDS: dict[str, float] = {
    "A+": 80.0,
    "A":  65.0,
    "B":  50.0,
    "C":  35.0,
}
TRADEABLE_THRESHOLD: float = 60.0

_FACTOR_COUNT: int = 6


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ConfluenceEngineError(Exception):
    """Raised when ConfluenceEngine encounters an unrecoverable error."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ConfluenceEngine:
    """Evaluates each Point of Interest against all six scoring factors.

    Reads from the POI engine, market structure engine, and liquidity engine
    to produce a :class:`~src.models.confluence.ConfluenceMap` containing
    one :class:`~src.models.confluence.ConfluenceResult` per POI.

    This engine is the core scoring intelligence of SmartTraderBot.  It does
    not place trades, generate entry signals, or connect to external data
    sources.

    Scoring weights:
        - Order Block:        20 pts
        - FVG:                20 pts
        - Liquidity Sweep:    25 pts
        - BOS / CHoCH:        15 pts
        - Premium / Discount: 10 pts
        - HTF Alignment:      10 pts
        - **Total possible:  100 pts**
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        poi_result: Any,
        market_structure: Optional[Any] = None,
        liquidity_map: Optional[Any] = None,
        htf_market_structure: Optional[Any] = None,
    ) -> ConfluenceMap:
        """Evaluate all POIs in *poi_result* and return a scored ConfluenceMap.

        Parameters
        ----------
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"H1"``.
        poi_result:
            ``POIResult`` from the POI engine, or ``None``.
        market_structure:
            Optional ``MarketStructure`` from the market structure engine.
        liquidity_map:
            Optional ``LiquidityMap`` from the liquidity engine.
        htf_market_structure:
            Optional higher-timeframe ``MarketStructure`` for HTF alignment
            scoring.

        Returns
        -------
        ConfluenceMap
            Fully populated map sorted by score descending.  Always returns
            a valid object — never raises.
        """
        empty = self._empty_map(symbol, timeframe)

        if poi_result is None:
            self._log.info(
                "[%s/%s] poi_result is None — returning empty ConfluenceMap.",
                symbol, timeframe,
            )
            return empty

        pois: list[Any] = getattr(poi_result, "pois", [])
        if not pois:
            self._log.info(
                "[%s/%s] No POIs to evaluate — returning empty ConfluenceMap.",
                symbol, timeframe,
            )
            return empty

        results: list[ConfluenceResult] = []

        for poi in pois:
            try:
                result = self._evaluate_poi(
                    poi,
                    market_structure=market_structure,
                    liquidity_map=liquidity_map,
                    htf_market_structure=htf_market_structure,
                )
                results.append(result)
            except Exception as exc:
                self._log.warning(
                    "[%s/%s] Failed to evaluate POI %s: %s",
                    symbol, timeframe,
                    getattr(poi, "poi_id", "unknown"), exc,
                )

        results.sort(key=lambda r: r.total_score, reverse=True)

        tradeable = [r for r in results if r.is_tradeable]
        top_result = results[0] if results else None
        avg_score  = (
            sum(r.total_score for r in results) / len(results)
            if results
            else 0.0
        )

        self._log.info(
            "[%s/%s] Confluence analysis complete — "
            "evaluated=%d  tradeable=%d  avg_score=%.2f",
            symbol, timeframe, len(results), len(tradeable), avg_score,
        )

        return ConfluenceMap(
            symbol=symbol,
            timeframe=timeframe,
            scanned_at=datetime.now(tz=timezone.utc),
            results=results,
            tradeable=tradeable,
            top_result=top_result,
            avg_score=avg_score,
            total_evaluated=len(results),
        )

    def filter_by_bias(
        self,
        confluence_map: Optional[ConfluenceMap],
        bias: str,
    ) -> Optional[ConfluenceMap]:
        """Keep only results whose direction matches market trend.

        Neutral / ranging bias leaves the map unchanged.  Counter-trend
        POIs are dropped when bias is ``bullish`` or ``bearish``.
        """
        if confluence_map is None:
            return None
        if bias not in ("bullish", "bearish"):
            return confluence_map

        aligned = [
            r for r in (confluence_map.results or [])
            if str(getattr(r, "direction", "")) == bias
        ]
        aligned.sort(key=lambda r: r.total_score, reverse=True)
        tradeable = [r for r in aligned if r.is_tradeable]
        avg_score = (
            sum(r.total_score for r in aligned) / len(aligned)
            if aligned
            else 0.0
        )
        removed = len(confluence_map.results or []) - len(aligned)
        if removed:
            self._log.info(
                "[%s/%s] Bias filter (%s): dropped %d counter-trend result(s).",
                confluence_map.symbol, confluence_map.timeframe, bias, removed,
            )

        return ConfluenceMap(
            symbol=confluence_map.symbol,
            timeframe=confluence_map.timeframe,
            scanned_at=confluence_map.scanned_at,
            results=aligned,
            tradeable=tradeable,
            top_result=aligned[0] if aligned else None,
            avg_score=avg_score,
            total_evaluated=len(aligned),
        )

    # ------------------------------------------------------------------
    # Private: POI evaluation
    # ------------------------------------------------------------------

    def _evaluate_poi(
        self,
        poi: Any,
        market_structure: Optional[Any],
        liquidity_map: Optional[Any],
        htf_market_structure: Optional[Any] = None,
    ) -> ConfluenceResult:
        """Evaluate a single POI across all six scoring factors.

        Parameters
        ----------
        poi:
            A ``PointOfInterest`` object from the POI engine.
        market_structure:
            Optional market structure context.
        liquidity_map:
            Optional liquidity context.
        htf_market_structure:
            Optional higher-timeframe market structure for HTF alignment.

        Returns
        -------
        ConfluenceResult
            Fully populated result for this POI.
        """
        fs_ob   = self._score_order_block(poi)
        fs_fvg  = self._score_fvg(poi)
        fs_liq  = self._score_liquidity_sweep(poi, liquidity_map)
        fs_bos  = self._score_bos(poi, market_structure)
        fs_pd   = self._score_premium_discount(poi)
        fs_htf  = self._score_htf_alignment(poi, htf_market_structure)

        factor_scores: list[FactorScore] = [
            fs_ob, fs_fvg, fs_liq, fs_bos, fs_pd, fs_htf
        ]

        total_score = sum(fs.points_awarded for fs in factor_scores)
        total_score = min(total_score, MAX_SCORE)

        score_pct       = total_score / MAX_SCORE * 100.0
        factors_present = sum(1 for fs in factor_scores if fs.is_present)
        grade           = self._assign_grade(total_score)
        is_tradeable    = total_score >= TRADEABLE_THRESHOLD

        self._log.debug(
            "POI %s evaluated — score=%.1f  grade=%s  tradeable=%s",
            getattr(poi, "poi_id", "unknown"),
            total_score, grade, is_tradeable,
        )

        return ConfluenceResult(
            poi_id=getattr(poi, "poi_id", "unknown"),
            symbol=getattr(poi, "symbol", ""),
            timeframe=getattr(poi, "timeframe", ""),
            direction=getattr(poi, "direction", "bullish"),
            evaluated_at=datetime.now(tz=timezone.utc),
            factor_scores=factor_scores,
            total_score=total_score,
            max_possible=MAX_SCORE,
            score_pct=score_pct,
            factors_present=factors_present,
            order_block_score=fs_ob.points_awarded,
            fvg_score=fs_fvg.points_awarded,
            liquidity_sweep_score=fs_liq.points_awarded,
            bos_score=fs_bos.points_awarded,
            premium_discount_score=fs_pd.points_awarded,
            htf_alignment_score=fs_htf.points_awarded,
            zone_top=getattr(poi, "zone_top", 0.0),
            zone_bottom=getattr(poi, "zone_bottom", 0.0),
            zone_midpoint=getattr(poi, "zone_midpoint", 0.0),
            premium_discount_zone=str(getattr(poi, "premium_discount_zone", "unknown")),
            grade=grade,
            is_tradeable=is_tradeable,
        )

    # ------------------------------------------------------------------
    # Private: individual factor scorers
    # ------------------------------------------------------------------

    def _score_order_block(self, poi: Any) -> FactorScore:
        """Evaluate the Order Block factor for *poi*.

        Parameters
        ----------
        poi:
            POI to evaluate.

        Returns
        -------
        FactorScore
            20 pts when ``poi.has_order_block`` is ``True``, 0 pts otherwise.
        """
        if getattr(poi, "has_order_block", False):
            direction = getattr(poi, "direction", "bullish").capitalize()
            zone_top    = getattr(poi, "zone_top", 0.0)
            zone_bottom = getattr(poi, "zone_bottom", 0.0)
            evidence = (
                f"{direction} OB at {zone_top:.5f}–{zone_bottom:.5f}"
            )
            return FactorScore(
                factor_type="order_block",
                is_present=True,
                points_awarded=SCORE_OB,
                max_points=SCORE_OB,
                evidence=evidence,
            )

        return FactorScore(
            factor_type="order_block",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_OB,
            evidence="Not detected",
        )

    def _score_fvg(self, poi: Any) -> FactorScore:
        """Evaluate the Fair Value Gap factor for *poi*.

        Parameters
        ----------
        poi:
            POI to evaluate.

        Returns
        -------
        FactorScore
            20 pts when ``poi.has_fvg`` is ``True``, 0 pts otherwise.
        """
        if getattr(poi, "has_fvg", False):
            zone_top    = getattr(poi, "zone_top", 0.0)
            zone_bottom = getattr(poi, "zone_bottom", 0.0)
            evidence = f"FVG gap {zone_top:.5f}–{zone_bottom:.5f}"
            return FactorScore(
                factor_type="fvg",
                is_present=True,
                points_awarded=SCORE_FVG,
                max_points=SCORE_FVG,
                evidence=evidence,
            )

        return FactorScore(
            factor_type="fvg",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_FVG,
            evidence="Not detected",
        )

    def _score_liquidity_sweep(
        self,
        poi: Any,
        liquidity_map: Optional[Any],
    ) -> FactorScore:
        """Evaluate the Liquidity Sweep factor for *poi*.

        When a recent sweep is present, ``poi.has_liquidity_sweep`` is also
        set to ``True`` on the POI object in-place.

        Parameters
        ----------
        poi:
            POI to evaluate.
        liquidity_map:
            Optional ``LiquidityMap`` from the liquidity engine.

        Returns
        -------
        FactorScore
            25 pts when a recent sweep exists, 0 pts otherwise.
        """
        if liquidity_map is None:
            return FactorScore(
                factor_type="liquidity_sweep",
                is_present=False,
                points_awarded=0.0,
                max_points=SCORE_LIQUIDITY,
                evidence="Not detected",
            )

        recent_sweep = getattr(liquidity_map, "recent_sweep", None)
        if recent_sweep is not None:
            if not bool(getattr(recent_sweep, "returned_inside", False)):
                return FactorScore(
                    factor_type="liquidity_sweep",
                    is_present=False,
                    points_awarded=0.0,
                    max_points=SCORE_LIQUIDITY,
                    evidence="Sweep without close rejection",
                )

            swept_level = getattr(recent_sweep, "swept_level", None)
            sweep_price = float(getattr(swept_level, "price", 0.0)) if swept_level else 0.0
            zone_top = float(getattr(poi, "zone_top", 0.0))
            zone_bottom = float(getattr(poi, "zone_bottom", 0.0))
            zone_size = max(zone_top - zone_bottom, 0.0)
            tolerance = max(zone_size * 2.0, zone_top * 0.001)

            if sweep_price > 0 and not (
                zone_bottom - tolerance <= sweep_price <= zone_top + tolerance
            ):
                return FactorScore(
                    factor_type="liquidity_sweep",
                    is_present=False,
                    points_awarded=0.0,
                    max_points=SCORE_LIQUIDITY,
                    evidence="Sweep not near POI zone",
                )

            # Mutate the POI flag so downstream engines see it
            try:
                poi.has_liquidity_sweep = True
            except AttributeError:
                self._logger.debug("POI does not support liquidity-sweep mutation")

            sweep_type  = getattr(recent_sweep, "sweep_type", "sweep")
            if swept_level is not None:
                price     = getattr(swept_level, "price", 0.0)
                evidence  = f"Recent {sweep_type} at {price:.5f}"
            else:
                evidence = f"Recent {sweep_type}"

            return FactorScore(
                factor_type="liquidity_sweep",
                is_present=True,
                points_awarded=SCORE_LIQUIDITY,
                max_points=SCORE_LIQUIDITY,
                evidence=evidence,
            )

        return FactorScore(
            factor_type="liquidity_sweep",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_LIQUIDITY,
            evidence="Not detected",
        )

    def _score_bos(
        self,
        poi: Any,
        market_structure: Optional[Any],
    ) -> FactorScore:
        """Evaluate the Break of Structure factor for *poi*.

        Parameters
        ----------
        poi:
            POI to evaluate.
        market_structure:
            Optional ``MarketStructure`` from the market structure engine.

        Returns
        -------
        FactorScore
            15 pts when a BOS is confirmed in the same direction as the POI,
            0 pts otherwise.
        """
        if market_structure is None:
            return FactorScore(
                factor_type="bos",
                is_present=False,
                points_awarded=0.0,
                max_points=SCORE_BOS,
                evidence="Not detected",
            )

        last_event = getattr(market_structure, "last_event", None)
        poi_dir    = getattr(poi, "direction", "")
        events     = getattr(market_structure, "events", []) or []

        bos_confirmed = False
        if last_event is not None:
            if (
                str(getattr(last_event, "event_type", "")) == "BOS"
                and str(getattr(last_event, "direction", "")) == poi_dir
            ):
                bos_confirmed = True

        if not bos_confirmed and events:
            recent = events[-5:]
            bos_confirmed = any(
                str(getattr(ev, "event_type", "")) == "BOS"
                and str(getattr(ev, "direction", "")) == poi_dir
                for ev in recent
            )

        if bos_confirmed:
            evidence = f"BOS {poi_dir} confirmed"
            return FactorScore(
                factor_type="bos",
                is_present=True,
                points_awarded=SCORE_BOS,
                max_points=SCORE_BOS,
                evidence=evidence,
            )

        return FactorScore(
            factor_type="bos",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_BOS,
            evidence="Not detected",
        )

    def _score_premium_discount(self, poi: Any) -> FactorScore:
        """Evaluate the Premium / Discount factor for *poi*.

        Parameters
        ----------
        poi:
            POI to evaluate.

        Returns
        -------
        FactorScore
            10 pts when the POI is in the optimal ICT zone for its direction:

            - **Bullish POI** in ``"discount"`` → 10 pts
            - **Bearish POI** in ``"premium"``  → 10 pts
        """
        direction = getattr(poi, "direction", "")
        pd_zone   = getattr(poi, "premium_discount_zone", "unknown")

        in_optimal_zone = (
            (direction == "bullish" and pd_zone == "discount")
            or (direction == "bearish" and pd_zone == "premium")
        )

        if in_optimal_zone:
            return FactorScore(
                factor_type="premium_discount",
                is_present=True,
                points_awarded=SCORE_PREMIUM_DISCOUNT,
                max_points=SCORE_PREMIUM_DISCOUNT,
                evidence=f"In {pd_zone} zone",
            )

        return FactorScore(
            factor_type="premium_discount",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_PREMIUM_DISCOUNT,
            evidence=f"Not in optimal zone ({pd_zone})",
        )

    def _score_htf_alignment(
        self,
        poi: Any,
        htf_ms: Optional[Any],
    ) -> FactorScore:
        """Evaluate the Higher-Timeframe Alignment factor for *poi*.

        The ``htf_aligned`` flag on the POI is set externally (by the
        scanner or a multi-timeframe coordinator) before this engine is
        called.  This method simply reads the flag.

        Parameters
        ----------
        poi:
            POI to evaluate.
        htf_ms:
            Optional higher-timeframe ``MarketStructure`` (reserved for
            future use; the flag on the POI takes precedence).

        Returns
        -------
        FactorScore
            10 pts when ``poi.htf_aligned`` is ``True``, 0 pts otherwise.
        """
        if getattr(poi, "htf_aligned", False):
            return FactorScore(
                factor_type="htf_alignment",
                is_present=True,
                points_awarded=SCORE_HTF,
                max_points=SCORE_HTF,
                evidence="HTF bias aligned with POI direction",
            )

        return FactorScore(
            factor_type="htf_alignment",
            is_present=False,
            points_awarded=0.0,
            max_points=SCORE_HTF,
            evidence="No HTF alignment data",
        )

    # ------------------------------------------------------------------
    # Private: grade assignment
    # ------------------------------------------------------------------

    def _assign_grade(
        self, total_score: float
    ) -> Literal["A+", "A", "B", "C", "D"]:
        """Map a numeric score to a letter grade.

        Parameters
        ----------
        total_score:
            Confluene score in ``[0.0, 100.0]``.

        Returns
        -------
        Literal["A+", "A", "B", "C", "D"]
            Grade according to ``GRADE_THRESHOLDS``.
        """
        for grade, threshold in GRADE_THRESHOLDS.items():
            if total_score >= threshold:
                return grade  # type: ignore[return-value]
        return "D"

    # ------------------------------------------------------------------
    # Private: utility
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_map(symbol: str, timeframe: str) -> ConfluenceMap:
        """Create an empty :class:`~src.models.confluence.ConfluenceMap`.

        Parameters
        ----------
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.

        Returns
        -------
        ConfluenceMap
            Map with no results.
        """
        return ConfluenceMap(
            symbol=symbol,
            timeframe=timeframe,
            scanned_at=datetime.now(tz=timezone.utc),
            results=[],
            tradeable=[],
            top_result=None,
            avg_score=0.0,
            total_evaluated=0,
        )


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_engine() -> ConfluenceEngine:
    """Factory — return a configured :class:`ConfluenceEngine`.

    Returns
    -------
    ConfluenceEngine
        Ready-to-use engine instance.
    """
    return ConfluenceEngine()