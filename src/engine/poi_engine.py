from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import pandas as pd

from src.engine.fvg_engine import FVG
from src.engine.order_block_engine import OrderBlock
from src.engine.supply_demand_engine import SupplyDemandZone
from src.utils.candle_utils import compute_atr_from_df
from src.utils.price_utils import price_distance_to_zone

__all__ = [
    "POIEngine",
    "POIEngineError",
    "create_engine",
    "PointOfInterest",
    "POIResult",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERLAP_TOLERANCE_PCT: float = 0.1
SWING_LOOKBACK: int = 50
MIN_CANDLES_REQUIRED: int = 10
MAX_ZONE_DISTANCE_ATR: float = 3.0

_REQUIRED_COLUMNS: frozenset[str] = frozenset({"high", "low", "close"})
_TYPE_OB: str = "ob"
_TYPE_FVG: str = "fvg"
_TYPE_SD: str = "sd"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class POIEngineError(Exception):
    """Raised when POIEngine encounters an unrecoverable input error."""


# ---------------------------------------------------------------------------
# Model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PointOfInterest:
    """A unified price zone where one or more SMC signals overlap.

    A Point of Interest (POI) aggregates active Order Blocks, FVGs, and
    Supply/Demand zones that share the same directional bias and whose price
    ranges intersect.  It becomes the primary unit consumed by the confluence
    scoring engine.

    Attributes:
        poi_id: Unique identifier —
            ``"POI_{direction}_{symbol}_{timeframe}_{anchor_index}"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        direction: Expected directional reaction — ``"bullish"`` (price rises
            from here) or ``"bearish"`` (price falls from here).
        zone_top: Upper price boundary of the merged zone.
        zone_bottom: Lower price boundary of the merged zone.
        zone_midpoint: Midpoint of the zone.
        zone_size: Width of the zone — ``zone_top - zone_bottom``.
        anchor_index: Most recent candle index among all contributing zones.
        anchor_time: UTC timestamp of the anchor candle.
        source_ob: Contributing :class:`~src.engine.order_block_engine.OrderBlock`,
            or ``None``.
        source_fvg: Contributing :class:`~src.engine.fvg_engine.FVG`, or
            ``None``.
        source_sd: Contributing
            :class:`~src.engine.supply_demand_engine.SupplyDemandZone`, or
            ``None``.
        has_order_block: ``True`` when an OB contributed to this POI.
        has_fvg: ``True`` when an FVG contributed to this POI.
        has_supply_demand: ``True`` when a Supply/Demand zone contributed.
        has_liquidity_sweep: Set later by the confluence engine.
        htf_aligned: Set later by the confluence engine.
        premium_discount_zone: ICT classification relative to the current
            price range.
        component_count: Number of distinct SMC components (OB, FVG, S&D)
            that contributed to this POI.
    """

    poi_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    zone_size: float
    anchor_index: int
    anchor_time: datetime
    source_ob: Optional[Any] = field(default=None)
    source_fvg: Optional[Any] = field(default=None)
    source_sd: Optional[Any] = field(default=None)
    has_order_block: bool = field(default=False)
    has_fvg: bool = field(default=False)
    has_supply_demand: bool = field(default=False)
    has_liquidity_sweep: bool = field(default=False)
    htf_aligned: bool = field(default=False)
    premium_discount_zone: Literal[
        "premium", "discount", "equilibrium", "unknown"
    ] = field(default="unknown")
    component_count: int = field(default=0)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``source_ob``, ``source_fvg``, and ``source_sd`` are serialised via
        their own ``to_dict()`` methods when present, otherwise ``None``.
        Price fields are rounded to 6 decimal places.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        def _safe_dict(obj: Any) -> Optional[dict]:
            if obj is None:
                return None
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            return None

        return {
            "poi_id": self.poi_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "zone_size": round(self.zone_size, 6),
            "anchor_index": self.anchor_index,
            "anchor_time": self.anchor_time.isoformat(),
            "source_ob": _safe_dict(self.source_ob),
            "source_fvg": _safe_dict(self.source_fvg),
            "source_sd": _safe_dict(self.source_sd),
            "has_order_block": self.has_order_block,
            "has_fvg": self.has_fvg,
            "has_supply_demand": self.has_supply_demand,
            "has_liquidity_sweep": self.has_liquidity_sweep,
            "htf_aligned": self.htf_aligned,
            "premium_discount_zone": self.premium_discount_zone,
            "component_count": self.component_count,
        }


@dataclass
class POIResult:
    """Complete Point of Interest aggregation for one symbol / timeframe.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        analyzed_at: UTC timestamp when the analysis was run.
        candle_count: Total candles in the source DataFrame.
        pois: All detected :class:`PointOfInterest` objects, sorted by
            ``anchor_index`` descending.
        bullish_pois: Subset with ``direction == "bullish"``.
        bearish_pois: Subset with ``direction == "bearish"``.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    pois: list[PointOfInterest] = field(default_factory=list)
    bullish_pois: list[PointOfInterest] = field(default_factory=list)
    bearish_pois: list[PointOfInterest] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "pois": [p.to_dict() for p in self.pois],
            "bullish_pois": [p.to_dict() for p in self.bullish_pois],
            "bearish_pois": [p.to_dict() for p in self.bearish_pois],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class POIEngine:
    """Aggregates SMC zones into unified Points of Interest (POIs).

    Collects active Order Blocks, FVGs, and Supply/Demand zones, groups
    overlapping same-direction zones into single POI objects, and enriches
    each POI with premium/discount context relative to the recent price range.

    This engine is a **pure aggregation** module.  It does not produce trade
    signals, manage positions, or connect to external data sources.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        ob_result: Optional[Any] = None,
        fvg_result: Optional[Any] = None,
        sd_result: Optional[Any] = None,
    ) -> POIResult:
        """Aggregate active SMC zones into Points of Interest.

        Parameters
        ----------
        df:
            OHLCV DataFrame sorted oldest-first with integer index.
            Required columns: ``high``, ``low``, ``close``.
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"H1"``.
        ob_result:
            Optional ``OrderBlockResult`` from the OB engine.
        fvg_result:
            Optional ``FVGResult`` from the FVG engine.
        sd_result:
            Optional ``SupplyDemandResult`` from the S&D engine.

        Returns
        -------
        POIResult
            Fully populated result.  Returns an empty result on validation
            failure — never raises.
        """
        empty = POIResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=len(df) if isinstance(df, pd.DataFrame) else 0,
        )

        if not self._validate(df, symbol, timeframe):
            return empty

        df = df.reset_index(drop=True)

        current_price = float(df["close"].iloc[-1]) if len(df) else 0.0
        atr = compute_atr_from_df(df)
        max_distance = (
            atr * MAX_ZONE_DISTANCE_ATR
            if atr > 0
            else current_price * 0.01
        )

        candidates = self._collect_candidates(
            ob_result, fvg_result, sd_result,
            current_price=current_price,
            max_distance=max_distance,
        )

        if not candidates:
            self._log.info(
                "[%s/%s] No active zone candidates — returning empty POIResult.",
                symbol, timeframe,
            )
            return empty

        pois = self._group_into_pois(candidates, symbol, timeframe, df)

        # Enrich with premium/discount
        for poi in pois:
            poi.premium_discount_zone = self._get_premium_discount(
                poi.zone_midpoint, df
            )

        bullish_pois = [p for p in pois if p.direction == "bullish"]
        bearish_pois = [p for p in pois if p.direction == "bearish"]

        self._log.info(
            "[%s/%s] POI analysis complete — total=%d  bullish=%d  bearish=%d",
            symbol, timeframe, len(pois), len(bullish_pois), len(bearish_pois),
        )

        return POIResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=len(df),
            pois=pois,
            bullish_pois=bullish_pois,
            bearish_pois=bearish_pois,
        )

    # ------------------------------------------------------------------
    # Private: validation
    # ------------------------------------------------------------------

    def _validate(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Validate the input DataFrame.

        Parameters
        ----------
        df:
            DataFrame to validate.
        symbol:
            Instrument name (log context).
        timeframe:
            Timeframe label (log context).

        Returns
        -------
        bool
            ``True`` when the DataFrame is usable.
        """
        if not isinstance(df, pd.DataFrame):
            self._log.warning(
                "[%s/%s] candles must be a pandas DataFrame.", symbol, timeframe
            )
            return False

        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing:
            self._log.warning(
                "[%s/%s] DataFrame missing required columns: %s.",
                symbol, timeframe, sorted(missing),
            )
            return False

        if len(df) < MIN_CANDLES_REQUIRED:
            self._log.warning(
                "[%s/%s] Insufficient rows (%d < %d) for POI analysis.",
                symbol, timeframe, len(df), MIN_CANDLES_REQUIRED,
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Private: candidate collection
    # ------------------------------------------------------------------

    def _collect_candidates(
        self,
        ob_result: Optional[Any],
        fvg_result: Optional[Any],
        sd_result: Optional[Any],
        current_price: float = 0.0,
        max_distance: float = 0.0,
    ) -> list[dict]:
        """Flatten active zones from all engine results into a candidate list."""
        candidates: list[dict] = []

        def _keep(top: float, bottom: float) -> bool:
            if current_price <= 0 or max_distance <= 0:
                return True
            return price_distance_to_zone(current_price, top, bottom) <= max_distance

        # --- Order Blocks ---
        if ob_result is not None and hasattr(ob_result, "active_obs"):
            for ob in ob_result.active_obs:
                if getattr(ob, "is_broken_retested", False):
                    continue
                if not _keep(ob.zone_top, ob.zone_bottom):
                    continue
                candidates.append(
                    {
                        "top": ob.zone_top,
                        "bottom": ob.zone_bottom,
                        "direction": ob.direction,
                        "index": ob.origin_index,
                        "time": ob.origin_time,
                        "type": _TYPE_OB,
                        "source": ob,
                    }
                )

        # --- FVGs ---
        if fvg_result is not None and hasattr(fvg_result, "active_fvgs"):
            for fvg in fvg_result.active_fvgs:
                if not _keep(fvg.gap_top, fvg.gap_bottom):
                    continue
                candidates.append(
                    {
                        "top": fvg.gap_top,
                        "bottom": fvg.gap_bottom,
                        "direction": fvg.direction,
                        "index": fvg.formation_index,
                        "time": fvg.formation_time,
                        "type": _TYPE_FVG,
                        "source": fvg,
                    }
                )

        # --- Supply / Demand ---
        if sd_result is not None and hasattr(sd_result, "active_zones"):
            for sd in sd_result.active_zones:
                if getattr(sd, "is_broken", False):
                    continue
                direction: Literal["bullish", "bearish"] = (
                    "bullish" if sd.zone_type == "demand" else "bearish"
                )
                if not _keep(sd.zone_top, sd.zone_bottom):
                    continue
                candidates.append(
                    {
                        "top": sd.zone_top,
                        "bottom": sd.zone_bottom,
                        "direction": direction,
                        "index": sd.explosion_index,
                        "time": sd.explosion_time,
                        "type": _TYPE_SD,
                        "source": sd,
                    }
                )

        self._log.debug(
            "Collected %d zone candidates (OB/FVG/SD).", len(candidates)
        )
        return candidates

    # ------------------------------------------------------------------
    # Private: grouping
    # ------------------------------------------------------------------

    def _group_into_pois(
        self,
        candidates: list[dict],
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> list[PointOfInterest]:
        """Group overlapping same-direction candidates into POIs.

        Uses a greedy single-pass algorithm:

        1. Sort candidates by ``index`` ascending (oldest first).
        2. For each candidate, check whether it overlaps with the current
           price range of any existing open group that shares its direction.
        3. If an overlap is found, merge the candidate into that group
           (expand the group's ``top`` / ``bottom`` boundaries).
        4. Otherwise, open a new group.
        5. Once all candidates are processed, build one
           :class:`PointOfInterest` per group.

        Parameters
        ----------
        candidates:
            Flat list of zone dicts from ``_collect_candidates``.
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.
        df:
            Source DataFrame (used only for timestamp resolution).

        Returns
        -------
        list[PointOfInterest]
            POIs sorted by ``anchor_index`` descending (most recent first).
        """
        # Sort oldest → newest for stable greedy grouping
        sorted_candidates = sorted(candidates, key=lambda c: c["index"])

        # Each group: {"top", "bottom", "direction", "members": list[dict]}
        groups: list[dict] = []

        for cand in sorted_candidates:
            merged = False
            for group in groups:
                if group["direction"] != cand["direction"]:
                    continue
                if self._zones_overlap(
                    group["top"], group["bottom"],
                    cand["top"], cand["bottom"],
                ):
                    # Expand group boundaries
                    group["top"]    = max(group["top"], cand["top"])
                    group["bottom"] = min(group["bottom"], cand["bottom"])
                    group["members"].append(cand)
                    merged = True
                    break

            if not merged:
                groups.append(
                    {
                        "top": cand["top"],
                        "bottom": cand["bottom"],
                        "direction": cand["direction"],
                        "members": [cand],
                    }
                )

        pois: list[PointOfInterest] = []
        for group in groups:
            poi = self._build_poi(group, symbol, timeframe)
            if poi is not None:
                pois.append(poi)

        # Sort by anchor_index descending (most recent first)
        pois.sort(key=lambda p: p.anchor_index, reverse=True)
        return pois

    def _build_poi(
        self,
        group: dict,
        symbol: str,
        timeframe: str,
    ) -> Optional[PointOfInterest]:
        """Build a single :class:`PointOfInterest` from a merged group.

        Parameters
        ----------
        group:
            Dict with keys ``top``, ``bottom``, ``direction``,
            ``members`` (list of candidate dicts).
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.

        Returns
        -------
        Optional[PointOfInterest]
            The constructed POI, or ``None`` when zone boundaries are
            degenerate.
        """
        zone_top    = float(group["top"])
        zone_bottom = float(group["bottom"])

        if zone_top <= zone_bottom:
            return None

        members: list[dict] = group["members"]

        # Anchor = most recent member
        anchor = max(members, key=lambda m: m["index"])
        anchor_index = anchor["index"]
        anchor_time  = anchor["time"]
        direction: Literal["bullish", "bearish"] = group["direction"]

        zone_midpoint = (zone_top + zone_bottom) / 2.0
        zone_size     = zone_top - zone_bottom

        poi_id = f"POI_{direction.upper()}_{symbol}_{timeframe}_{anchor_index}"

        # Identify contributing sources
        source_ob:  Optional[Any] = None
        source_fvg: Optional[Any] = None
        source_sd:  Optional[Any] = None

        for m in members:
            if m["type"] == _TYPE_OB and source_ob is None:
                source_ob = m["source"]
            elif m["type"] == _TYPE_FVG and source_fvg is None:
                source_fvg = m["source"]
            elif m["type"] == _TYPE_SD and source_sd is None:
                source_sd = m["source"]

        has_ob  = source_ob is not None
        has_fvg = source_fvg is not None
        has_sd  = source_sd is not None
        component_count = sum([has_ob, has_fvg, has_sd])

        return PointOfInterest(
            poi_id=poi_id,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            zone_top=zone_top,
            zone_bottom=zone_bottom,
            zone_midpoint=zone_midpoint,
            zone_size=zone_size,
            anchor_index=anchor_index,
            anchor_time=anchor_time,
            source_ob=source_ob,
            source_fvg=source_fvg,
            source_sd=source_sd,
            has_order_block=has_ob,
            has_fvg=has_fvg,
            has_supply_demand=has_sd,
            component_count=component_count,
        )

    # ------------------------------------------------------------------
    # Private: overlap check
    # ------------------------------------------------------------------

    def _zones_overlap(
        self,
        top_a: float,
        bottom_a: float,
        top_b: float,
        bottom_b: float,
    ) -> bool:
        """Determine whether two price ranges intersect.

        An overlap tolerance of ``OVERLAP_TOLERANCE_PCT`` percent of the
        smaller zone's size is applied to catch near-touching zones.

        Parameters
        ----------
        top_a, bottom_a:
            Boundaries of zone A.
        top_b, bottom_b:
            Boundaries of zone B.

        Returns
        -------
        bool
            ``True`` when the zones overlap (including within tolerance).
        """
        tolerance = (
            min(top_a - bottom_a, top_b - bottom_b)
            * OVERLAP_TOLERANCE_PCT
        )
        return top_a + tolerance >= bottom_b and bottom_a - tolerance <= top_b

    # ------------------------------------------------------------------
    # Private: premium / discount
    # ------------------------------------------------------------------

    def _get_premium_discount(
        self,
        zone_midpoint: float,
        df: pd.DataFrame,
    ) -> Literal["premium", "discount", "equilibrium", "unknown"]:
        """Classify a zone midpoint relative to the recent price range.

        Parameters
        ----------
        zone_midpoint:
            Midpoint of the POI zone to classify.
        df:
            OHLCV DataFrame (uses last ``SWING_LOOKBACK`` candles).

        Returns
        -------
        Literal["premium", "discount", "equilibrium", "unknown"]
            - ``"premium"``     → midpoint above equilibrium
            - ``"discount"``    → midpoint below equilibrium
            - ``"equilibrium"`` → midpoint exactly at equilibrium
            - ``"unknown"``     → insufficient data or zero range
        """
        lookback = min(SWING_LOOKBACK, len(df))
        if lookback < 2:
            return "unknown"

        highs = df["high"].iloc[-lookback:].to_numpy(dtype=float)
        lows  = df["low"].iloc[-lookback:].to_numpy(dtype=float)

        swing_high = float(highs.max())
        swing_low  = float(lows.min())
        price_range = swing_high - swing_low

        if price_range <= 0:
            return "unknown"

        equilibrium = (swing_high + swing_low) / 2.0

        if zone_midpoint > equilibrium:
            return "premium"
        if zone_midpoint < equilibrium:
            return "discount"
        return "equilibrium"


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_engine() -> POIEngine:
    """Factory — return a configured :class:`POIEngine`.

    Returns
    -------
    POIEngine
        Ready-to-use engine instance.
    """
    return POIEngine()