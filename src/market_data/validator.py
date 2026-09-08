from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

__all__ = [
    "CandleDataError",
    "CandleValidationReport",
    "normalize_ohlcv",
    "slice_as_of",
]

_REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
_TIMEFRAME_MINUTES = {
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "DAILY": 1440,
}


class CandleDataError(ValueError):
    """Raised when OHLCV data violates the market-data contract."""


@dataclass(frozen=True)
class CandleValidationReport:
    """Auditable data-quality facts for a normalized candle frame."""

    rows_received: int
    rows_returned: int
    duplicates_removed: int
    invalid_rows_removed: int
    missing_intervals: tuple[pd.Timestamp, ...]
    timeframe: str

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_intervals)


def normalize_ohlcv(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    drop_invalid: bool = False,
    report: list[CandleValidationReport] | None = None,
) -> pd.DataFrame:
    """Normalize an OHLCV frame into a sorted, UTC, unique time index.

    The function does not impute missing candles. Invalid rows are rejected by
    default, while ``drop_invalid=True`` permits an explicit audit trail via
    the returned validation report.
    """
    logger = logging.getLogger(__name__)
    if frame is None or frame.empty:
        raise CandleDataError("OHLCV data is empty")

    data = frame.copy()
    columns = {str(column).strip().lower(): column for column in data.columns}
    missing = [column for column in _REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise CandleDataError(f"Missing OHLCV columns: {', '.join(missing)}")
    data = data.rename(columns={columns[name]: name for name in _REQUIRED_COLUMNS})

    if "time" in columns:
        timestamps = pd.to_datetime(data[columns["time"]], utc=True, errors="coerce")
        data = data.drop(columns=[columns["time"]])
    else:
        timestamps = pd.to_datetime(data.index, utc=True, errors="coerce")

    data.index = timestamps
    data.index.name = "time"
    if data.index.isna().any():
        raise CandleDataError("OHLCV data contains invalid timestamps")

    data = data.sort_index()
    duplicate_count = int(data.index.duplicated(keep="last").sum())
    if duplicate_count:
        data = data[~data.index.duplicated(keep="last")]

    numeric = data.loc[:, _REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().all(axis=1)
    valid &= numeric[["open", "high", "low", "close"]].gt(0).all(axis=1)
    valid &= numeric["high"].ge(numeric[["open", "close", "low"]].max(axis=1))
    valid &= numeric["low"].le(numeric[["open", "close", "high"]].min(axis=1))
    valid &= numeric["volume"].ge(0)
    invalid_count = int((~valid).sum())
    if invalid_count and not drop_invalid:
        raise CandleDataError(f"OHLCV data contains {invalid_count} invalid rows")
    data = numeric.loc[valid].copy()

    normalized_timeframe = str(timeframe).strip().upper()
    if normalized_timeframe not in _TIMEFRAME_MINUTES:
        raise CandleDataError(f"Unsupported timeframe: {timeframe}")
    missing_intervals = _find_missing_intervals(data.index, normalized_timeframe)
    validation = CandleValidationReport(
        rows_received=len(frame),
        rows_returned=len(data),
        duplicates_removed=duplicate_count,
        invalid_rows_removed=invalid_count,
        missing_intervals=tuple(missing_intervals),
        timeframe=normalized_timeframe,
    )
    if report is not None:
        report.append(validation)
    logger.debug("Normalized %d candles for %s", len(data), normalized_timeframe)
    return data


def slice_as_of(frame: pd.DataFrame, as_of: datetime | pd.Timestamp) -> pd.DataFrame:
    """Return only candles whose close time is at or before ``as_of``."""
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    timestamps = pd.to_datetime(frame.index, utc=True, errors="raise")
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    result = frame.copy()
    result.index = timestamps
    return result.loc[result.index <= cutoff].copy()


def _find_missing_intervals(index: pd.DatetimeIndex, timeframe: str) -> list[pd.Timestamp]:
    if len(index) < 2:
        return []
    expected = pd.Timedelta(minutes=_TIMEFRAME_MINUTES[timeframe])
    gaps: list[pd.Timestamp] = []
    for previous, current in zip(index[:-1], index[1:]):
        missing = int((current - previous) / expected) - 1
        if missing > 0:
            gaps.extend(previous + expected * step for step in range(1, missing + 1))
    return gaps
