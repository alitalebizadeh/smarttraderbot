from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from src.models.zone_cluster import ClusterFactor, ClusterMap, ZoneCluster

__all__ = ["ZoneClusterEngine", "create_cluster_engine"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCORE_OB: float         = 20.0
_SCORE_FVG: float        = 20.0
_SCORE_SWEEP: float      = 25.0
_SCORE_BOS: float        = 15.0
_SCORE_SD: float         = 10.0
_SCORE_PD: float         = 10.0
_TRADEABLE_MIN: float    = 60.0
_PD_EQ_BAND: float       = 0.10
_RANGE_LOOKBACK: int     = 200
_BOS_EVENT_LOOKBACK: int = 5
_FIBO_382: float         = 0.382

_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (80.0, "A+"),
    (65.0, "A"),
    (50.0, "B"),
    (35.0, "C"),
]

_GRADE_LABELS: dict[str, str] = {
    "A+": "سیگنال A+",
    "A":  "سیگنال قوی",
    "B":  "سیگنال خوب",
    "C":  "سیگنال ضعیف",
    "D":  "سیگنال بد",
}

_GRADE_COLORS: dict[str, str] = {
    "A+": "#28a745",
    "A":  "#17a2b8",
    "B":  "#ffc107",
    "C":  "#fd7e14",
    "D":  "#dc3545",
}


# ---------------------------------------------------------------------------
# Internal raw-zone container
# ---------------------------------------------------------------------------

@dataclass
class _RawZone:
    zone_top: float
    zone_bottom: float
    direction: str
    factor_type: str
    strength: float
    description: str
    zone_id: str
    is_broken_retested: bool = False
    ob_time: Optional[datetime] = None
    fvg_time: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ZoneClusterEngine:
    """Clusters overlapping SMC zones into unified, scored trade setups.

    Reads raw engine outputs from a ``MarketSnapshot``, groups overlapping
    zones that share the prevailing market bias, scores each group by
    confluence, and returns a :class:`~src.models.zone_cluster.ClusterMap`.

    This engine never raises from :meth:`analyze`.

    Parameters
    ----------
    pip_size:
        Size of one pip for the instrument.  For XAUUSD: ``0.01``.
    cluster_tolerance_pips:
        Maximum gap in pips between zones to merge.  Default ``20.0``.
    min_factors:
        Minimum contributing factors per cluster.  Default ``1``.
    """

    def __init__(
        self,
        pip_size: float = 0.01,
        cluster_tolerance_pips: float = 50.0,
        min_factors: int = 1,
    ) -> None:
        self._pip_size    = pip_size
        self._tolerance   = cluster_tolerance_pips * pip_size
        self._min_factors = max(1, min_factors)
        self._log         = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        snapshot: Any,
        symbol: str,
        timeframe: str,
        candles: Any = None,
    ) -> ClusterMap:
        """Run the full clustering pipeline.

        Parameters
        ----------
        snapshot:
            ``MarketSnapshot`` from the timeframe scanner.
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"M1"``.
        candles:
            Optional raw OHLCV DataFrame for premium/discount range
            calculation.  When ``None``, the engine falls back to
            snapshot-level price data.

        Returns
        -------
        ClusterMap
            Always valid — empty on error or neutral bias.
        """
        try:
            return self._run(snapshot, symbol, timeframe, candles)
        except Exception as exc:
            self._log.error(
                "[%s/%s] ZoneClusterEngine.analyze failed: %s",
                symbol, timeframe, exc, exc_info=True,
            )
            return self._empty_map(symbol, timeframe, "neutral")

    # ------------------------------------------------------------------
    # Private: main pipeline
    # ------------------------------------------------------------------

    def _run(
        self,
        snapshot: Any,
        symbol: str,
        timeframe: str,
        candles: Any,
    ) -> ClusterMap:
        """Internal pipeline — may raise; caller wraps in try/except."""

        # Step 1 — Market bias
        ms   = getattr(snapshot, "market_structure", None)
        bias: str = "neutral"
        if ms is not None:
            bias = str(getattr(ms, "current_bias", "neutral"))

        if bias == "neutral":
            self._log.info(
                "[%s/%s] Market bias is neutral — returning empty ClusterMap.",
                symbol, timeframe,
            )
            return self._empty_map(symbol, timeframe, "neutral")

        direction: Literal["bullish", "bearish"] = bias  # type: ignore[assignment]

        # Step 2 — Collect raw zones aligned with bias
        raw_zones = self._collect_raw_zones(snapshot, direction)

        if not raw_zones:
            self._log.info(
                "[%s/%s] No active zones found for %s bias.",
                symbol, timeframe, direction,
            )
            return self._empty_map(symbol, timeframe, direction)

        # Step 5 — Cluster overlapping zones
        groups = self._cluster(raw_zones)

        # Compute premium/discount range once
        pd_range = self._price_range(snapshot, candles)

        # Build initial clusters (without sweep/BOS)
        clusters: list[ZoneCluster] = []
        for idx, group in enumerate(groups):
            if len(group) < self._min_factors:
                continue
            cluster = self._build_cluster(
                group, idx, symbol, timeframe, direction, pd_range, candles
            )
            if cluster is not None:
                clusters.append(cluster)

        # Step 3 — Attach liquidity sweep to nearest cluster
        self._attach_sweep(snapshot, clusters, direction)

        # Step 4 — Attach BOS context from structure events
        self._attach_bos(snapshot, clusters, direction)

        # Re-score all clusters after sweep / BOS attachment
        for c in clusters:
            self._score_cluster(c, pd_range, direction)

        # Step 10 — Sort by score descending
        clusters.sort(key=lambda c: c.confluence_score, reverse=True)
        clusters = clusters[:3]

        top        = clusters[0] if clusters else None
        top_score  = top.confluence_score if top else 0.0

        self._log.info(
            "[%s/%s] Clustered %d zones into %d clusters, "
            "bias=%s, top_score=%.1f",
            symbol, timeframe,
            len(raw_zones), len(clusters),
            direction, top_score,
        )

        return ClusterMap(
            symbol=symbol,
            timeframe=timeframe,
            market_bias=direction,
            scanned_at=datetime.utcnow(),
            clusters=clusters,
            top_cluster=top,
            total_count=len(clusters),
            tradeable_count=sum(1 for c in clusters if c.is_tradeable),
        )

    # ------------------------------------------------------------------
    # Step 2: raw zone collection
    # ------------------------------------------------------------------

    def _collect_raw_zones(
        self, snapshot: Any, direction: str
    ) -> list[_RawZone]:
        """Collect all active SMC zones that match *direction*.

        Parameters
        ----------
        snapshot:
            MarketSnapshot with engine results.
        direction:
            ``"bullish"`` or ``"bearish"``.

        Returns
        -------
        list[_RawZone]
            Flat list of valid raw zones.
        """
        zones: list[_RawZone] = []

        # --- Order Blocks ---
        ob_map = getattr(snapshot, "order_blocks", None)
        if ob_map is not None:
            ob_list = (
                getattr(ob_map, "bearish_obs", [])
                if direction == "bearish"
                else getattr(ob_map, "bullish_obs", [])
            ) or []

            for ob in ob_list:
                if getattr(ob, "is_mitigated", False):
                    continue
                top    = float(getattr(ob, "zone_top",    0.0))
                bottom = float(getattr(ob, "zone_bottom", 0.0))
                if not self._valid_zone(top, bottom):
                    continue
                label = "Bearish" if direction == "bearish" else "Bullish"
                zones.append(_RawZone(
                    zone_top=top,
                    zone_bottom=bottom,
                    direction=direction,
                    factor_type="order_block",
                    strength=float(getattr(ob, "strength", 0.5)),
                    description=f"{label} OB at {bottom:.2f}–{top:.2f}",
                    zone_id=str(getattr(ob, "ob_id", "")),
                    is_broken_retested=bool(getattr(ob, "is_broken_retested", False)),
                    ob_time=getattr(ob, "origin_time", getattr(ob, "candle_time", None)),
                ))

        # --- FVGs ---
        fvg_map = getattr(snapshot, "fvgs", None)
        if fvg_map is not None:
            fvg_list = (
                getattr(fvg_map, "bearish_fvgs", [])
                if direction == "bearish"
                else getattr(fvg_map, "bullish_fvgs", [])
            ) or []

            for fvg in fvg_list:
                if getattr(fvg, "is_filled", False):
                    continue
                top    = float(getattr(fvg, "gap_top",    0.0))
                bottom = float(getattr(fvg, "gap_bottom", 0.0))
                if not self._valid_zone(top, bottom):
                    continue
                zones.append(_RawZone(
                    zone_top=top,
                    zone_bottom=bottom,
                    direction=direction,
                    factor_type="fvg",
                    strength=0.65,
                    description=f"FVG at {bottom:.2f}–{top:.2f}",
                    zone_id=str(getattr(fvg, "fvg_id", "")),
                    fvg_time=getattr(fvg, "formation_time", getattr(fvg, "candle_time", None)),
                ))

        # --- Supply / Demand ---
        sd_map = getattr(snapshot, "supply_demand", None)
        if sd_map is not None:
            sd_list = (
                getattr(sd_map, "supply_zones", [])
                if direction == "bearish"
                else getattr(sd_map, "demand_zones", [])
            ) or []

            for sdz in sd_list:
                if getattr(sdz, "status", "broken") == "broken":
                    continue
                top    = float(getattr(sdz, "zone_top",    0.0))
                bottom = float(getattr(sdz, "zone_bottom", 0.0))
                if not self._valid_zone(top, bottom):
                    continue
                label = "Supply" if direction == "bearish" else "Demand"
                zones.append(_RawZone(
                    zone_top=top,
                    zone_bottom=bottom,
                    direction=direction,
                    factor_type="supply_demand",
                    strength=float(getattr(sdz, "strength", 0.5)),
                    description=f"{label} zone {bottom:.2f}–{top:.2f}",
                    zone_id=str(getattr(sdz, "zone_id", "")),
                ))

        return zones

    # ------------------------------------------------------------------
    # Step 5: clustering
    # ------------------------------------------------------------------

    def _cluster(
        self, raw_zones: list[_RawZone]
    ) -> list[list[_RawZone]]:
        """Group overlapping / nearby raw zones into clusters.

        Sort by ``zone_bottom`` ascending, then merge zones whose
        ``zone_bottom`` falls within current cluster top + tolerance.

        Parameters
        ----------
        raw_zones:
            Flat list of raw zones to cluster.

        Returns
        -------
        list[list[_RawZone]]
            Each inner list is one cluster group.
        """
        sorted_zones = sorted(raw_zones, key=lambda z: z.zone_bottom)
        groups: list[list[_RawZone]] = []
        current: list[_RawZone] = []
        current_top: float = 0.0

        for zone in sorted_zones:
            if not current:
                current     = [zone]
                current_top = zone.zone_top
            elif zone.zone_bottom <= current_top + self._tolerance:
                current.append(zone)
                current_top = max(current_top, zone.zone_top)
            else:
                groups.append(current)
                current     = [zone]
                current_top = zone.zone_top

        if current:
            groups.append(current)

        return groups

    # ------------------------------------------------------------------
    # Build ZoneCluster
    # ------------------------------------------------------------------

    def _build_cluster(
        self,
        group: list[_RawZone],
        idx: int,
        symbol: str,
        timeframe: str,
        direction: Literal["bullish", "bearish"],
        pd_range: Optional[tuple[float, float]],
        candles: Any = None,
    ) -> Optional[ZoneCluster]:
        """Build a :class:`~src.models.zone_cluster.ZoneCluster` from a group.

        Parameters
        ----------
        group:
            Raw zones belonging to the same cluster.
        idx:
            Cluster index for ID generation.
        symbol, timeframe:
            Instrument identifiers.
        direction:
            Directional bias.
        pd_range:
            ``(range_high, range_low)`` or ``None``.

        Returns
        -------
        Optional[ZoneCluster]
            Built cluster, or ``None`` on degenerate boundaries.
        """
        zone_top    = max(z.zone_top    for z in group)
        zone_bottom = min(z.zone_bottom for z in group)

        has_ob = any(z.factor_type == "order_block" for z in group)
        has_fvg = any(z.factor_type == "fvg" for z in group)
        if not (has_ob or has_fvg):
            return None

        # Extract formation times and entry points from raw zones
        ob_zone  = next((z for z in group if z.factor_type == "order_block"), None)
        fvg_zone = next((z for z in group if z.factor_type == "fvg"), None)
        ob_formation_time  = ob_zone.ob_time  if ob_zone  else None
        fvg_formation_time = fvg_zone.fvg_time if fvg_zone else None
        entry_point_ob  = ob_zone.zone_bottom  if ob_zone  else None
        entry_point_fvg = fvg_zone.zone_bottom if fvg_zone else None
        if direction == "bearish":
            stop_loss_val = zone_top + (zone_top - zone_bottom) * 0.02
        else:
            stop_loss_val = zone_bottom - (zone_top - zone_bottom) * 0.02

        if not self._valid_zone(zone_top, zone_bottom):
            return None

        zone_size     = zone_top - zone_bottom
        zone_midpoint = (zone_top + zone_bottom) / 2.0

        # Step 6 — Entry zone (Fibonacci 38.2%)
        if direction == "bearish":
            ez_bottom = min(z.zone_bottom for z in group)
            ez_top    = ez_bottom + zone_size * _FIBO_382
        else:
            ez_top    = max(z.zone_top for z in group)
            ez_bottom = ez_top - zone_size * _FIBO_382

        if ez_top <= ez_bottom:
            ez_top    = zone_top
            ez_bottom = zone_bottom

        factors = [
            ClusterFactor(
                factor_type=z.factor_type,  # type: ignore[arg-type]
                direction=direction,
                zone_top=z.zone_top,
                zone_bottom=z.zone_bottom,
                strength=z.strength,
                description=z.description,
                is_broken_retested=z.is_broken_retested,
            )
            for z in group
        ]

        cluster_id = (
            f"CLUSTER_{direction.upper()}_{symbol}_{timeframe}_{idx:03d}"
        )

        types  = {z.factor_type for z in group}
        has_ob = "order_block"   in types
        has_fv = "fvg"            in types
        has_sd = "supply_demand" in types

        ob_times = [z.ob_time for z in group if z.factor_type == "order_block" and z.ob_time is not None]
        fvg_times = [z.fvg_time for z in group if z.factor_type == "fvg" and z.fvg_time is not None]
        ob_time = min(ob_times) if ob_times else None
        fvg_time = min(fvg_times) if fvg_times else None
        # entry_time = اولین کندلی که بعد از آخرین سیگنال به zone برمیگرده
        last_signal_time = max(ob_time, fvg_time) if ob_time and fvg_time else (ob_time or fvg_time)
        entry_time = self._find_entry_time(candles, zone_bottom, zone_top, direction, last_signal_time) if candles is not None and last_signal_time else None
        ob_factors = [z for z in group if z.factor_type == "order_block"]
        fvg_factors = [z for z in group if z.factor_type == "fvg"]
        if direction == "bearish":
            entry_ob  = min(z.zone_bottom for z in ob_factors)  if ob_factors  else None
            entry_fvg = min(z.zone_bottom for z in fvg_factors) if fvg_factors else None
            sl_buffer = max((zone_top - zone_bottom) * 0.1, 10 * self._pip_size)
            stop_loss = (max(z.zone_top for z in ob_factors) + sl_buffer) if ob_factors else None
        else:
            entry_ob  = min(z.zone_bottom for z in ob_factors)  if ob_factors  else None
            entry_fvg = min(z.zone_bottom for z in fvg_factors) if fvg_factors else None
            sl_buffer = max((zone_top - zone_bottom) * 0.1, 10 * self._pip_size)
            stop_loss = (min(z.zone_bottom for z in ob_factors) - sl_buffer) if ob_factors else None

        pd_zone = self._classify_pd(zone_midpoint, pd_range, direction)

        try:
            cluster = ZoneCluster(
                cluster_id=cluster_id,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                zone_top=zone_top,
                zone_bottom=zone_bottom,
                zone_midpoint=zone_midpoint,
                zone_size=zone_size,
                entry_zone_top=ez_top,
                entry_zone_bottom=ez_bottom,
                factors=factors,
                factor_count=len(factors),
                has_order_block=has_ob,
                has_fvg=has_fv,
                has_supply_demand=has_sd,
                premium_discount_zone=pd_zone,
                created_at=datetime.utcnow(),
                ob_formation_time=ob_time,
                fvg_formation_time=fvg_time,
                entry_time_suggestion=entry_time,
                entry_point_ob=entry_ob,
                entry_point_fvg=entry_fvg,
                stop_loss=stop_loss,
            )
        except ValueError as exc:
            self._log.warning(
                "Skipping degenerate cluster %s: %s", cluster_id, exc
            )
            return None

        # Initial score (sweep / BOS not yet attached)
        self._score_cluster(cluster, pd_range, direction)
        return cluster

    # ------------------------------------------------------------------
    # Step 3: liquidity sweep attachment
    # ------------------------------------------------------------------

    def _attach_sweep(
        self,
        snapshot: Any,
        clusters: list[ZoneCluster],
        direction: str,
    ) -> None:
        """Attach the most recent relevant liquidity sweep to the nearest cluster.

        Fix: for BEARISH bias, BSL_sweep AND SSL_sweep are both relevant
        context — a recent SSL_sweep near bearish zones indicates stop hunts
        that precede a continuation move down.

        Modifies *clusters* in-place.

        Parameters
        ----------
        snapshot:
            MarketSnapshot.
        clusters:
            Partially built cluster list.
        direction:
            Market bias.
        """
        liq = getattr(snapshot, "liquidity", None)
        if liq is None or not clusters:
            return

        # Try recent_sweep first, then fall back to last sweep in list
        recent_sweep = getattr(liq, "recent_sweep", None)
        if recent_sweep is None:
            sweeps = getattr(liq, "sweeps", []) or []
            recent_sweep = sweeps[-1] if sweeps else None

        if recent_sweep is None:
            return

        sweep_type = str(getattr(recent_sweep, "sweep_type", ""))

        # For bearish bias: both SSL_sweep (sell-side liquidity grab before
        # drop) and BSL_sweep (buy-side taken, then reversal down) are valid.
        # For bullish bias: both SSL_sweep and BSL_sweep can apply.
        # → Accept ANY sweep as context — direction filter removed.

        # Resolve sweep price level
        swept_level = getattr(recent_sweep, "swept_level", None)
        sweep_price: Optional[float] = None
        if swept_level is not None:
            p = getattr(swept_level, "price", 0.0)
            if p and p > 0:
                sweep_price = float(p)

        # Find nearest cluster by midpoint distance
        if sweep_price is not None:
            target = min(
                clusters,
                key=lambda c: abs(c.zone_midpoint - sweep_price),
            )
        else:
            target = clusters[0]

        # Only attach once
        if target.has_liquidity_sweep:
            return

        price_label = f"{sweep_price:.2f}" if sweep_price else "unknown"
        try:
            sweep_factor = ClusterFactor(
                factor_type="liquidity_sweep",
                direction=direction,  # type: ignore[arg-type]
                zone_top=target.zone_top,
                zone_bottom=target.zone_bottom,
                strength=0.80,
                description=f"{sweep_type} at {price_label}",
            )
            target.factors.append(sweep_factor)
            target.factor_count       = len(target.factors)
            target.has_liquidity_sweep = True
            self._log.debug(
                "Attached %s to cluster %s", sweep_type, target.cluster_id
            )
        except ValueError as exc:
            self._log.debug("Could not attach sweep factor: %s", exc)

    # ------------------------------------------------------------------
    # Step 4: BOS attachment
    # ------------------------------------------------------------------

    def _attach_bos(
        self,
        snapshot: Any,
        clusters: list[ZoneCluster],
        direction: str,
    ) -> None:
        """Mark clusters with BOS context by reading structure events directly.

        Reads ``market_structure.events`` (list of MarketStructureEvent)
        instead of a ``has_bos`` flag which may not exist on the model.

        Modifies *clusters* in-place.

        Parameters
        ----------
        snapshot:
            MarketSnapshot.
        clusters:
            Cluster list.
        direction:
            Market bias.
        """
        ms = getattr(snapshot, "market_structure", None)
        if ms is None or not clusters:
            return

        events = getattr(ms, "events", []) or []
        if not events:
            return

        recent = events[-_BOS_EVENT_LOOKBACK:]

        has_bos = any(
            str(getattr(ev, "direction", "")) == direction
            and str(getattr(ev, "event_type", "")) in ("BOS", "CHoCH")
            for ev in recent
        )

        if not has_bos:
            return

        for cluster in clusters:
            if cluster.has_bos:
                continue
            cluster.has_bos = True
            try:
                bos_factor = ClusterFactor(
                    factor_type="bos",
                    direction=direction,  # type: ignore[arg-type]
                    zone_top=cluster.zone_top,
                    zone_bottom=cluster.zone_bottom,
                    strength=0.75,
                    description=f"BOS {direction} confirmed",
                )
                cluster.factors.append(bos_factor)
                cluster.factor_count = len(cluster.factors)
            except ValueError as exc:
                self._log.debug(
                    "Could not attach BOS factor to %s: %s",
                    cluster.cluster_id, exc,
                )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_cluster(
        self,
        cluster: ZoneCluster,
        pd_range: Optional[tuple[float, float]],
        direction: str,
    ) -> None:
        """Compute and apply confluence score for *cluster* in-place.

        Parameters
        ----------
        cluster:
            ZoneCluster to score.
        pd_range:
            ``(range_high, range_low)`` or ``None``.
        direction:
            Market bias.
        """
        score = 0.0

        if cluster.has_order_block:
            score += _SCORE_OB
        if cluster.has_fvg:
            score += _SCORE_FVG
        if any(
            getattr(f, "is_broken_retested", False)
            for f in cluster.factors
            if f.factor_type == "order_block"
        ):
            score += 15.0
        if cluster.has_liquidity_sweep:
            score += _SCORE_SWEEP
        if cluster.has_bos:
            score += _SCORE_BOS
        if cluster.has_supply_demand:
            score += _SCORE_SD

        # Re-classify premium/discount with latest pd_range
        pd_zone = self._classify_pd(cluster.zone_midpoint, pd_range, direction)
        cluster.premium_discount_zone = pd_zone

        if (
            (direction == "bearish" and pd_zone == "premium")
            or (direction == "bullish" and pd_zone == "discount")
        ):
            score += _SCORE_PD

        score = min(score, 100.0)
        grade, label, color = self._assign_grade(score)

        cluster.confluence_score = score
        cluster.grade             = grade  # type: ignore[assignment]
        cluster.grade_label       = label
        cluster.grade_color       = color
        cluster.is_tradeable      = score >= _TRADEABLE_MIN

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_entry_time(self, candles: Any, zone_bottom: float, zone_top: float, direction: str, after_time: Any) -> Any:
        """اولین کندلی که بعد از تشکیل سیگنال به zone برمیگرده."""
        try:
            import pandas as pd
            if candles is None or not hasattr(candles, 'index'):
                return None
            after_ts = pd.Timestamp(after_time)
            if after_ts.tzinfo is None:
                after_ts = after_ts.tz_localize('UTC')
            df_after = candles[candles.index > after_ts]
            if df_after.empty:
                return None
            for ts, row in df_after.iterrows():
                low = float(row['low'])
                high = float(row['high'])
                if low <= zone_top and high >= zone_bottom:
                    return ts
            return None
        except Exception:
            return None

    def _classify_pd(
        self,
        midpoint: float,
        pd_range: Optional[tuple[float, float]],
        direction: str,
    ) -> Literal["premium", "discount", "equilibrium", "unknown"]:
        """Classify *midpoint* as premium, discount, equilibrium, or unknown.

        Parameters
        ----------
        midpoint:
            Price midpoint of the zone.
        pd_range:
            ``(range_high, range_low)`` from last 200 candles, or ``None``.
        direction:
            Market bias (context only — not used in calculation).

        Returns
        -------
        Literal["premium", "discount", "equilibrium", "unknown"]
        """
        if pd_range is None:
            return "unknown"

        range_high, range_low = pd_range
        price_range = range_high - range_low
        if price_range <= 0:
            return "unknown"

        equilibrium = (range_high + range_low) / 2.0
        band        = price_range * _PD_EQ_BAND

        if abs(midpoint - equilibrium) <= band:
            return "equilibrium"
        if midpoint > equilibrium:
            return "premium"
        return "discount"

    def _price_range(
        self,
        snapshot: Any,
        candles: Any,
    ) -> Optional[tuple[float, float]]:
        """Extract high/low range from candle data.

        Tries multiple sources in order:
        1. *candles* argument (explicit DataFrame passed by caller)
        2. ``snapshot.df``
        3. ``snapshot.candles``
        4. Swing points from ``snapshot.market_structure`` (fallback)

        Parameters
        ----------
        snapshot:
            MarketSnapshot.
        candles:
            Optional raw OHLCV DataFrame.

        Returns
        -------
        Optional[tuple[float, float]]
            ``(range_high, range_low)`` or ``None``.
        """
        # Try explicit candles argument
        for df_candidate in (
            candles,
            getattr(snapshot, "df", None),
            getattr(snapshot, "candles", None),
        ):
            if df_candidate is not None:
                try:
                    tail = df_candidate.iloc[-_RANGE_LOOKBACK:]
                    return (
                        float(tail["high"].max()),
                        float(tail["low"].min()),
                    )
                except Exception:
                    continue

        # Fallback: derive from swing points in market structure
        ms = getattr(snapshot, "market_structure", None)
        if ms is not None:
            highs = [
                float(sp.price)
                for sp in (getattr(ms, "swing_highs", []) or [])
            ]
            lows = [
                float(sp.price)
                for sp in (getattr(ms, "swing_lows", []) or [])
            ]
            if highs and lows:
                return max(highs), min(lows)

        # Last resort: use current price from snapshot
        cp = getattr(snapshot, "current_price", 0.0)
        if cp and cp > 0:
            # Estimate ±2% range around current price
            return cp * 1.02, cp * 0.98

        return None

    @staticmethod
    def _assign_grade(score: float) -> tuple[str, str, str]:
        """Map a numeric score to grade, label, and hex colour.

        Parameters
        ----------
        score:
            Confluence score in ``[0.0, 100.0]``.

        Returns
        -------
        tuple[str, str, str]
            ``(grade, label, color)``.
        """
        grade = "D"
        for threshold, g in _GRADE_THRESHOLDS:
            if score >= threshold:
                grade = g
                break
        return grade, _GRADE_LABELS[grade], _GRADE_COLORS[grade]

    @staticmethod
    def _valid_zone(top: float, bottom: float) -> bool:
        """Return ``True`` when zone boundaries are positive and non-degenerate.

        Parameters
        ----------
        top, bottom:
            Zone boundary prices.
        """
        return top > 0 and bottom > 0 and top > bottom

    @staticmethod
    def _empty_map(
        symbol: str,
        timeframe: str,
        bias: str,
    ) -> ClusterMap:
        """Return an empty :class:`~src.models.zone_cluster.ClusterMap`.

        Parameters
        ----------
        symbol, timeframe:
            Instrument identifiers.
        bias:
            Market bias (may be ``"neutral"``).
        """
        safe_bias: Literal["bullish", "bearish", "neutral"] = (
            bias if bias in ("bullish", "bearish", "neutral") else "neutral"
        )
        return ClusterMap(
            symbol=symbol,
            timeframe=timeframe,
            market_bias=safe_bias,
            scanned_at=datetime.utcnow(),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_cluster_engine(
    pip_size: float = 0.01,
    cluster_tolerance_pips: float = 20.0,
    min_factors: int = 1,
) -> ZoneClusterEngine:
    """Factory — return a configured :class:`ZoneClusterEngine`.

    Parameters
    ----------
    pip_size:
        One pip in price units.  Default ``0.01`` (XAUUSD).
    cluster_tolerance_pips:
        Merge gap in pips.  Default ``20.0``.
    min_factors:
        Minimum factors per cluster.  Default ``1``.

    Returns
    -------
    ZoneClusterEngine
        Ready-to-use engine instance.
    """
    return ZoneClusterEngine(
        pip_size=pip_size,
        cluster_tolerance_pips=cluster_tolerance_pips,
        min_factors=min_factors,
    )