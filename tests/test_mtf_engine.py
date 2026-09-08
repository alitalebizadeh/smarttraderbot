from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from src.mtf_engine import (
    MarketBias,
    TimeframeManager,
    check_alignment,
    compute_bias,
)


def bias(direction: str, timeframe: str, strength: float = 80.0) -> MarketBias:
    return MarketBias(
        direction=direction,
        timeframe=timeframe,
        strength=strength,
        reason=f"{direction} test bias",
        timestamp=datetime.now(timezone.utc),
    )


def test_aligned_bullish_setup_is_accepted() -> None:
    result = TimeframeManager().analyze(
        {
            "D1": bias("bullish", "D1"),
            "H4": bias("bullish", "H4"),
            "H1": bias("bullish", "H1"),
            "M15": bias("bullish", "M15"),
            "M5": bias("bullish", "M5"),
        }
    )

    assert result.decision == "BUY"
    assert result.htf_bias.direction == "bullish"
    assert result.alignment_score == 100.0


def test_lower_timeframe_conflict_is_rejected() -> None:
    result = TimeframeManager().analyze(
        {
            "D1": bias("bearish", "D1"),
            "H4": bias("bearish", "H4"),
            "H1": bias("bearish", "H1"),
            "M15": bias("bullish", "M15"),
        }
    )

    assert result.decision == "WAIT"
    assert result.htf_bias.direction == "bearish"
    assert result.ltf_signal is not None
    assert result.counter_trend_warning is not None


def test_neutral_higher_timeframe_returns_wait() -> None:
    result = TimeframeManager().analyze(
        {
            "D1": bias("neutral", "D1", 0.0),
            "H4": bias("neutral", "H4", 0.0),
            "M15": bias("bullish", "M15"),
            "M5": bias("bullish", "M5"),
        }
    )

    assert result.htf_bias.direction == "neutral"
    assert result.decision == "WAIT"
    assert result.alignment_score == 0.0


def test_missing_timeframe_data_is_safe() -> None:
    result = TimeframeManager().analyze({"H4": bias("bullish", "H4")})

    assert result.decision == "WAIT"
    assert result.htf_bias.direction == "bullish"
    assert result.h4_h1_context["H4"].direction == "bullish"
    assert result.ltf_signal is None


def _event(direction: str, event_type: str, minute: int) -> SimpleNamespace:
    """Build a minimal causal structure event for bias tests."""
    return SimpleNamespace(
        direction=direction,
        event_type=event_type,
        break_candle_time=pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(minutes=minute),
    )


def test_bias_bullish_majority_bos() -> None:
    """A bullish majority produces bullish bias and normalized confidence."""
    result = compute_bias([_event("bullish", "BOS", 1), _event("bullish", "BOS", 2), _event("bearish", "CHoCH", 3)], "H1")
    assert result.direction == "bullish"
    assert result.bos_count == 2
    assert result.choch_count == 0
    assert result.confidence == 1 / 3


def test_bias_neutral_equal_events() -> None:
    """Equal bullish and bearish event counts produce neutral bias."""
    result = compute_bias([_event("bullish", "BOS", 1), _event("bearish", "BOS", 2)], "H1")
    assert result.direction == "neutral"
    assert result.confidence == 0.0


def test_alignment_both_bullish_returns_aligned() -> None:
    """Matching non-neutral bullish biases produce an aligned buy direction."""
    higher = compute_bias([_event("bullish", "BOS", 1)], "H4")
    lower = compute_bias([_event("bullish", "BOS", 2)], "M15")
    result = check_alignment(higher, lower, "XAUUSD")
    assert result.is_aligned is True
    assert result.trade_direction == "bullish"
    assert result.alignment_score == 1.0


def test_alignment_conflict_returns_no_trade() -> None:
    """Conflicting timeframe directions must produce no trade."""
    higher = compute_bias([_event("bullish", "BOS", 1)], "H4")
    lower = compute_bias([_event("bearish", "BOS", 2)], "M15")
    result = check_alignment(higher, lower, "XAUUSD")
    assert result.is_aligned is False
    assert result.trade_direction == "no_trade"
    assert result.alignment_score == 0.0


def test_higher_tf_neutral_forces_no_trade() -> None:
    """A neutral higher timeframe dominates a directional lower timeframe."""
    higher = compute_bias([], "H4")
    lower = compute_bias([_event("bullish", "BOS", 2)], "M15")
    result = check_alignment(higher, lower, "XAUUSD")
    assert result.trade_direction == "no_trade"
