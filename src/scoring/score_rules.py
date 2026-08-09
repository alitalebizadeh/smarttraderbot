from __future__ import annotations

__all__ = [
    # Weight constants
    "SCORE_ORDER_BLOCK",
    "SCORE_FVG",
    "SCORE_LIQUIDITY_SWEEP",
    "SCORE_BOS",
    "SCORE_PREMIUM_DISCOUNT",
    "SCORE_HTF_ALIGNMENT",
    "MAX_TOTAL_SCORE",
    # Grade threshold constants
    "GRADE_APLUS_MIN",
    "GRADE_A_MIN",
    "GRADE_B_MIN",
    "GRADE_C_MIN",
    "GRADE_LABELS",
    "GRADE_COLORS",
    "SHOW_ON_DASHBOARD",
    "TRADEABLE_MIN_SCORE",
    # Direction helpers
    "DIRECTION_EMOJI",
    # Pure functions
    "assign_grade",
    "get_grade_label",
    "get_grade_color",
    "is_tradeable",
    "show_on_dashboard",
    "get_direction_emoji",
    "build_summary",
    "validate_score",
    "compute_score_pct",
]

# ---------------------------------------------------------------------------
# Score weight constants
# ---------------------------------------------------------------------------

SCORE_ORDER_BLOCK: float = 20.0
SCORE_FVG: float = 20.0
SCORE_LIQUIDITY_SWEEP: float = 25.0
SCORE_BOS: float = 15.0
SCORE_PREMIUM_DISCOUNT: float = 10.0
SCORE_HTF_ALIGNMENT: float = 10.0
MAX_TOTAL_SCORE: float = 100.0

# ---------------------------------------------------------------------------
# Grade threshold constants
# ---------------------------------------------------------------------------

GRADE_APLUS_MIN: float = 80.0
GRADE_A_MIN: float = 65.0
GRADE_B_MIN: float = 50.0
GRADE_C_MIN: float = 35.0

GRADE_LABELS: dict[str, str] = {
    "A+": "A+ Setup",
    "A":  "Strong Setup",
    "B":  "Good Setup",
    "C":  "Weak Setup",
    "D":  "Poor Setup",
}

GRADE_COLORS: dict[str, str] = {
    "A+": "#28a745",
    "A":  "#17a2b8",
    "B":  "#ffc107",
    "C":  "#fd7e14",
    "D":  "#dc3545",
}

SHOW_ON_DASHBOARD: set[str] = {"A+", "A", "B"}

TRADEABLE_MIN_SCORE: float = 60.0

# ---------------------------------------------------------------------------
# Direction helpers
# ---------------------------------------------------------------------------

DIRECTION_EMOJI: dict[str, str] = {
    "bullish": "🟢",
    "bearish": "🔴",
}

_FALLBACK_LABEL: str = "Unknown Setup"
_FALLBACK_COLOR: str = "#6c757d"
_FALLBACK_EMOJI: str = "⚪"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def assign_grade(total_score: float) -> str:
    """Return the letter grade for a given confluence score.

    Grades are assigned by comparing *total_score* against the module-level
    threshold constants in descending order.  Scores outside ``[0, 100]``
    are accepted without clamping — use :func:`validate_score` first if
    strict range enforcement is needed.

    Args:
        total_score: Numeric score in the range ``[0.0, 100.0]``.

    Returns:
        One of ``"A+"``, ``"A"``, ``"B"``, ``"C"``, or ``"D"``.

    Examples:
        >>> assign_grade(85.0)
        'A+'
        >>> assign_grade(70.0)
        'A'
        >>> assign_grade(20.0)
        'D'
    """
    if total_score >= GRADE_APLUS_MIN:
        return "A+"
    if total_score >= GRADE_A_MIN:
        return "A"
    if total_score >= GRADE_B_MIN:
        return "B"
    if total_score >= GRADE_C_MIN:
        return "C"
    return "D"


def get_grade_label(grade: str) -> str:
    """Return the human-readable label for a letter grade.

    Falls back to ``"Unknown Setup"`` for unrecognised grades so the
    function never raises.

    Args:
        grade: Letter grade string, e.g. ``"A+"``, ``"B"``.

    Returns:
        Human-readable label string, e.g. ``"Strong Setup"``.

    Examples:
        >>> get_grade_label("A")
        'Strong Setup'
        >>> get_grade_label("Z")
        'Unknown Setup'
    """
    return GRADE_LABELS.get(grade, _FALLBACK_LABEL)


def get_grade_color(grade: str) -> str:
    """Return the hex colour code associated with a letter grade.

    Falls back to a neutral grey (``"#6c757d"``) for unrecognised grades.

    Args:
        grade: Letter grade string, e.g. ``"A+"``, ``"C"``.

    Returns:
        Hex colour string, e.g. ``"#28a745"``.

    Examples:
        >>> get_grade_color("A+")
        '#28a745'
        >>> get_grade_color("X")
        '#6c757d'
    """
    return GRADE_COLORS.get(grade, _FALLBACK_COLOR)


def is_tradeable(total_score: float) -> bool:
    """Return ``True`` when *total_score* meets the tradeability threshold.

    A setup is considered tradeable when its score is greater than or equal
    to :data:`TRADEABLE_MIN_SCORE` (60.0 by default).

    Args:
        total_score: Numeric confluence score.

    Returns:
        ``True`` when ``total_score >= TRADEABLE_MIN_SCORE``.

    Examples:
        >>> is_tradeable(60.0)
        True
        >>> is_tradeable(59.9)
        False
    """
    return total_score >= TRADEABLE_MIN_SCORE


def show_on_dashboard(grade: str) -> bool:
    """Return ``True`` when a setup with this grade should appear on the dashboard.

    Only grades in :data:`SHOW_ON_DASHBOARD` (``{"A+", "A", "B"}``) are
    displayed by default, filtering out weak and poor setups.

    Args:
        grade: Letter grade string, e.g. ``"A"``, ``"D"``.

    Returns:
        ``True`` when the grade is in :data:`SHOW_ON_DASHBOARD`.

    Examples:
        >>> show_on_dashboard("A+")
        True
        >>> show_on_dashboard("D")
        False
    """
    return grade in SHOW_ON_DASHBOARD


def get_direction_emoji(direction: str) -> str:
    """Return the emoji representing a trade direction.

    Falls back to ``"⚪"`` for unrecognised direction strings so the
    function never raises.

    Args:
        direction: Direction string — ``"bullish"`` or ``"bearish"``.

    Returns:
        Emoji string: ``"🟢"`` for bullish, ``"🔴"`` for bearish, ``"⚪"``
        for anything else.

    Examples:
        >>> get_direction_emoji("bullish")
        '🟢'
        >>> get_direction_emoji("sideways")
        '⚪'
    """
    return DIRECTION_EMOJI.get(direction.lower(), _FALLBACK_EMOJI)


def build_summary(
    symbol: str,
    timeframe: str,
    direction: str,
    total_score: float,
    grade_label: str,
) -> str:
    """Build a one-line human-readable summary for a scored setup.

    Format:
        ``"{symbol} {timeframe} | {DIRECTION} | Score: {score:.0f} | {grade_label}"``

    Args:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        direction: Direction string — ``"bullish"`` or ``"bearish"``.
        total_score: Numeric confluence score.
        grade_label: Human-readable grade label, e.g. ``"Strong Setup"``.

    Returns:
        Formatted summary string.

    Examples:
        >>> build_summary("XAUUSD", "M1", "bullish", 75.0, "Strong Setup")
        'XAUUSD M1 | BULLISH | Score: 75 | Strong Setup'
    """
    return (
        f"{symbol} {timeframe} | "
        f"{direction.upper()} | "
        f"Score: {total_score:.0f} | "
        f"{grade_label}"
    )


def validate_score(total_score: float) -> float:
    """Clamp *total_score* to the valid range ``[0.0, MAX_TOTAL_SCORE]``.

    This is a pure utility function — it does not raise for out-of-range
    values but silently clamps them.

    Args:
        total_score: Raw numeric score, potentially outside ``[0, 100]``.

    Returns:
        Score clamped to ``[0.0, MAX_TOTAL_SCORE]``.

    Examples:
        >>> validate_score(110.0)
        100.0
        >>> validate_score(-5.0)
        0.0
        >>> validate_score(75.0)
        75.0
    """
    return max(0.0, min(total_score, MAX_TOTAL_SCORE))


def compute_score_pct(total_score: float) -> float:
    """Return *total_score* as a percentage of :data:`MAX_TOTAL_SCORE`.

    The result is clamped to ``[0.0, 100.0]``.  When ``MAX_TOTAL_SCORE``
    is zero (degenerate configuration), 0.0 is returned.

    Args:
        total_score: Numeric confluence score.

    Returns:
        Percentage value in ``[0.0, 100.0]``.

    Examples:
        >>> compute_score_pct(75.0)
        75.0
        >>> compute_score_pct(110.0)
        100.0
        >>> compute_score_pct(-10.0)
        0.0
    """
    if MAX_TOTAL_SCORE <= 0:
        return 0.0
    pct = total_score / MAX_TOTAL_SCORE * 100.0
    return max(0.0, min(pct, 100.0))
