from __future__ import annotations

import logging
from typing import Any

from src.scoring.score_rules import (
    GRADE_A_MIN,
    GRADE_APLUS_MIN,
    GRADE_B_MIN,
    GRADE_C_MIN,
    TRADEABLE_MIN_SCORE,
)

__all__ = ["ScoreClassifier", "create_classifier"]

# ---------------------------------------------------------------------------
# Grade ordering — used to guarantee consistent key ordering in group outputs
# ---------------------------------------------------------------------------

_ALL_GRADES: list[str] = ["A+", "A", "B", "C", "D"]
_ALL_DIRECTIONS: list[str] = ["bullish", "bearish"]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely retrieve an attribute from an object or a dict.

    Args:
        obj: Source object or dictionary.
        attr: Attribute / key name.
        default: Fallback value when the attribute is missing.

    Returns:
        Resolved value or *default*.
    """
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _sort_desc(results: list[Any]) -> list[Any]:
    """Return a new list sorted by ``total_score`` descending.

    Args:
        results: List of ScoreResult objects or compatible dicts.

    Returns:
        New list sorted highest score first.
    """
    return sorted(results, key=lambda r: float(_safe_get(r, "total_score", 0.0)), reverse=True)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class ScoreClassifier:
    """Filters, ranks, and groups :class:`~src.models.scoring.ScoreResult` objects.

    Provides pure query utilities used by the scanner and dashboard layers
    to select, order, and group scored setups.  All filter methods return
    **new lists** and never mutate the input.

    Attribute access on each result uses the :func:`_safe_get` helper so the
    methods work equally well with dataclass instances and plain dicts.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Filter methods
    # ------------------------------------------------------------------

    def filter_dashboard(self, results: list[Any]) -> list[Any]:
        """Return results eligible for dashboard display.

        A result is eligible when its ``show_on_dashboard`` field is
        ``True`` (set by :mod:`src.scoring.score_rules`).

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            New list containing only dashboard-eligible results, sorted by
            ``total_score`` descending.
        """
        filtered = [r for r in results if _safe_get(r, "show_on_dashboard", False)]
        return _sort_desc(filtered)

    def filter_tradeable(self, results: list[Any]) -> list[Any]:
        """Return results whose score meets the tradeability threshold.

        A result is tradeable when ``is_tradeable`` is ``True``
        (i.e. ``total_score >= TRADEABLE_MIN_SCORE``).

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            New list of tradeable results, sorted by ``total_score`` descending.
        """
        filtered = [r for r in results if _safe_get(r, "is_tradeable", False)]
        return _sort_desc(filtered)

    def filter_by_grade(
        self, results: list[Any], grades: list[str]
    ) -> list[Any]:
        """Return results whose grade is in the provided set.

        Args:
            results: Full list of ScoreResult objects.
            grades: Grade strings to include, e.g. ``["A+", "A"]``.

        Returns:
            New filtered list sorted by ``total_score`` descending.
        """
        grade_set = set(grades)
        filtered  = [r for r in results if _safe_get(r, "grade", "") in grade_set]
        return _sort_desc(filtered)

    def filter_by_direction(
        self, results: list[Any], direction: str
    ) -> list[Any]:
        """Return results matching a given trade direction.

        Args:
            results: Full list of ScoreResult objects.
            direction: ``"bullish"`` or ``"bearish"`` (case-sensitive).

        Returns:
            New filtered list sorted by ``total_score`` descending.
        """
        filtered = [
            r for r in results
            if _safe_get(r, "direction", "") == direction
        ]
        return _sort_desc(filtered)

    def filter_by_symbol(
        self, results: list[Any], symbol: str
    ) -> list[Any]:
        """Return results for a specific symbol (case-insensitive).

        Args:
            results: Full list of ScoreResult objects.
            symbol: Instrument name, e.g. ``"XAUUSD"``.

        Returns:
            New filtered list sorted by ``total_score`` descending.
        """
        target = symbol.upper()
        filtered = [
            r for r in results
            if str(_safe_get(r, "symbol", "")).upper() == target
        ]
        return _sort_desc(filtered)

    def filter_by_min_score(
        self, results: list[Any], min_score: float
    ) -> list[Any]:
        """Return results whose ``total_score`` is at or above *min_score*.

        Args:
            results: Full list of ScoreResult objects.
            min_score: Minimum score threshold (inclusive).

        Returns:
            New filtered list sorted by ``total_score`` descending.
        """
        filtered = [
            r for r in results
            if float(_safe_get(r, "total_score", 0.0)) >= min_score
        ]
        return _sort_desc(filtered)

    def filter_by_components(
        self,
        results: list[Any],
        require_ob: bool = False,
        require_fvg: bool = False,
        require_sweep: bool = False,
        require_bos: bool = False,
    ) -> list[Any]:
        """Return results that have all the required SMC component flags set.

        Only flags explicitly set to ``True`` are enforced.  Flags left at
        the default ``False`` are not evaluated.

        Args:
            results: Full list of ScoreResult objects.
            require_ob: When ``True``, only include results with
                ``has_order_block=True``.
            require_fvg: When ``True``, only include results with
                ``has_fvg=True``.
            require_sweep: When ``True``, only include results with
                ``has_liquidity_sweep=True``.
            require_bos: When ``True``, only include results with
                ``has_bos=True``.

        Returns:
            New filtered list sorted by ``total_score`` descending.
        """
        filtered: list[Any] = []
        for r in results:
            if require_ob and not _safe_get(r, "has_order_block", False):
                continue
            if require_fvg and not _safe_get(r, "has_fvg", False):
                continue
            if require_sweep and not _safe_get(r, "has_liquidity_sweep", False):
                continue
            if require_bos and not _safe_get(r, "has_bos", False):
                continue
            filtered.append(r)

        return _sort_desc(filtered)

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def top_n(self, results: list[Any], n: int) -> list[Any]:
        """Return the top *n* results by ``total_score``.

        *n* is clamped to a minimum of 1.  When *results* has fewer than
        *n* items the full sorted list is returned.

        Args:
            results: Full list of ScoreResult objects.
            n: Maximum number of results to return.  Values < 1 are treated
                as 1.

        Returns:
            New list of up to *n* results sorted by ``total_score``
            descending.
        """
        n = max(1, n)
        return _sort_desc(results)[:n]

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    def group_by_grade(
        self, results: list[Any]
    ) -> dict[str, list[Any]]:
        """Group results by letter grade.

        All five grade keys are always present in the returned dictionary,
        even when some buckets are empty.

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            Dictionary with keys ``"A+"``, ``"A"``, ``"B"``, ``"C"``,
            ``"D"``, each mapping to a list sorted by ``total_score``
            descending.
        """
        grouped: dict[str, list[Any]] = {g: [] for g in _ALL_GRADES}

        for r in results:
            grade = str(_safe_get(r, "grade", "D"))
            if grade not in grouped:
                self._log.debug("Unknown grade '%s' encountered — placing in 'D'.", grade)
                grade = "D"
            grouped[grade].append(r)

        for grade in grouped:
            grouped[grade] = _sort_desc(grouped[grade])

        return grouped

    def group_by_symbol(
        self, results: list[Any]
    ) -> dict[str, list[Any]]:
        """Group results by instrument symbol.

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            Dictionary keyed by symbol (original case as stored on the
            result), each value sorted by ``total_score`` descending.
        """
        grouped: dict[str, list[Any]] = {}

        for r in results:
            symbol = str(_safe_get(r, "symbol", ""))
            grouped.setdefault(symbol, []).append(r)

        for sym in grouped:
            grouped[sym] = _sort_desc(grouped[sym])

        return grouped

    def group_by_direction(
        self, results: list[Any]
    ) -> dict[str, list[Any]]:
        """Group results by trade direction.

        Both direction keys are always present in the returned dictionary.

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            Dictionary with keys ``"bullish"`` and ``"bearish"``, each
            mapping to a list sorted by ``total_score`` descending.
        """
        grouped: dict[str, list[Any]] = {d: [] for d in _ALL_DIRECTIONS}

        for r in results:
            direction = str(_safe_get(r, "direction", ""))
            if direction not in grouped:
                self._log.debug(
                    "Unknown direction '%s' encountered — skipping.", direction
                )
                continue
            grouped[direction].append(r)

        for d in grouped:
            grouped[d] = _sort_desc(grouped[d])

        return grouped

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def get_best_per_symbol(self, results: list[Any]) -> list[Any]:
        """Return the highest-scoring result for each unique symbol.

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            New list containing one result per symbol (the one with the
            highest ``total_score``), sorted by ``total_score`` descending.
        """
        best: dict[str, Any] = {}

        for r in results:
            symbol = str(_safe_get(r, "symbol", ""))
            score  = float(_safe_get(r, "total_score", 0.0))
            if symbol not in best:
                best[symbol] = r
            else:
                current_best_score = float(
                    _safe_get(best[symbol], "total_score", 0.0)
                )
                if score > current_best_score:
                    best[symbol] = r

        return _sort_desc(list(best.values()))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summarize(self, results: list[Any]) -> dict[str, Any]:
        """Compute aggregate statistics for a list of ScoreResult objects.

        Args:
            results: Full list of ScoreResult objects.

        Returns:
            Dictionary with the following keys:

            - ``"total"`` (int): Total number of results.
            - ``"dashboard_count"`` (int): Results with
              ``show_on_dashboard=True``.
            - ``"tradeable_count"`` (int): Results with
              ``is_tradeable=True``.
            - ``"aplus_count"`` (int): Results with grade ``"A+"``.
            - ``"a_count"`` (int): Results with grade ``"A"``.
            - ``"b_count"`` (int): Results with grade ``"B"``.
            - ``"c_count"`` (int): Results with grade ``"C"``.
            - ``"d_count"`` (int): Results with grade ``"D"``.
            - ``"bullish_count"`` (int): Bullish direction results.
            - ``"bearish_count"`` (int): Bearish direction results.
            - ``"avg_score"`` (float): Mean ``total_score`` (0.0 when
              *results* is empty).
            - ``"top_score"`` (float): Highest ``total_score`` (0.0 when
              empty).
            - ``"symbols"`` (list[str]): Unique symbol names, sorted
              alphabetically.
        """
        total = len(results)

        dashboard_count  = sum(1 for r in results if _safe_get(r, "show_on_dashboard", False))
        tradeable_count  = sum(1 for r in results if _safe_get(r, "is_tradeable", False))
        aplus_count      = sum(1 for r in results if _safe_get(r, "grade", "") == "A+")
        a_count          = sum(1 for r in results if _safe_get(r, "grade", "") == "A")
        b_count          = sum(1 for r in results if _safe_get(r, "grade", "") == "B")
        c_count          = sum(1 for r in results if _safe_get(r, "grade", "") == "C")
        d_count          = sum(1 for r in results if _safe_get(r, "grade", "") == "D")
        bullish_count    = sum(1 for r in results if _safe_get(r, "direction", "") == "bullish")
        bearish_count    = sum(1 for r in results if _safe_get(r, "direction", "") == "bearish")

        scores = [float(_safe_get(r, "total_score", 0.0)) for r in results]
        avg_score = sum(scores) / total if total > 0 else 0.0
        top_score = max(scores, default=0.0)

        symbols = sorted(
            {str(_safe_get(r, "symbol", "")) for r in results}
        )

        return {
            "total": total,
            "dashboard_count": dashboard_count,
            "tradeable_count": tradeable_count,
            "aplus_count": aplus_count,
            "a_count": a_count,
            "b_count": b_count,
            "c_count": c_count,
            "d_count": d_count,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "avg_score": avg_score,
            "top_score": top_score,
            "symbols": symbols,
        }


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_classifier() -> ScoreClassifier:
    """Factory — return a configured :class:`ScoreClassifier`.

    Returns:
        Ready-to-use :class:`ScoreClassifier` instance.
    """
    return ScoreClassifier()