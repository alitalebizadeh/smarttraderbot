import pandas as pd

from src.liquidity_engine.levels import (
    detect_equal_highs,
    detect_equal_lows,
    detect_previous_day_levels,
    detect_weekly_levels,
)
from src.liquidity_engine.sweep_detector import detect_sweeps


def _frame_from_rows(rows: list[dict[str, float]]) -> pd.DataFrame:
    """Create a simple OHLCV frame for synthetic liquidity tests."""
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame["time"], utc=True)
    frame = frame.drop(columns=["time"])
    return frame.astype(float)


def test_pdh_pdl_detected_correctly() -> None:
    """Previous day highs and lows should be detected for a completed prior day."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 100.0, "high": 104.0, "low": 99.0, "close": 102.0},
        {"time": "2024-01-01 00:05:00+00:00", "open": 101.0, "high": 103.0, "low": 98.0, "close": 100.0},
        {"time": "2024-01-02 00:00:00+00:00", "open": 99.0, "high": 101.0, "low": 97.0, "close": 98.0},
        {"time": "2024-01-03 00:00:00+00:00", "open": 98.0, "high": 102.0, "low": 96.0, "close": 100.0},
    ]
    df = _frame_from_rows(rows)
    levels = detect_previous_day_levels(df)
    assert len(levels) == 4
    assert {level.level_type for level in levels} == {"PDH", "PDL"}
    assert any(level.price == 104.0 for level in levels)
    assert any(level.price == 97.0 for level in levels)


def test_weekly_high_low_detected() -> None:
    """The weekly high and low should be computed from full completed ISO weeks."""
    rows = [
        {"time": "2024-01-08 00:00:00+00:00", "open": 95.0, "high": 98.0, "low": 94.0, "close": 96.0},
        {"time": "2024-01-09 00:00:00+00:00", "open": 96.0, "high": 101.0, "low": 95.0, "close": 99.0},
        {"time": "2024-01-10 00:00:00+00:00", "open": 99.0, "high": 100.5, "low": 96.0, "close": 97.0},
        {"time": "2024-01-11 00:00:00+00:00", "open": 97.0, "high": 99.0, "low": 93.5, "close": 94.0},
        {"time": "2024-01-12 00:00:00+00:00", "open": 94.0, "high": 102.0, "low": 92.0, "close": 101.0},
        {"time": "2024-01-15 00:00:00+00:00", "open": 102.0, "high": 103.0, "low": 100.0, "close": 101.5},
    ]
    df = _frame_from_rows(rows)
    levels = detect_weekly_levels(df)
    assert {level.level_type for level in levels} == {"WH", "WL"}
    assert any(level.price == 102.0 for level in levels)
    assert any(level.price == 92.0 for level in levels)


def test_equal_highs_detected_within_threshold() -> None:
    """Two swing highs within 0.1% should cluster as an EQH level."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 100.0, "high": 100.0, "low": 99.5, "close": 99.8},
        {"time": "2024-01-01 00:05:00+00:00", "open": 100.1, "high": 100.05, "low": 99.6, "close": 99.9},
        {"time": "2024-01-01 00:10:00+00:00", "open": 100.0, "high": 100.03, "low": 99.7, "close": 100.0},
    ]
    df = _frame_from_rows(rows)
    levels = detect_equal_highs(df, [100.0, 100.05, 100.03], [df.index[0], df.index[1], df.index[2]])
    assert len(levels) == 1
    assert levels[0].level_type == "EQH"
    assert abs(levels[0].price - 100.02666666666667) < 1e-9


def test_equal_lows_detected_within_threshold() -> None:
    """Two swing lows within 0.1% should cluster as an EQL level."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 99.8},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.9, "high": 100.8, "low": 98.98, "close": 99.3},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.1, "high": 100.5, "low": 98.95, "close": 99.0},
    ]
    df = _frame_from_rows(rows)
    levels = detect_equal_lows(df, [99.0, 98.98, 98.95], [df.index[0], df.index[1], df.index[2]])
    assert len(levels) == 1
    assert levels[0].level_type == "EQL"
    assert abs(levels[0].price - 98.97666666666666) < 1e-9


def test_no_false_level_on_random_data() -> None:
    """Only completed prior periods should count; same-day data should not generate daily or weekly levels."""
    base = pd.Timestamp.now(tz="UTC").floor("D")
    rows = [
        {"time": str(base), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
        {"time": str(base + pd.Timedelta(minutes=5)), "open": 101.5, "high": 104.0, "low": 100.0, "close": 103.5},
        {"time": str(base + pd.Timedelta(minutes=10)), "open": 103.0, "high": 106.0, "low": 101.0, "close": 104.0},
    ]
    df = _frame_from_rows(rows)
    previous_day_levels = detect_previous_day_levels(df)
    weekly_levels = detect_weekly_levels(df)
    eqh = detect_equal_highs(df, [101.0, 104.0, 106.0], [df.index[0], df.index[1], df.index[2]])
    eql = detect_equal_lows(df, [99.0, 100.0, 101.0], [df.index[0], df.index[1], df.index[2]])
    assert previous_day_levels == []
    assert weekly_levels == []
    assert eqh == []
    assert eql == []


def test_sweep_valid_wick_and_close_back() -> None:
    """A valid sweep requires a wick beyond the level, close back inside, and next-candle confirmation."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 99.0, "high": 99.8, "low": 98.8, "close": 99.2},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.1, "high": 100.2, "low": 98.9, "close": 99.6},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.7, "high": 101.5, "low": 99.5, "close": 99.8},
        {"time": "2024-01-01 00:15:00+00:00", "open": 99.9, "high": 100.1, "low": 99.4, "close": 99.5},
    ]
    df = _frame_from_rows(rows)
    atr = pd.Series([1.0] * len(df), dtype=float)
    level = type("Level", (), {"level_type": "PDH", "price": 100.0, "formed_at": df.index[0], "is_swept": False})()
    sweeps = detect_sweeps(df, [level], atr)
    assert len(sweeps) == 1
    assert sweeps[0].rejection_confirmed is True
    assert sweeps[0].confirmation_candle_index == 3


def test_sweep_rejected_no_close_back() -> None:
    """If the candle closes on the same side of the level, it is not a valid sweep."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 99.0, "high": 99.8, "low": 98.8, "close": 99.2},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.1, "high": 100.2, "low": 98.9, "close": 99.6},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.7, "high": 101.5, "low": 99.5, "close": 100.5},
        {"time": "2024-01-01 00:15:00+00:00", "open": 100.5, "high": 101.0, "low": 99.8, "close": 101.0},
    ]
    df = _frame_from_rows(rows)
    atr = pd.Series([1.0] * len(df), dtype=float)
    level = type("Level", (), {"level_type": "PDH", "price": 100.0, "formed_at": df.index[0], "is_swept": False})()
    assert detect_sweeps(df, [level], atr) == []


def test_sweep_rejected_wick_only() -> None:
    """A wick beyond the level without a close back should not count as a sweep."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 99.0, "high": 99.8, "low": 98.8, "close": 99.2},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.1, "high": 100.2, "low": 98.9, "close": 99.6},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.7, "high": 101.5, "low": 99.5, "close": 100.3},
        {"time": "2024-01-01 00:15:00+00:00", "open": 100.2, "high": 100.7, "low": 99.3, "close": 100.6},
    ]
    df = _frame_from_rows(rows)
    atr = pd.Series([1.0] * len(df), dtype=float)
    level = type("Level", (), {"level_type": "PDH", "price": 100.0, "formed_at": df.index[0], "is_swept": False})()
    assert detect_sweeps(df, [level], atr) == []


def test_sweep_confirmation_candle_required() -> None:
    """Without immediate confirmation after the sweep bar, the event is rejected."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 99.0, "high": 99.8, "low": 98.8, "close": 99.2},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.1, "high": 100.2, "low": 98.9, "close": 99.6},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.7, "high": 101.5, "low": 99.5, "close": 99.8},
        {"time": "2024-01-01 00:15:00+00:00", "open": 100.0, "high": 100.7, "low": 99.7, "close": 100.4},
        {"time": "2024-01-01 00:20:00+00:00", "open": 100.5, "high": 101.5, "low": 100.0, "close": 100.8},
    ]
    df = _frame_from_rows(rows)
    atr = pd.Series([1.0] * len(df), dtype=float)
    level = type("Level", (), {"level_type": "PDH", "price": 100.0, "formed_at": df.index[0], "is_swept": False})()
    assert detect_sweeps(df, [level], atr) == []


def test_sweep_no_lookahead_bias() -> None:
    """Only the immediate next candle should count as confirmation; later bars must not be used."""
    rows = [
        {"time": "2024-01-01 00:00:00+00:00", "open": 99.0, "high": 99.8, "low": 98.8, "close": 99.2},
        {"time": "2024-01-01 00:05:00+00:00", "open": 99.1, "high": 100.2, "low": 98.9, "close": 99.6},
        {"time": "2024-01-01 00:10:00+00:00", "open": 99.7, "high": 101.5, "low": 99.5, "close": 99.8},
        {"time": "2024-01-01 00:15:00+00:00", "open": 100.1, "high": 100.8, "low": 99.9, "close": 100.2},
        {"time": "2024-01-01 00:20:00+00:00", "open": 100.3, "high": 101.0, "low": 99.8, "close": 100.1},
        {"time": "2024-01-01 00:25:00+00:00", "open": 100.0, "high": 100.9, "low": 99.7, "close": 100.5},
    ]
    df = _frame_from_rows(rows)
    atr = pd.Series([1.0] * len(df), dtype=float)
    level = type("Level", (), {"level_type": "PDH", "price": 100.0, "formed_at": df.index[0], "is_swept": False})()
    assert detect_sweeps(df, [level], atr) == []
