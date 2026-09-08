from datetime import datetime, timezone

import pandas as pd
import pytest

from src.market_data import CandleDataError, normalize_ohlcv, slice_as_of


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                "2024-01-01T00:15:00Z",
                "2024-01-01T00:15:00Z",
            ],
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [10, 10, 10, 10],
        }
    )


def test_normalization_removes_duplicates_and_reports_gaps() -> None:
    reports = []
    normalized = normalize_ohlcv(_frame(), "M5", report=reports)

    assert normalized.index.tz is not None
    assert normalized.index.is_monotonic_increasing
    assert len(normalized) == 3
    assert reports[0].duplicates_removed == 1
    assert reports[0].missing_intervals == (pd.Timestamp("2024-01-01T00:10:00Z"),)


def test_invalid_rows_are_rejected_without_explicit_drop_policy() -> None:
    frame = _frame()
    frame.loc[0, "low"] = 110

    with pytest.raises(CandleDataError, match="invalid rows"):
        normalize_ohlcv(frame, "M5")


def test_slice_as_of_excludes_future_candles() -> None:
    normalized = normalize_ohlcv(_frame(), "M5", drop_invalid=True)
    sliced = slice_as_of(normalized, datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc))

    assert list(sliced.index) == list(normalized.index[:2])
