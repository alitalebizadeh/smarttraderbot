"""
src/output/signals_exporter.py — SmartTraderBot
Exports analysis results to signals.json for MT5 MQL5 Indicator consumption.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import get_logger

__all__ = ["SignalsExporter", "export_signals"]

logger = get_logger(__name__)


class SignalsExporter:
    """Exports SMC analysis results to a JSON file readable by MT5 indicator."""

    def __init__(self, output_dir: str = "output_files") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._output_dir / "signals.json"

    def export(self, scan_result: Any) -> str:
        """Export ScanResult to signals.json.

        Args:
            scan_result: ScanResult from MarketScanner.run()

        Returns:
            Path to the saved JSON file, or "" on error.
        """
        try:
            payload = self._build_payload(scan_result)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info("signals.json saved: %s", self._filepath)
            return str(self._filepath)
        except Exception as exc:
            logger.error("Failed to export signals.json: %s", exc)
            return ""

    def _build_payload(self, scan_result: Any) -> dict:
        """Build the full JSON payload from scan result."""
        tf_results = getattr(scan_result, "timeframe_results", []) or []

        symbols_data = []
        for tf_result in tf_results:
            try:
                symbol    = str(getattr(tf_result, "symbol", ""))
                timeframe = str(getattr(tf_result, "timeframe", ""))
                snapshot  = getattr(tf_result, "snapshot", None)
                scoring   = getattr(tf_result, "scoring_output", None)

                entry = {
                    "symbol":    symbol,
                    "timeframe": timeframe,
                    "generated_at": datetime.utcnow().isoformat(),
                    "market_structure": self._extract_market_structure(snapshot),
                    "order_blocks":     self._extract_order_blocks(snapshot),
                    "fvgs":             self._extract_fvgs(snapshot),
                    "supply_zones":     self._extract_supply_zones(snapshot),
                    "demand_zones":     self._extract_demand_zones(snapshot),
                    "liquidity":        self._extract_liquidity(snapshot),
                    "pois":             self._extract_pois(scoring),
                    "top_setups":       self._extract_top_setups(scoring),
                    "entry_points":     self._extract_entries(tf_result),
                }
                symbols_data.append(entry)
            except Exception as exc:
                logger.warning("Error building payload for %s: %s", tf_result, exc)

        return {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "symbols": symbols_data,
        }

    def _extract_market_structure(self, snapshot: Any) -> dict:
        try:
            ms = getattr(snapshot, "market_structure", None)
            if ms is None:
                return {"bias": "neutral", "events": []}

            events = []
            for ev in (getattr(ms, "events", []) or [])[-10:]:
                events.append({
                    "type":      str(getattr(ev, "event_type", "")),
                    "direction": str(getattr(ev, "direction", "")),
                    "price":     float(getattr(ev, "break_price", 0)),
                    "time":      str(getattr(ev, "break_candle_time", "")),
                })

            return {
                "bias":   str(getattr(ms, "current_bias", "neutral")),
                "events": events,
            }
        except Exception:
            return {"bias": "neutral", "events": []}

    def _extract_order_blocks(self, snapshot: Any) -> list:
        try:
            ob_map = getattr(snapshot, "order_blocks", None)
            if ob_map is None:
                return []

            result = []
            for ob in (getattr(ob_map, "bullish_obs", []) or []):
                result.append(self._ob_to_dict(ob, "bullish"))
            for ob in (getattr(ob_map, "bearish_obs", []) or []):
                result.append(self._ob_to_dict(ob, "bearish"))
            return result
        except Exception:
            return []

    def _ob_to_dict(self, ob: Any, direction: str) -> dict:
        return {
            "id":          str(getattr(ob, "ob_id", "")),
            "direction":   direction,
            "zone_top":    float(getattr(ob, "zone_top", 0)),
            "zone_bottom": float(getattr(ob, "zone_bottom", 0)),
            "midpoint":    float(getattr(ob, "zone_midpoint", 0)),
            "strength":    float(getattr(ob, "strength", 0)),
            "mitigated":   bool(getattr(ob, "is_mitigated", False)),
            "time":        str(getattr(ob, "candle_time", "")),
        }

    def _extract_fvgs(self, snapshot: Any) -> list:
        try:
            fvg_map = getattr(snapshot, "fvgs", None)
            if fvg_map is None:
                return []

            result = []
            for fvg in (getattr(fvg_map, "bullish_fvgs", []) or []):
                result.append(self._fvg_to_dict(fvg, "bullish"))
            for fvg in (getattr(fvg_map, "bearish_fvgs", []) or []):
                result.append(self._fvg_to_dict(fvg, "bearish"))
            return result
        except Exception:
            return []

    def _fvg_to_dict(self, fvg: Any, direction: str) -> dict:
        return {
            "id":           str(getattr(fvg, "fvg_id", "")),
            "direction":    direction,
            "gap_top":      float(getattr(fvg, "gap_top", 0)),
            "gap_bottom":   float(getattr(fvg, "gap_bottom", 0)),
            "equilibrium":  float(getattr(fvg, "equilibrium", 0)),
            "fill_status":  str(getattr(fvg, "fill_status", "unfilled")),
            "fill_pct":     float(getattr(fvg, "fill_percentage", 0)),
            "time":         str(getattr(fvg, "candle_time", "")),
        }

    def _extract_supply_zones(self, snapshot: Any) -> list:
        try:
            sd = getattr(snapshot, "supply_demand", None)
            if sd is None:
                return []
            result = []
            for z in (getattr(sd, "supply_zones", []) or []):
                result.append({
                    "id":          str(getattr(z, "zone_id", "")),
                    "zone_top":    float(getattr(z, "zone_top", 0)),
                    "zone_bottom": float(getattr(z, "zone_bottom", 0)),
                    "proximal":    float(getattr(z, "proximal_line", 0)),
                    "strength":    float(getattr(z, "strength", 0)),
                    "status":      str(getattr(z, "status", "active")),
                    "time":        str(getattr(z, "base_start_time", "")),
                })
            return result
        except Exception:
            return []

    def _extract_demand_zones(self, snapshot: Any) -> list:
        try:
            sd = getattr(snapshot, "supply_demand", None)
            if sd is None:
                return []
            result = []
            for z in (getattr(sd, "demand_zones", []) or []):
                result.append({
                    "id":          str(getattr(z, "zone_id", "")),
                    "zone_top":    float(getattr(z, "zone_top", 0)),
                    "zone_bottom": float(getattr(z, "zone_bottom", 0)),
                    "proximal":    float(getattr(z, "proximal_line", 0)),
                    "strength":    float(getattr(z, "strength", 0)),
                    "status":      str(getattr(z, "status", "active")),
                    "time":        str(getattr(z, "base_start_time", "")),
                })
            return result
        except Exception:
            return []

    def _extract_liquidity(self, snapshot: Any) -> dict:
        try:
            liq = getattr(snapshot, "liquidity", None)
            if liq is None:
                return {"bsl": [], "ssl": [], "sweeps": []}

            sweeps = []
            for sw in (getattr(liq, "sweeps", []) or [])[-10:]:
                sweeps.append({
                    "type":           str(getattr(sw, "sweep_type", "")),
                    "price":          float(getattr(sw, "swept_level", None) and
                                      getattr(getattr(sw, "swept_level", None), "price", 0) or 0),
                    "returned_inside": bool(getattr(sw, "returned_inside", False)),
                    "time":           str(getattr(sw, "sweep_candle_time", "")),
                })

            return {
                "bsl_count": len(getattr(liq, "bsl_levels", []) or []),
                "ssl_count": len(getattr(liq, "ssl_levels", []) or []),
                "sweeps":    sweeps,
            }
        except Exception:
            return {"bsl": [], "ssl": [], "sweeps": []}

    def _extract_pois(self, scoring: Any) -> list:
        try:
            if scoring is None:
                return []
            result = []
            for r in (getattr(scoring, "all_results", []) or []):
                result.append({
                    "id":          str(getattr(r, "poi_id", "")),
                    "direction":   str(getattr(r, "direction", "")),
                    "zone_top":    float(getattr(r, "zone_top", 0)),
                    "zone_bottom": float(getattr(r, "zone_bottom", 0)),
                    "score":       float(getattr(r, "total_score", 0)),
                    "grade":       str(getattr(r, "grade", "D")),
                    "label":       str(getattr(r, "grade_label", "")),
                    "color":       str(getattr(r, "grade_color", "#6c757d")),
                    "tradeable":   bool(getattr(r, "is_tradeable", False)),
                    "pd_zone":     str(getattr(r, "premium_discount_zone", "unknown")),
                    "has_ob":      bool(getattr(r, "has_order_block", False)),
                    "has_fvg":     bool(getattr(r, "has_fvg", False)),
                    "has_sweep":   bool(getattr(r, "has_liquidity_sweep", False)),
                    "has_bos":     bool(getattr(r, "has_bos", False)),
                })
            return result
        except Exception:
            return []

    def _extract_top_setups(self, scoring: Any) -> list:
        try:
            if scoring is None:
                return []
            result = []
            for r in (getattr(scoring, "dashboard_results", []) or [])[:5]:
                result.append({
                    "direction":   str(getattr(r, "direction", "")),
                    "zone_top":    float(getattr(r, "zone_top", 0)),
                    "zone_bottom": float(getattr(r, "zone_bottom", 0)),
                    "score":       float(getattr(r, "total_score", 0)),
                    "grade":       str(getattr(r, "grade", "D")),
                    "label":       str(getattr(r, "grade_label", "")),
                    "color":       str(getattr(r, "grade_color", "#6c757d")),
                    "summary":     str(getattr(r, "summary", "")),
                })
            return result
        except Exception:
            return []


    def _extract_entries(self, tf_result: Any) -> list:
        try:
            entry_map = getattr(tf_result, "entry_map", None)
            if entry_map is None:
                scoring = getattr(tf_result, "scoring_output", None)
                entry_map = getattr(scoring, "entry_map", None)
            if entry_map is None:
                return []
            result = []
            for e in getattr(entry_map, "entries", []) or []:
                result.append(e.to_dict() if hasattr(e, "to_dict") else {})
            return [r for r in result if r]
        except Exception:
            return []


def export_signals(scan_result: Any, output_dir: str = "output_files") -> str:
    """Convenience function to export signals.json.

    Args:
        scan_result: ScanResult from MarketScanner.run()
        output_dir: Directory to write signals.json

    Returns:
        Path to saved file or "" on error.
    """
    return SignalsExporter(output_dir=output_dir).export(scan_result)
