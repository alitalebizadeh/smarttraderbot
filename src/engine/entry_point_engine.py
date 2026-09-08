"""Best-entry recommendations after SMC analysis (with-trend only)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from src.utils.logger import get_logger

__all__ = [
    "EntryPoint",
    "EntryMap",
    "EntryPointEngine",
    "create_entry_engine",
    "export_entry_points",
]

logger = get_logger(__name__)

_RR_TP1: float = 2.0
_RR_TP2: float = 3.0
_SL_BUFFER_PCT: float = 0.00015
_MAX_ENTRIES: int = 5
_MIN_SCORE: float = 50.0


@dataclass
class EntryPoint:
    """A ranked, with-trend trade entry derived from a scored zone or cluster."""

    entry_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    source_id: str
    source_type: str
    entry_price: float
    entry_zone_top: float
    entry_zone_bottom: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_1: float
    risk_reward_2: float
    score: float
    grade: str
    current_price: float
    distance: float
    status: Literal["in_zone", "awaiting_pullback", "invalidated"]
    reason: str
    rank: int = 1
    ob_formation_time: str = ""
    fvg_formation_time: str = ""
    entry_time_suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "entry_price": round(self.entry_price, 5),
            "entry_zone_top": round(self.entry_zone_top, 5),
            "entry_zone_bottom": round(self.entry_zone_bottom, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit_1": round(self.take_profit_1, 5),
            "take_profit_2": round(self.take_profit_2, 5),
            "risk_reward_1": round(self.risk_reward_1, 2),
            "risk_reward_2": round(self.risk_reward_2, 2),
            "score": round(self.score, 2),
            "grade": self.grade,
            "current_price": round(self.current_price, 5),
            "distance": round(self.distance, 5),
            "status": self.status,
            "reason": self.reason,
            "rank": self.rank,
            "ob_formation_time": self.ob_formation_time,
            "fvg_formation_time": self.fvg_formation_time,
            "entry_time_suggestion": self.entry_time_suggestion,
        }


@dataclass
class EntryMap:
    """Ranked entry points for one symbol / timeframe after a full scan."""

    symbol: str
    timeframe: str
    market_bias: str
    current_price: float
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    entries: list[EntryPoint] = field(default_factory=list)
    best_entry: Optional[EntryPoint] = field(default=None)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market_bias": self.market_bias,
            "current_price": round(self.current_price, 5),
            "generated_at": self.generated_at.isoformat(),
            "entries": [e.to_dict() for e in self.entries],
            "best_entry": (
                self.best_entry.to_dict() if self.best_entry is not None else None
            ),
        }


class EntryPointEngine:
    """Builds ranked entry levels from with-trend clusters and scored POIs."""

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._max_entries = max(1, int(max_entries))
        self._log = logging.getLogger(__name__)

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        market_structure: Optional[Any] = None,
        cluster_map: Optional[Any] = None,
        scoring_output: Optional[Any] = None,
    ) -> EntryMap:
        """Return ranked entry points aligned with market bias.

        Never raises — returns an empty map on failure.
        """
        try:
            return self._run(
                symbol,
                timeframe,
                float(current_price or 0.0),
                market_structure,
                cluster_map,
                scoring_output,
            )
        except Exception as exc:
            self._log.warning(
                "[%s/%s] EntryPointEngine failed: %s", symbol, timeframe, exc
            )
            bias = "neutral"
            if market_structure is not None:
                bias = str(getattr(market_structure, "current_bias", "neutral"))
            return EntryMap(
                symbol=symbol,
                timeframe=timeframe,
                market_bias=bias,
                current_price=float(current_price or 0.0),
            )

    def _run(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        market_structure: Optional[Any],
        cluster_map: Optional[Any],
        scoring_output: Optional[Any],
    ) -> EntryMap:
        bias = "neutral"
        if market_structure is not None:
            bias = str(getattr(market_structure, "current_bias", "neutral"))

        empty = EntryMap(
            symbol=symbol,
            timeframe=timeframe,
            market_bias=bias,
            current_price=current_price,
        )

        if bias not in ("bullish", "bearish") or current_price <= 0:
            self._log.info(
                "[%s/%s] No directional bias (bias=%s) — no entry points.",
                symbol, timeframe, bias,
            )
            return empty

        candidates: list[EntryPoint] = []
        seen_keys: set[tuple[float, float, str]] = set()

        clusters = getattr(cluster_map, "clusters", None) or []
        for cluster in clusters:
            if str(getattr(cluster, "direction", "")) != bias:
                continue
            if bool(getattr(cluster, "invalidated", False)):
                continue
            entry = self._from_cluster(cluster, current_price, bias)
            if entry is None:
                continue
            key = (round(entry.entry_zone_bottom, 2), round(entry.entry_zone_top, 2), bias)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(entry)

        results = getattr(scoring_output, "all_results", None) or []
        for result in results:
            if str(getattr(result, "direction", "")) != bias:
                continue
            if float(getattr(result, "total_score", 0.0)) < _MIN_SCORE:
                continue
            entry = self._from_score_result(result, current_price, bias)
            if entry is None:
                continue
            key = (round(entry.entry_zone_bottom, 2), round(entry.entry_zone_top, 2), bias)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(entry)

        live = [e for e in candidates if e.status != "invalidated"]
        live.sort(
            key=lambda e: (
                0 if e.status == "in_zone" else 1,
                -e.score,
                e.distance,
            )
        )

        ranked: list[EntryPoint] = []
        for idx, entry in enumerate(live[: self._max_entries], start=1):
            entry.rank = idx
            ranked.append(entry)

        best = ranked[0] if ranked else None
        self._log.info(
            "[%s/%s] Entry points: %d (bias=%s, best_score=%.1f)",
            symbol, timeframe, len(ranked), bias,
            best.score if best else 0.0,
        )
        return EntryMap(
            symbol=symbol,
            timeframe=timeframe,
            market_bias=bias,
            current_price=current_price,
            generated_at=datetime.now(tz=timezone.utc),
            entries=ranked,
            best_entry=best,
        )

    def _from_cluster(
        self, cluster: Any, current_price: float, bias: str
    ) -> Optional[EntryPoint]:
        zone_top = float(getattr(cluster, "zone_top", 0.0))
        zone_bot = float(getattr(cluster, "zone_bottom", 0.0))
        ez_top = float(getattr(cluster, "entry_zone_top", 0.0) or zone_top)
        ez_bot = float(getattr(cluster, "entry_zone_bottom", 0.0) or zone_bot)
        if ez_top <= ez_bot or zone_top <= zone_bot:
            return None

        score = float(getattr(cluster, "confluence_score", 0.0))
        grade = str(getattr(cluster, "grade", "D"))
        source_id = str(getattr(cluster, "cluster_id", "cluster"))

        # Extract formation times
        ob_time = getattr(cluster, "ob_formation_time", None)
        fvg_time = getattr(cluster, "fvg_formation_time", None)
        entry_time = getattr(cluster, "entry_time_suggestion", None)

        def _fmt(dt):
            if dt is None:
                return ""
            if hasattr(dt, "strftime"):
                return dt.strftime("%Y-%m-%d %H:%M")
            return str(dt)

        entry = self._build_entry(
            symbol=str(getattr(cluster, "symbol", "")),
            timeframe=str(getattr(cluster, "timeframe", "")),
            direction=bias,  # type: ignore[arg-type]
            source_id=source_id,
            source_type="cluster",
            zone_top=zone_top,
            zone_bottom=zone_bot,
            entry_zone_top=ez_top,
            entry_zone_bottom=ez_bot,
            score=score,
            grade=grade,
            current_price=current_price,
        )
        if entry is not None:
            entry.ob_formation_time = _fmt(ob_time)
            entry.fvg_formation_time = _fmt(fvg_time)
            entry.entry_time_suggestion = _fmt(entry_time)
        return entry

    def _from_score_result(
        self, result: Any, current_price: float, bias: str
    ) -> Optional[EntryPoint]:
        zone_top = float(getattr(result, "zone_top", 0.0))
        zone_bot = float(getattr(result, "zone_bottom", 0.0))
        if zone_top <= zone_bot:
            return None

        width = zone_top - zone_bot
        if bias == "bullish":
            ez_top, ez_bot = zone_top, zone_top - (width * 0.382)
        else:
            ez_bot, ez_top = zone_bot, zone_bot + (width * 0.382)
        if ez_top <= ez_bot:
            ez_top, ez_bot = zone_top, zone_bot

        return self._build_entry(
            symbol=str(getattr(result, "symbol", "")),
            timeframe=str(getattr(result, "timeframe", "")),
            direction=bias,  # type: ignore[arg-type]
            source_id=str(getattr(result, "poi_id", "poi")),
            source_type="poi",
            zone_top=zone_top,
            zone_bottom=zone_bot,
            entry_zone_top=ez_top,
            entry_zone_bottom=ez_bot,
            score=float(getattr(result, "total_score", 0.0)),
            grade=str(getattr(result, "grade", "D")),
            current_price=current_price,
        )

    def _build_entry(
        self,
        symbol: str,
        timeframe: str,
        direction: Literal["bullish", "bearish"],
        source_id: str,
        source_type: str,
        zone_top: float,
        zone_bottom: float,
        entry_zone_top: float,
        entry_zone_bottom: float,
        score: float,
        grade: str,
        current_price: float,
    ) -> Optional[EntryPoint]:
        if direction == "bullish":
            entry_price = entry_zone_top
            sl_buffer = max(zone_bottom * _SL_BUFFER_PCT, 0.01)
            stop_loss = zone_bottom - sl_buffer
            risk = entry_price - stop_loss
            if risk <= 0:
                return None
            take_profit_1 = entry_price + risk * _RR_TP1
            take_profit_2 = entry_price + risk * _RR_TP2
            if current_price < zone_bottom:
                status: Literal["in_zone", "awaiting_pullback", "invalidated"] = "invalidated"
                reason = "Price traded through the demand zone — setup is consumed."
            elif zone_bottom <= current_price <= zone_top:
                status = "in_zone"
                reason = "Price is inside the demand zone — limit/market long is available."
            else:
                status = "awaiting_pullback"
                reason = "Wait for a pullback into the demand entry zone before longing."
        else:
            entry_price = entry_zone_bottom
            sl_buffer = max(zone_top * _SL_BUFFER_PCT, 0.01)
            stop_loss = zone_top + sl_buffer
            risk = stop_loss - entry_price
            if risk <= 0:
                return None
            take_profit_1 = entry_price - risk * _RR_TP1
            take_profit_2 = entry_price - risk * _RR_TP2
            if current_price > zone_top:
                status = "invalidated"
                reason = "Price traded through the supply zone — setup is consumed."
            elif zone_bottom <= current_price <= zone_top:
                status = "in_zone"
                reason = "Price is inside the supply zone — limit/market short is available."
            else:
                status = "awaiting_pullback"
                reason = "Wait for a rally into the supply entry zone before shorting."

        distance = abs(current_price - entry_price)
        entry_id = f"ENTRY_{direction.upper()}_{symbol}_{timeframe}_{source_id}"

        return EntryPoint(
            entry_id=entry_id,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            source_id=source_id,
            source_type=source_type,
            entry_price=entry_price,
            entry_zone_top=entry_zone_top,
            entry_zone_bottom=entry_zone_bottom,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            risk_reward_1=_RR_TP1,
            risk_reward_2=_RR_TP2,
            score=score,
            grade=grade,
            current_price=current_price,
            distance=distance,
            status=status,
            reason=reason,
        )


def create_entry_engine(max_entries: int = _MAX_ENTRIES) -> EntryPointEngine:
    """Factory — return a configured EntryPointEngine."""
    return EntryPointEngine(max_entries=max_entries)


def export_entry_points(scan_result: Any, output_dir: str = "output_files") -> str:
    """Write entry_points.json from a completed ScanResult."""
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "entry_points.json"

        symbols_data: list[dict] = []
        for tf_result in getattr(scan_result, "timeframe_results", []) or []:
            entry_map = getattr(tf_result, "entry_map", None)
            if entry_map is None:
                snapshot = getattr(tf_result, "snapshot", None)
                scoring = getattr(tf_result, "scoring_output", None)
                entry_map = getattr(snapshot, "entry_map", None) or getattr(
                    scoring, "entry_map", None
                )
            if entry_map is None:
                continue
            if hasattr(entry_map, "to_dict"):
                symbols_data.append(entry_map.to_dict())

        payload = {
            "version": "1.0",
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "symbols": symbols_data,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("entry_points.json saved: %s", path)
        return str(path)
    except Exception as exc:
        logger.error("Failed to export entry_points.json: %s", exc)
        return ""
