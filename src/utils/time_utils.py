from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Optional

__all__ = [
    # Constants
    "TIMEFRAME_SECONDS",
    "MARKET_SESSIONS",
    # UTC helpers
    "utcnow",
    "to_utc_timestamp",
    "from_utc_timestamp",
    # Formatting
    "format_datetime",
    "format_time_only",
    "format_date_only",
    "format_duration_ms",
    # Parsing
    "parse_mt5_time",
    "parse_timeframe_to_seconds",
    # Calculation
    "get_next_scan_time",
    "seconds_until",
    "is_within_seconds",
    "candles_since",
    # Sessions
    "get_active_sessions",
    "is_market_open",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

TIMEFRAME_SECONDS: dict[str, int] = {
    "M1":  60,
    "M5":  300,
    "M15": 900,
    "M30": 1_800,
    "H1":  3_600,
    "H4":  14_400,
    "D1":  86_400,
    "W1":  604_800,
    "MN":  2_592_000,
}

MARKET_SESSIONS: dict[str, dict[str, int]] = {
    "sydney":   {"open": 21, "close": 6},
    "tokyo":    {"open": 0,  "close": 9},
    "london":   {"open": 7,  "close": 16},
    "new_york": {"open": 12, "close": 21},
}

_DEFAULT_TF_SECONDS: int = 60          # M1 fallback
_EPOCH: datetime = datetime(1970, 1, 1)
_MS_PER_SECOND: float = 1_000.0
_MS_PER_MINUTE: float = 60_000.0

# MT5 timestamp formats tried in order
_MT5_FORMATS: tuple[str, ...] = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


# ─────────────────────────────────────────────
#  UTC Helpers
# ─────────────────────────────────────────────

def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (no tzinfo).

    Returns:
        Current UTC datetime with tzinfo=None. Never raises.
    """
    try:
        return datetime.utcnow()
    except Exception:
        return _EPOCH


def to_utc_timestamp(dt: datetime) -> float:
    """Convert a datetime to a UTC Unix timestamp (seconds since epoch).

    If dt has no tzinfo it is treated as UTC. If dt is timezone-aware,
    it is converted to UTC before computing the timestamp.

    Args:
        dt: datetime to convert.

    Returns:
        Float seconds since 1970-01-01 00:00:00 UTC.
        Returns 0.0 on any error.
    """
    try:
        if dt.tzinfo is not None:
            # Convert to UTC then strip tzinfo
            utc_dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            utc_dt = dt
        return calendar.timegm(utc_dt.timetuple()) + utc_dt.microsecond / 1_000_000.0
    except Exception:
        return 0.0


def from_utc_timestamp(ts: float) -> datetime:
    """Convert a UTC Unix timestamp to a naive datetime (UTC, no tzinfo).

    Args:
        ts: Seconds since 1970-01-01 00:00:00 UTC.

    Returns:
        Corresponding naive UTC datetime.
        Returns datetime(1970, 1, 1) on any error.
    """
    try:
        return datetime.utcfromtimestamp(float(ts))
    except Exception:
        return _EPOCH


# ─────────────────────────────────────────────
#  Formatting
# ─────────────────────────────────────────────

def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object to a string using the given strftime format.

    Args:
        dt: datetime to format.
        fmt: strftime format string. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        Formatted datetime string, or "" on any error.
    """
    try:
        return dt.strftime(fmt)
    except Exception:
        return ""


def format_time_only(dt: datetime) -> str:
    """Format a datetime to a time-only string "HH:MM:SS".

    Args:
        dt: datetime to format.

    Returns:
        Time string in "HH:MM:SS" format, or "" on any error.
    """
    try:
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ""


def format_date_only(dt: datetime) -> str:
    """Format a datetime to a date-only string "YYYY-MM-DD".

    Args:
        dt: datetime to format.

    Returns:
        Date string in "YYYY-MM-DD" format, or "" on any error.
    """
    try:
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def format_duration_ms(milliseconds: float) -> str:
    """Convert a duration in milliseconds to a human-readable string.

    Formatting rules:
    - < 1 000 ms  →  "Xms"    (e.g. "142ms")
    - < 60 000 ms →  "X.Xs"   (e.g. "3.5s")
    - >= 60 000 ms → "Xm Ys"  (e.g. "2m 15s")

    Args:
        milliseconds: Duration in milliseconds.

    Returns:
        Human-readable duration string, or "0ms" on any error.
    """
    try:
        ms = float(milliseconds)
        if ms < _MS_PER_SECOND:
            return f"{int(ms)}ms"
        if ms < _MS_PER_MINUTE:
            seconds = ms / _MS_PER_SECOND
            return f"{seconds:.1f}s"
        total_seconds = int(ms / _MS_PER_SECOND)
        minutes = total_seconds // 60
        remaining_seconds = total_seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    except Exception:
        return "0ms"


# ─────────────────────────────────────────────
#  Parsing
# ─────────────────────────────────────────────

def parse_mt5_time(time_str: str) -> Optional[datetime]:
    """Parse an MT5-exported timestamp string to a naive datetime.

    Tries multiple formats used by MetaTrader 5 CSV exports:
    - "2024.01.15 09:00"       (primary)
    - "2024-01-15 09:00:00"    (alternative)
    - "2024.01.15"             (date only)
    - and further variants

    Args:
        time_str: Raw timestamp string from an MT5 CSV file.

    Returns:
        Parsed datetime, or None if no format matches. Never raises.
    """
    try:
        if not isinstance(time_str, str) or not time_str.strip():
            return None
        stripped = time_str.strip()
        for fmt in _MT5_FORMATS:
            try:
                return datetime.strptime(stripped, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def parse_timeframe_to_seconds(timeframe: str) -> int:
    """Return the number of seconds in one candle for the given timeframe.

    Args:
        timeframe: Timeframe string (e.g. "M1", "H4", "D1").

    Returns:
        Duration in seconds. Returns 60 (M1) for unrecognized timeframes.
        Never raises.
    """
    try:
        return TIMEFRAME_SECONDS.get(timeframe.strip().upper(), _DEFAULT_TF_SECONDS)
    except Exception:
        return _DEFAULT_TF_SECONDS


# ─────────────────────────────────────────────
#  Calculation
# ─────────────────────────────────────────────

def get_next_scan_time(last_scan: datetime, interval_seconds: int) -> datetime:
    """Calculate the next scheduled scan time.

    Args:
        last_scan: Datetime of the previous scan.
        interval_seconds: Number of seconds between scans.

    Returns:
        last_scan + interval_seconds as a datetime.
        Falls back to utcnow() + interval_seconds if last_scan is invalid.
        Never raises.
    """
    try:
        return last_scan + timedelta(seconds=int(interval_seconds))
    except Exception:
        try:
            return utcnow() + timedelta(seconds=int(interval_seconds))
        except Exception:
            return utcnow()


def seconds_until(target: datetime) -> float:
    """Return the number of seconds from now until the target datetime.

    Args:
        target: Future datetime to measure until.

    Returns:
        Positive float seconds remaining, or 0.0 if target is in the past
        or on any error. Never raises.
    """
    try:
        delta = (target - utcnow()).total_seconds()
        return max(0.0, delta)
    except Exception:
        return 0.0


def is_within_seconds(
    dt: datetime,
    reference: datetime,
    seconds: float,
) -> bool:
    """Return True if dt is within the given number of seconds of reference.

    Args:
        dt: datetime to test.
        reference: Reference datetime to compare against.
        seconds: Maximum allowed absolute difference in seconds.

    Returns:
        True if abs(dt - reference).total_seconds() <= seconds.
        False on any error. Never raises.
    """
    try:
        diff = abs((dt - reference).total_seconds())
        return diff <= float(seconds)
    except Exception:
        return False


def candles_since(start: datetime, timeframe: str) -> int:
    """Return the approximate number of candles elapsed since start until now.

    Formula: int((utcnow() - start).total_seconds() / candle_seconds)

    Args:
        start: Start datetime (must be in the past for a positive result).
        timeframe: Timeframe string (e.g. "M1", "H1").

    Returns:
        Non-negative integer candle count. Returns 0 if start is in the future
        or on any error. Never raises.
    """
    try:
        candle_seconds = parse_timeframe_to_seconds(timeframe)
        elapsed = (utcnow() - start).total_seconds()
        if elapsed <= 0:
            return 0
        return int(elapsed / candle_seconds)
    except Exception:
        return 0


# ─────────────────────────────────────────────
#  Market Session Detection
# ─────────────────────────────────────────────

def get_active_sessions(dt: Optional[datetime] = None) -> list[str]:
    """Return the names of forex market sessions active at the given UTC datetime.

    Handles overnight sessions (e.g. Sydney 21:00–06:00) where the session
    spans midnight UTC.

    Args:
        dt: UTC datetime to check. Uses utcnow() when None.

    Returns:
        List of active session name strings (e.g. ["london", "new_york"]).
        Returns [] on any error. Never raises.
    """
    try:
        reference = dt if dt is not None else utcnow()
        current_hour = reference.hour
        active: list[str] = []

        for name, hours in MARKET_SESSIONS.items():
            open_h: int = hours["open"]
            close_h: int = hours["close"]

            if open_h < close_h:
                # Normal session: open and close on the same day
                if open_h <= current_hour < close_h:
                    active.append(name)
            else:
                # Overnight session: spans midnight (e.g. 21:00–06:00)
                if current_hour >= open_h or current_hour < close_h:
                    active.append(name)

        return active
    except Exception:
        return []


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Return True if at least one major forex session is active at dt.

    Args:
        dt: UTC datetime to check. Uses utcnow() when None.

    Returns:
        True if any session is currently active, False otherwise.
        Returns False on any error. Never raises.
    """
    try:
        return len(get_active_sessions(dt)) > 0
    except Exception:
        return False