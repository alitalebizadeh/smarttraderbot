import pandas as pd

from src.liquidity_engine.levels import LiquidityLevel
from src.liquidity_engine.sweep_detector import LiquiditySweep
from src.smc_engine.fvg import (
    FairValueGap,
    _calculate_fvg_score,
    _classify_fill_status,
    _is_inverted,
    detect_fvgs,
)
from src.smc_engine.order_block import (
    OrderBlock,
    _calculate_ob_score,
    _is_fresh,
    _is_mitigated,
    detect_order_blocks,
)


def _frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    """Create a UTC-indexed synthetic OHLC frame."""
    data = pd.DataFrame(rows)
    data.index = pd.date_range("2024-01-01", periods=len(data), freq="5min", tz="UTC")
    return data.astype(float)


def _sweep(index: int = 0) -> LiquiditySweep:
    """Create a prior confirmed liquidity sweep for OB tests."""
    level = LiquidityLevel("PDH", 100.0, pd.Timestamp("2024-01-01", tz="UTC"))
    return LiquiditySweep(level, index, level.formed_at, True, index + 1, 1.0, 1.0)


def test_ob_valid_all_conditions_met() -> None:
    """A prior sweep, displacement, BOS, and untouched zone produce a valid OB."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.5, "close": 99.5},
        {"open": 99.5, "high": 100.0, "low": 98.8, "close": 99.0},
        {"open": 100.2, "high": 100.5, "low": 100.1, "close": 100.4},
        {"open": 100.2, "high": 103.0, "low": 100.1, "close": 102.0},
        {"open": 102.0, "high": 103.5, "low": 101.8, "close": 103.0},
        {"open": 103.0, "high": 104.0, "low": 102.8, "close": 103.8},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    blocks = detect_order_blocks(frame, atr, [_sweep()], "bullish")
    assert len(blocks) == 1
    assert blocks[0].liquidity_swept is True
    assert blocks[0].displacement_confirmed is True
    assert blocks[0].bos_confirmed is True
    assert blocks[0].is_fresh is True
    assert blocks[0].score == 100.0


def test_ob_rejected_no_liquidity_sweep() -> None:
    """An otherwise strong setup is rejected when no sweep precedes the OB."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.5, "close": 99.5},
        {"open": 99.5, "high": 100.0, "low": 98.8, "close": 99.0},
        {"open": 99.0, "high": 103.0, "low": 98.8, "close": 102.0},
        {"open": 102.0, "high": 104.0, "low": 101.8, "close": 103.8},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert detect_order_blocks(frame, atr, [], "bullish") == []


def test_ob_rejected_no_displacement() -> None:
    """A prior sweep without a qualifying displacement candle is rejected."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.5, "close": 99.5},
        {"open": 99.5, "high": 100.0, "low": 98.8, "close": 99.0},
        {"open": 99.0, "high": 99.8, "low": 98.8, "close": 99.4},
        {"open": 99.4, "high": 100.2, "low": 99.0, "close": 99.8},
        {"open": 99.8, "high": 100.3, "low": 99.4, "close": 100.0},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert detect_order_blocks(frame, atr, [_sweep()], "bullish") == []


def test_ob_rejected_no_bos() -> None:
    """A displacement without a later close break is not a valid order block."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.5, "close": 99.5},
        {"open": 99.5, "high": 100.0, "low": 98.8, "close": 99.0},
        {"open": 99.0, "high": 103.0, "low": 98.8, "close": 102.0},
        {"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.2},
        {"open": 102.2, "high": 102.5, "low": 101.9, "close": 102.3},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert detect_order_blocks(frame, atr, [_sweep()], "bullish") == []


def test_ob_mitigated_score_penalty() -> None:
    """A return close inside the zone marks mitigation and applies the score penalty."""
    assert _calculate_ob_score(True, True, True, True, True) == 50.0
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.5, "close": 99.5},
        {"open": 99.5, "high": 100.0, "low": 98.8, "close": 99.0},
        {"open": 99.0, "high": 103.0, "low": 98.8, "close": 102.0},
        {"open": 102.0, "high": 103.5, "low": 98.9, "close": 99.2},
    ])
    assert _is_mitigated(frame, 100.0, 98.8, 1) is True
    assert _is_fresh(frame, 100.0, 98.8, 1) is False


def test_fvg_valid_above_atr_threshold() -> None:
    """A three-candle bullish gap larger than 0.3 ATR is detected and scored."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.6, "high": 103.0, "low": 99.5, "close": 102.5},
        {"open": 102.5, "high": 103.5, "low": 101.0, "close": 103.0},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    gaps = detect_fvgs(frame, atr, "bullish")
    assert len(gaps) == 1
    assert gaps[0].gap_size == 1.0
    assert gaps[0].fill_status == "none"


def test_fvg_rejected_too_small() -> None:
    """A gap no larger than 0.3 ATR is rejected."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.6, "high": 101.0, "low": 99.5, "close": 100.8},
        {"open": 100.8, "high": 101.5, "low": 100.2, "close": 101.0},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    assert detect_fvgs(frame, atr, "bullish") == []


def test_fvg_partial_fill_detected() -> None:
    """A later candle entering but not crossing the gap marks a partial fill."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.6, "high": 103.0, "low": 99.5, "close": 102.5},
        {"open": 102.5, "high": 103.5, "low": 101.0, "close": 103.0},
        {"open": 103.0, "high": 103.2, "low": 100.5, "close": 102.0},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    gaps = detect_fvgs(frame, atr, "bullish")
    assert gaps[0].fill_status == "partial"


def test_fvg_inversion_detected() -> None:
    """A fully filled bullish gap followed by rejection above its lower edge is inverted."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.6, "high": 103.0, "low": 99.5, "close": 102.5},
        {"open": 102.5, "high": 103.5, "low": 101.0, "close": 103.0},
        {"open": 103.0, "high": 103.2, "low": 100.5, "close": 99.8},
        {"open": 100.8, "high": 102.0, "low": 100.7, "close": 101.5},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    gaps = detect_fvgs(frame, atr, "bullish")
    assert gaps[0].fill_status == "full"
    assert gaps[0].is_inverted is True


def test_fvg_no_lookahead_bias() -> None:
    """A gap formed at the end of known data is not filled by absent future candles."""
    frame = _frame([
        {"open": 99.0, "high": 100.0, "low": 98.8, "close": 99.5},
        {"open": 99.6, "high": 103.0, "low": 99.5, "close": 102.5},
        {"open": 102.5, "high": 103.5, "low": 101.0, "close": 103.0},
    ])
    atr = pd.Series([1.0] * len(frame), dtype=float)
    gaps = detect_fvgs(frame, atr, "bullish")
    assert gaps[0].fill_status == "none"
    assert _classify_fill_status(frame, 101.0, 100.0, 1) == "none"
    assert _calculate_fvg_score(1.2, "none", True, True) == 100.0
