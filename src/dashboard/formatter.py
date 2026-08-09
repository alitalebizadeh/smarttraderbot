from __future__ import annotations

import logging
from typing import Any, Optional

from src.utils.logger import get_logger
from src.utils.price_utils import get_pip_size, price_to_pips
from src.utils.time_utils import format_datetime, format_duration_ms

__all__ = [
    # Price
    "format_price",
    "format_price_range",
    "format_zone_size",
    # Score
    "format_score",
    "format_score_bar",
    "format_grade_badge",
    # Direction
    "format_direction",
    "format_pd_zone",
    # Factor
    "format_factor_checkmarks",
    "format_factor_scores",
    # Summary
    "format_scan_header",
    "format_scan_stats",
    "format_result_row",
]

_logger = get_logger(__name__)

# ─────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────

_SCORE_FILLED: str = "█"
_SCORE_EMPTY: str  = "░"

_PD_LABELS: dict[str, str] = {
    "premium":     "🔴 Premium",
    "discount":    "🟢 Discount",
    "equilibrium": "⚪ Equilibrium",
    "unknown":     "— Unknown",
}

_FACTOR_MAX: dict[str, int] = {
    "order_block_score":        20,
    "fvg_score":                20,
    "liquidity_sweep_score":    25,
    "bos_score":                15,
    "premium_discount_score":   10,
    "htf_alignment_score":      10,
}

_FACTOR_LABELS: dict[str, str] = {
    "order_block_score":      "Order Block",
    "fvg_score":              "FVG",
    "liquidity_sweep_score":  "Liquidity Sweep",
    "bos_score":              "BOS",
    "premium_discount_score": "Premium/Discount",
    "htf_alignment_score":    "HTF Alignment",
}

_CHECK_ATTRS: list[tuple[str, str]] = [
    ("has_order_block",    "OB"),
    ("has_fvg",            "FVG"),
    ("has_liquidity_sweep","LIQ"),
    ("has_bos",            "BOS"),
    ("premium_discount_score", "PD"),   # checked via score > 0
    ("htf_aligned",        "HTF"),
]


def _auto_decimals(symbol: str) -> int:
    """Return the appropriate decimal places for a given symbol.

    Args:
        symbol: Trading instrument symbol.

    Returns:
        Number of decimal places to display.
    """
    upper = symbol.upper()
    if "JPY" in upper:
        return 3
    if "XAU" in upper:
        return 2
    if "US30" in upper or "NAS" in upper:
        return 0
    return 5


# ─────────────────────────────────────────────
#  1. Price Formatting
# ─────────────────────────────────────────────

def format_price(
    price: float,
    symbol: str,
    decimals: Optional[int] = None,
) -> str:
    """Format a price to the appropriate number of decimal places for the symbol.

    When decimals is None, the count is inferred from the symbol:
    JPY pairs → 3, XAU (Gold) → 2, US30/NAS → 0, all others → 5.

    Args:
        price: Raw price value.
        symbol: Trading instrument symbol used to determine decimal places.
        decimals: Override the auto-detected decimal count. Uses auto when None.

    Returns:
        Formatted price string (e.g. "2025.12"). Returns "" on any error.
        Never raises.
    """
    try:
        d = decimals if decimals is not None else _auto_decimals(symbol)
        return f"{float(price):.{d}f}"
    except Exception:
        return ""


def format_price_range(zone_top: float, zone_bottom: float, symbol: str) -> str:
    """Format a price zone as "bottom — top" with symbol-appropriate decimals.

    Args:
        zone_top: Upper boundary of the zone.
        zone_bottom: Lower boundary of the zone.
        symbol: Trading instrument symbol for decimal detection.

    Returns:
        Formatted string e.g. "2017.50 — 2025.00". Returns "" on any error.
        Never raises.
    """
    try:
        bot = format_price(zone_bottom, symbol)
        top = format_price(zone_top, symbol)
        if not bot or not top:
            return ""
        return f"{bot} — {top}"
    except Exception:
        return ""


def format_zone_size(zone_size: float, symbol: str) -> str:
    """Format the zone height as a pip count string.

    Args:
        zone_size: Raw zone height in price terms.
        symbol: Trading instrument symbol for pip conversion.

    Returns:
        Formatted string e.g. "75.0 pips". Returns "" on any error.
        Never raises.
    """
    try:
        pips = price_to_pips(float(zone_size), symbol)
        return f"{pips:.1f} pips"
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  2. Score Formatting
# ─────────────────────────────────────────────

def format_score(score: float) -> str:
    """Format a confluence score as an integer string.

    Args:
        score: Confluence score between 0.0 and 100.0.

    Returns:
        Integer string e.g. "75". Returns "0" on any error. Never raises.
    """
    try:
        return str(int(round(float(score))))
    except Exception:
        return "0"


def format_score_bar(score: float, width: int = 10) -> str:
    """Render an ASCII progress bar proportional to the score.

    Example: score=75, width=10 → "███████░░░"

    Args:
        score: Confluence score between 0.0 and 100.0.
        width: Total character width of the bar. Defaults to 10.

    Returns:
        ASCII bar string of exactly `width` characters.
        Returns "" on any error. Never raises.
    """
    try:
        s = max(0.0, min(100.0, float(score)))
        w = max(1, int(width))
        filled = round(s / 100.0 * w)
        return _SCORE_FILLED * filled + _SCORE_EMPTY * (w - filled)
    except Exception:
        return ""


def format_grade_badge(grade: str, color: str) -> str:
    """Render an HTML badge span for a score grade.

    Args:
        grade: Grade letter string (e.g. "A+", "B").
        color: CSS hex color code for the badge background (e.g. "#28a745").

    Returns:
        HTML span element string with inline styles.
        Returns grade as plain text on any error. Never raises.
    """
    try:
        return (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-weight:bold">{grade}</span>'
        )
    except Exception:
        try:
            return str(grade)
        except Exception:
            return ""


# ─────────────────────────────────────────────
#  3. Direction Formatting
# ─────────────────────────────────────────────

def format_direction(direction: str, emoji: str) -> str:
    """Format a direction string with its emoji prefix.

    Args:
        direction: "bullish" or "bearish".
        emoji: Direction emoji (e.g. "🟢" or "🔴").

    Returns:
        Formatted string e.g. "🟢 BULLISH". Returns direction.upper() on error.
        Never raises.
    """
    try:
        return f"{emoji} {direction.upper()}"
    except Exception:
        try:
            return str(direction).upper()
        except Exception:
            return ""


def format_pd_zone(pd_zone: str) -> str:
    """Convert a premium_discount_zone value to a display-friendly label.

    Mapping:
        "premium"     → "🔴 Premium"
        "discount"    → "🟢 Discount"
        "equilibrium" → "⚪ Equilibrium"
        "unknown"     → "— Unknown"

    Args:
        pd_zone: Raw premium/discount zone identifier string.

    Returns:
        Human-readable label string. Returns pd_zone on any error. Never raises.
    """
    try:
        return _PD_LABELS.get(str(pd_zone).lower(), pd_zone)
    except Exception:
        try:
            return str(pd_zone)
        except Exception:
            return ""


# ─────────────────────────────────────────────
#  4. Factor Formatting
# ─────────────────────────────────────────────

def format_factor_checkmarks(result: Any) -> str:
    """Render a checkmark/cross summary for each confluence factor.

    Reads has_order_block, has_fvg, has_liquidity_sweep, has_bos,
    premium_discount_score (> 0 counts as present), and htf_aligned
    from the result object.

    Args:
        result: ScoreResult or any object with the expected boolean attributes.

    Returns:
        Formatted string e.g. "OB:✅ FVG:✅ LIQ:❌ BOS:❌ PD:✅ HTF:❌".
        Returns "" on any error. Never raises.
    """
    try:
        parts: list[str] = []

        def _check(attr: str) -> bool:
            """Return boolean flag from attr, handling the PD score special case."""
            if attr == "premium_discount_score":
                return getattr(result, "premium_discount_score", 0.0) > 0.0
            return bool(getattr(result, attr, False))

        for attr, label in _CHECK_ATTRS:
            mark = "✅" if _check(attr) else "❌"
            parts.append(f"{label}:{mark}")

        return " ".join(parts)
    except Exception:
        return ""


def format_factor_scores(result: Any) -> str:
    """Render a multi-line breakdown of each factor's score contribution.

    Args:
        result: ScoreResult or any object with individual score attributes.

    Returns:
        Multi-line string with one "Factor:  score/max" line per factor.
        Returns "" on any error. Never raises.
    """
    try:
        lines: list[str] = []
        for attr, max_pts in _FACTOR_MAX.items():
            label = _FACTOR_LABELS.get(attr, attr)
            score_val = getattr(result, attr, 0.0)
            # Left-pad label to 18 chars for alignment
            padded = f"{label}:".ljust(18)
            lines.append(f"{padded}{int(score_val)}/{max_pts}")
        return "\n".join(lines)
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  5. Summary Formatting
# ─────────────────────────────────────────────

def format_scan_header(summary: Any) -> str:
    """Format the dashboard header line for a scan summary.

    Format:
    "📊 XAUUSD M1 | Price: 2023.50 | Scanned: 09:05:32 | Duration: 142ms"

    Args:
        summary: ScanSummary or any object with symbol, timeframe,
            current_price, scanned_at, and scan_duration_ms attributes.

    Returns:
        Formatted header string. Returns "" on any error. Never raises.
    """
    try:
        symbol: str = str(getattr(summary, "symbol", ""))
        timeframe: str = str(getattr(summary, "timeframe", ""))
        price: float = float(getattr(summary, "current_price", 0.0))
        scanned_at = getattr(summary, "scanned_at", None)
        duration_ms: float = float(getattr(summary, "scan_duration_ms", 0.0))

        price_str = format_price(price, symbol)
        time_str = (
            format_datetime(scanned_at, "%H:%M:%S")
            if scanned_at is not None
            else "--:--:--"
        )
        dur_str = format_duration_ms(duration_ms)

        return (
            f"📊 {symbol} {timeframe} | "
            f"Price: {price_str} | "
            f"Scanned: {time_str} | "
            f"Duration: {dur_str}"
        )
    except Exception:
        return ""


def format_scan_stats(summary: Any) -> str:
    """Format a compact statistics line for a scan summary.

    Format:
    "Found: 5 POIs | A+:1 A:2 B:1 C:1 D:0 | Bullish:3 Bearish:2 | Avg Score: 58"

    Args:
        summary: ScanSummary or any object with the expected count attributes.

    Returns:
        Formatted stats string. Returns "" on any error. Never raises.
    """
    try:
        total: int = int(getattr(summary, "total_pois_found", 0))
        aplus: int = int(getattr(summary, "aplus_count", 0))
        a: int = int(getattr(summary, "a_count", 0))
        b: int = int(getattr(summary, "b_count", 0))
        c: int = int(getattr(summary, "c_count", 0))
        d: int = int(getattr(summary, "d_count", 0))
        bull: int = int(getattr(summary, "bullish_count", 0))
        bear: int = int(getattr(summary, "bearish_count", 0))
        avg: float = float(getattr(summary, "avg_score", 0.0))

        return (
            f"Found: {total} POIs | "
            f"A+:{aplus} A:{a} B:{b} C:{c} D:{d} | "
            f"Bullish:{bull} Bearish:{bear} | "
            f"Avg Score: {int(round(avg))}"
        )
    except Exception:
        return ""


def format_result_row(result: Any, index: int) -> str:
    """Format a single-line result entry for a ranked dashboard list.

    Format:
    "#1 | 🟢 XAUUSD M1 | Score:75 ██████░░░░ | A+ Setup | OB:✅ FVG:✅ LIQ:✅ BOS:❌ PD:✅ HTF:❌"

    Args:
        result: ScoreResult or any object with the expected display attributes.
        index: 1-based position in the ranked list.

    Returns:
        Formatted single-line string. Returns "" on any error. Never raises.
    """
    try:
        symbol: str = str(getattr(result, "symbol", ""))
        timeframe: str = str(getattr(result, "timeframe", ""))
        direction_emoji: str = str(getattr(result, "direction_emoji", ""))
        direction: str = str(getattr(result, "direction", ""))
        total_score: float = float(getattr(result, "total_score", 0.0))
        grade_label: str = str(getattr(result, "grade_label", ""))

        dir_str = format_direction(direction, direction_emoji)
        score_str = format_score(total_score)
        bar_str = format_score_bar(total_score, width=10)
        checks_str = format_factor_checkmarks(result)

        return (
            f"#{index} | "
            f"{dir_str} {symbol} {timeframe} | "
            f"Score:{score_str} {bar_str} | "
            f"{grade_label} | "
            f"{checks_str}"
        )
    except Exception:
        return ""