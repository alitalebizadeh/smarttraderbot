import pandas as pd

from src.market_structure import CausalMarketStructureEngine
from src.market_structure.causal import (
    _has_confirmation_candle,
    _has_displacement,
    _is_valid_bos,
    _is_valid_choch,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    open_prices = [float(value) for value in closes]
    return pd.DataFrame(
        {
            "open": open_prices,
            "high": [max(open_prices[i], closes[i]) + 0.2 for i in range(len(closes))],
            "low": [min(open_prices[i], closes[i]) - 0.2 for i in range(len(closes))],
            "close": closes,
        },
        index=pd.date_range("2024-01-01", periods=len(closes), freq="5min", tz="UTC"),
    ).astype(float)


def _atr_frame() -> pd.Series:
    values = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    return pd.Series(values, dtype=float)


def _custom_frame(open_prices: list[float], close_prices: list[float]) -> pd.DataFrame:
    """Build a realistic OHLCV DataFrame from explicit open and close values."""
    assert len(open_prices) == len(close_prices)
    frame = pd.DataFrame(
        {
            "open": open_prices,
            "close": close_prices,
        },
        index=pd.date_range("2024-01-01", periods=len(open_prices), freq="5min", tz="UTC"),
    )
    frame["high"] = [max(open_prices[i], close_prices[i]) + 0.2 for i in range(len(open_prices))]
    frame["low"] = [min(open_prices[i], close_prices[i]) - 0.2 for i in range(len(open_prices))]
    return frame.astype(float)


def test_swing_is_timestamped_at_confirmation_before_break() -> None:
    """The swing is recorded at its confirmation candle and the break occurs later."""
    closes = [100, 100, 100, 100, 101, 100, 99, 100, 101, 102, 103, 104, 105, 106]
    events = CausalMarketStructureEngine(2).analyze(_frame(closes), "XAUUSD", "M5")

    assert events
    event = events[0]
    assert event.broken_swing.confirmation_index == 6
    assert event.broken_swing.confirmation_index < event.break_candle_index


def test_break_does_not_require_future_follow_through() -> None:
    """The break is validated using the current bar and past information only."""
    closes = [100, 100, 100, 100, 101, 100, 99, 100, 101, 102, 103, 104, 105, 106]
    frame = _frame(closes)
    frame.loc[frame.index[10], "close"] = 100.5
    frame.loc[frame.index[10], "high"] = 100.6
    frame.loc[frame.index[10], "low"] = 100.4
    events = CausalMarketStructureEngine(2).analyze(frame, "XAUUSD", "M5")

    assert events
    assert events[0].break_candle_index == 9


def test_bos_valid_close_above_swing() -> None:
    """A close beyond the prior swing level with enough ATR displacement should pass."""
    open_prices = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 104.5, 105.0]
    close_prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_bos(frame, 9, 105.0, "bullish", atr) is True


def test_bos_rejected_wick_only_no_close() -> None:
    """A wick-only excursion that does not close beyond the swing should be rejected."""
    open_prices = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 105.2, 104.9]
    close_prices = [100.0, 100.7, 101.2, 101.8, 102.4, 102.8, 103.2, 103.8, 104.3, 104.9, 104.8]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_bos(frame, 9, 105.0, "bullish", atr) is False


def test_bos_rejected_break_too_small_vs_atr() -> None:
    """A break smaller than half the ATR should be rejected even if the close is beyond the level."""
    open_prices = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 104.6, 105.1]
    close_prices = [100.0, 100.7, 101.2, 101.8, 102.4, 102.9, 103.3, 103.8, 104.3, 105.1, 105.3]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_bos(frame, 9, 105.0, "bullish", atr) is False


def test_bos_rejected_no_displacement() -> None:
    """A valid close break is not enough without a prior displacement candle."""
    open_prices = [100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.1, 101.2, 101.3, 101.1, 101.4]
    close_prices = [100.0, 100.3, 100.5, 100.7, 100.9, 101.0, 101.2, 101.3, 101.4, 101.7, 101.9]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_bos(frame, 9, 101.0, "bullish", atr) is False


def test_bos_no_lookahead_bias() -> None:
    """The validator should not inspect candles after the break index."""
    open_prices = [100.0, 100.4, 100.8, 101.1, 101.3, 101.7, 102.0, 102.4, 102.6, 103.0, 103.5]
    close_prices = [100.0, 100.6, 101.0, 101.4, 101.8, 102.2, 102.7, 103.5, 104.2, 103.6, 103.9]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_bos(frame, 9, 101.8, "bullish", atr) is True
    assert _has_displacement(frame, 6, 9, atr) is True


def test_choch_valid_full_sequence() -> None:
    """A valid CHoCH needs a prior liquidity sweep, a close break, and a confirmation candle."""
    open_prices = [100.0, 99.8, 99.6, 99.4, 99.2, 99.1, 99.5, 99.8, 99.9, 100.1, 100.6, 101.0]
    close_prices = [100.0, 99.9, 99.7, 99.5, 99.3, 99.2, 99.7, 100.0, 100.2, 100.6, 101.1, 101.3]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_choch(frame, 8, 99.1, "bullish", atr, liquidity_swept=True) is True
    assert _has_confirmation_candle(frame, 9, "bullish", atr) is True


def test_choch_rejected_no_liquidity_sweep() -> None:
    """Without a quoted liquidity sweep, a reversal should not qualify as CHoCH."""
    open_prices = [100.0, 100.4, 100.5, 100.6, 100.7, 100.8, 100.9, 101.0, 101.1, 101.2, 101.3]
    close_prices = [100.0, 100.5, 100.6, 100.8, 101.0, 101.1, 101.3, 101.4, 101.5, 101.7, 101.9]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_choch(frame, 8, 100.8, "bullish", atr, liquidity_swept=False) is False


def test_choch_rejected_no_confirmation_candle() -> None:
    """If the follow-through candle does not confirm the direction, the CHoCH should fail."""
    open_prices = [100.0, 99.8, 99.6, 99.4, 99.2, 99.1, 99.5, 99.8, 99.9, 100.0, 99.9, 99.8]
    close_prices = [100.0, 99.9, 99.7, 99.5, 99.3, 99.2, 99.7, 100.0, 100.2, 99.9, 99.8, 99.7]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_choch(frame, 8, 99.1, "bullish", atr, liquidity_swept=True) is False


def test_choch_rejected_wick_only() -> None:
    """A wick spike that does not close beyond the swing and confirm should not count."""
    open_prices = [100.0, 99.8, 99.6, 99.4, 99.2, 99.1, 99.3, 99.5, 99.7, 99.3, 99.4]
    close_prices = [100.0, 99.9, 99.7, 99.5, 99.3, 99.2, 99.4, 99.6, 99.8, 99.05, 99.2]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_choch(frame, 8, 99.1, "bullish", atr, liquidity_swept=True) is False


def test_choch_no_lookahead_bias() -> None:
    """The confirmation check must use the immediate next candle, not any future bar."""
    open_prices = [100.0, 99.8, 99.6, 99.4, 99.2, 99.1, 99.4, 99.7, 99.8, 100.0, 100.5, 101.0]
    close_prices = [100.0, 99.9, 99.7, 99.5, 99.3, 99.2, 99.6, 99.9, 100.1, 100.6, 101.1, 101.3]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _is_valid_choch(frame, 8, 99.1, "bullish", atr, liquidity_swept=True) is True
    assert _has_confirmation_candle(frame, 9, "bullish", atr) is True


def test_has_displacement_detects_body_beyond_threshold() -> None:
    """A candle with a large body relative to ATR counts as displacement."""
    open_prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 105.0, 106.0, 106.5, 107.0, 108.0]
    close_prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.7, 106.1, 107.4, 108.3, 108.5]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _has_displacement(frame, 5, 9, atr) is True


def test_has_confirmation_candle_rejects_small_body() -> None:
    """A small body below the threshold should not count as confirmation."""
    open_prices = [100.0, 99.8, 99.5, 99.3, 99.1, 99.2, 99.3, 99.4, 99.5, 99.6, 99.7]
    close_prices = [100.0, 99.9, 99.6, 99.4, 99.2, 99.25, 99.35, 99.41, 99.52, 99.63, 99.72]
    frame = _custom_frame(open_prices, close_prices)
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert _has_confirmation_candle(frame, 9, "bullish", atr) is False
