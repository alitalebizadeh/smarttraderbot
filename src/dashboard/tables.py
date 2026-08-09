from __future__ import annotations

import html
from typing import Any, Optional

from src.dashboard.formatter import (
    format_direction,
    format_factor_checkmarks,
    format_grade_badge,
    format_pd_zone,
    format_price_range,
    format_scan_header,
    format_scan_stats,
    format_score,
    format_score_bar,
    format_zone_size,
)
from src.utils.logger import get_logger

__all__ = [
    "build_results_table",
    "build_summary_card",
    "build_top_result_card",
    "build_no_data_message",
]

_logger = get_logger(__name__)


# ─────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────

def _grade_css(grade: str) -> str:
    """Convert a grade string to a safe CSS class suffix.

    Args:
        grade: Grade letter (e.g. "A+", "B").

    Returns:
        CSS-safe string (e.g. "aplus", "b"). Never raises.
    """
    try:
        return grade.lower().replace("+", "plus")
    except Exception:
        return "unknown"


def _e(value: Any) -> str:
    """HTML-escape a value converted to string.

    Args:
        value: Any value to escape.

    Returns:
        HTML-escaped string. Never raises.
    """
    try:
        return html.escape(str(value))
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  1. Results Table
# ─────────────────────────────────────────────

def build_results_table(
    results: list[Any],
    title: str = "Top Setups",
    show_empty_message: bool = True,
) -> str:
    """Build the main HTML table showing a ranked list of scored POI results.

    Produces a complete ``<div class="table-container">`` block containing an
    ``<h3>`` heading and a ``<table>`` with one row per ScoreResult.  When the
    results list is empty and show_empty_message is True, a friendly paragraph
    is rendered instead of the table.

    Table columns (in order):
        #, Symbol, Direction, Zone, Score, Grade, Factors, P/D Zone, Trade

    Args:
        results: List of ScoreResult objects to render (may be empty).
        title: Heading text shown above the table. Defaults to "Top Setups".
        show_empty_message: When True and results is empty, renders a
            "No setups found" paragraph instead of an empty table.

    Returns:
        Complete HTML string for the table container.
        Returns "" on any error. Never raises.
    """
    try:
        escaped_title = _e(title)

        if not results:
            if show_empty_message:
                return (
                    f'<div class="table-container">\n'
                    f'  <h3>{escaped_title}</h3>\n'
                    f'  <p class="no-results">No setups found matching the criteria.</p>\n'
                    f'</div>'
                )
            return (
                f'<div class="table-container">\n'
                f'  <h3>{escaped_title}</h3>\n'
                f'</div>'
            )

        rows: list[str] = []
        for rank, result in enumerate(results, start=1):
            try:
                row = _build_result_row(result, rank)
                rows.append(row)
            except Exception as exc:
                _logger.debug("Skipping result row %d due to error: %s", rank, exc)

        tbody = "\n".join(rows)

        return (
            f'<div class="table-container">\n'
            f'  <h3>{escaped_title}</h3>\n'
            f'  <table class="results-table">\n'
            f'    <thead>\n'
            f'      <tr>\n'
            f'        <th>#</th><th>Symbol</th><th>Direction</th><th>Zone</th>\n'
            f'        <th>Score</th><th>Grade</th><th>Factors</th>'
            f'<th>P/D Zone</th><th>Trade</th>\n'
            f'      </tr>\n'
            f'    </thead>\n'
            f'    <tbody>\n'
            f'{tbody}\n'
            f'    </tbody>\n'
            f'  </table>\n'
            f'</div>'
        )
    except Exception:
        return ""


def _build_result_row(result: Any, rank: int) -> str:
    """Build a single ``<tr>`` element for the results table.

    Args:
        result: ScoreResult object.
        rank: 1-based position in the ranked list.

    Returns:
        HTML ``<tr>`` string. Never raises (returns "" on error).
    """
    try:
        symbol       = _e(getattr(result, "symbol", ""))
        timeframe    = _e(getattr(result, "timeframe", ""))
        direction    = str(getattr(result, "direction", ""))
        emoji        = str(getattr(result, "direction_emoji", ""))
        zone_top     = float(getattr(result, "zone_top", 0.0))
        zone_bottom  = float(getattr(result, "zone_bottom", 0.0))
        zone_size    = float(getattr(result, "zone_size", 0.0))
        total_score  = float(getattr(result, "total_score", 0.0))
        grade        = str(getattr(result, "grade", ""))
        grade_color  = str(getattr(result, "grade_color", "#6b7280"))
        pd_zone      = str(getattr(result, "premium_discount_zone", "unknown"))
        is_tradeable = bool(getattr(result, "is_tradeable", False))
        raw_symbol   = str(getattr(result, "symbol", ""))

        grade_lower      = _grade_css(grade)
        direction_fmt    = format_direction(direction, emoji)
        price_range_fmt  = format_price_range(zone_top, zone_bottom, raw_symbol)
        zone_size_fmt    = format_zone_size(zone_size, raw_symbol)
        score_str        = format_score(total_score)
        score_bar        = format_score_bar(total_score, width=10)
        grade_badge      = format_grade_badge(grade, grade_color)
        checkmarks       = format_factor_checkmarks(result)
        pd_fmt           = format_pd_zone(pd_zone)
        tradeable_icon   = "✅" if is_tradeable else "❌"

        return (
            f'      <tr class="grade-{grade_lower}">\n'
            f'        <td>{rank}</td>\n'
            f'        <td><strong>{symbol}</strong> {timeframe}</td>\n'
            f'        <td>{direction_fmt}</td>\n'
            f'        <td class="zone-cell">{price_range_fmt}'
            f'<br><small>{zone_size_fmt}</small></td>\n'
            f'        <td class="score-cell">'
            f'<span class="score-bar">{score_bar}</span> <strong>{score_str}</strong></td>\n'
            f'        <td>{grade_badge}</td>\n'
            f'        <td class="factors-cell"><code>{checkmarks}</code></td>\n'
            f'        <td>{pd_fmt}</td>\n'
            f'        <td>{tradeable_icon}</td>\n'
            f'      </tr>'
        )
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  2. Summary Card
# ─────────────────────────────────────────────

def build_summary_card(summary: Any) -> str:
    """Build an HTML card displaying aggregate statistics for one scan run.

    Renders a ``<div class="summary-card">`` block containing:
    - A header line (symbol, timeframe, price, scan time, duration)
    - A stats line (POI counts, grade distribution, avg score)
    - A grade breakdown row with per-grade counts

    Args:
        summary: ScanSummary object (or any object with the expected attributes).

    Returns:
        Complete HTML string for the summary card.
        Returns "" on any error. Never raises.
    """
    try:
        header_line = format_scan_header(summary)
        stats_line  = format_scan_stats(summary)

        aplus = int(getattr(summary, "aplus_count", 0))
        a     = int(getattr(summary, "a_count", 0))
        b     = int(getattr(summary, "b_count", 0))
        c     = int(getattr(summary, "c_count", 0))
        d     = int(getattr(summary, "d_count", 0))

        return (
            f'<div class="summary-card">\n'
            f'  <div class="summary-header">{_e(header_line)}</div>\n'
            f'  <div class="summary-stats">{_e(stats_line)}</div>\n'
            f'  <div class="grade-breakdown">\n'
            f'    <span class="grade-aplus">A+: {aplus}</span>\n'
            f'    <span class="grade-a">A: {a}</span>\n'
            f'    <span class="grade-b">B: {b}</span>\n'
            f'    <span class="grade-c">C: {c}</span>\n'
            f'    <span class="grade-d">D: {d}</span>\n'
            f'  </div>\n'
            f'</div>'
        )
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  3. Top Result Card
# ─────────────────────────────────────────────

def build_top_result_card(result: Optional[Any]) -> str:
    """Build a highlighted HTML card for the single highest-scored result.

    When result is None, renders a placeholder card with a "No top result
    available" message.

    Args:
        result: ScoreResult object, or None if no result is available.

    Returns:
        Complete HTML string for the top result card.
        Returns "" on any error. Never raises.
    """
    try:
        if result is None:
            return (
                '<div class="top-result-card">'
                '<p>No top result available.</p>'
                '</div>'
            )

        symbol      = _e(getattr(result, "symbol", ""))
        timeframe   = _e(getattr(result, "timeframe", ""))
        direction   = str(getattr(result, "direction", ""))
        emoji       = str(getattr(result, "direction_emoji", ""))
        zone_top    = float(getattr(result, "zone_top", 0.0))
        zone_bottom = float(getattr(result, "zone_bottom", 0.0))
        total_score = float(getattr(result, "total_score", 0.0))
        grade       = str(getattr(result, "grade", ""))
        grade_color = str(getattr(result, "grade_color", "#6b7280"))
        pd_zone     = str(getattr(result, "premium_discount_zone", "unknown"))
        raw_symbol  = str(getattr(result, "symbol", ""))

        grade_lower    = _grade_css(grade)
        direction_fmt  = format_direction(direction, emoji)
        price_range    = format_price_range(zone_top, zone_bottom, raw_symbol)
        score_str      = format_score(total_score)
        score_bar      = format_score_bar(total_score, width=10)
        grade_badge    = format_grade_badge(grade, grade_color)
        pd_fmt         = format_pd_zone(pd_zone)
        checkmarks     = format_factor_checkmarks(result)

        return (
            f'<div class="top-result-card grade-{grade_lower}">\n'
            f'  <div class="top-result-header">\n'
            f'    🏆 Top Setup: {symbol} {timeframe}\n'
            f'  </div>\n'
            f'  <div class="top-result-body">\n'
            f'    <div class="top-direction">{direction_fmt}</div>\n'
            f'    <div class="top-zone">Zone: {price_range}</div>\n'
            f'    <div class="top-score">Score: {score_bar} {score_str}/100</div>\n'
            f'    <div class="top-grade">{grade_badge}</div>\n'
            f'    <div class="top-pd">P/D: {pd_fmt}</div>\n'
            f'    <div class="top-factors">{checkmarks}</div>\n'
            f'  </div>\n'
            f'</div>'
        )
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  4. No Data Message
# ─────────────────────────────────────────────

def build_no_data_message(symbol: str, timeframe: str, reason: str) -> str:
    """Build an HTML warning block explaining why no data is available.

    Args:
        symbol: Trading instrument symbol (e.g. "XAUUSD").
        timeframe: Chart timeframe string (e.g. "M1").
        reason: Human-readable explanation of why data is unavailable.

    Returns:
        HTML ``<div class="no-data-message">`` string.
        Returns "" on any error. Never raises.
    """
    try:
        return (
            f'<div class="no-data-message">\n'
            f'  <span class="warning-icon">⚠️</span>\n'
            f'  <strong>{_e(symbol)} {_e(timeframe)}</strong>: {_e(reason)}\n'
            f'</div>'
        )
    except Exception:
        return ""