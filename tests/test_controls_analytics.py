from datetime import datetime, time, timezone

import pandas as pd
import pytest

from src.analytics import MonteCarloAnalyzer, chronological_split, classify_regime
from src.decision_engine import NewsEvent, NewsFilter, SessionFilter


def test_session_and_high_impact_news_filters() -> None:
    timestamp = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
    assert SessionFilter().session_at(timestamp) == "london"
    event = NewsEvent("CPI", datetime(2024, 1, 1, 8, 15, tzinfo=timezone.utc), "high")
    assert NewsFilter(before_minutes=30, after_minutes=30).blocks(timestamp, [event])


def test_chronological_split_keeps_test_data_last() -> None:
    split = chronological_split(list(range(10)))
    assert split.training == tuple(range(6))
    assert split.validation == (6, 7)
    assert split.testing == (8, 9)


def test_monte_carlo_is_reproducible_with_seed() -> None:
    analyzer = MonteCarloAnalyzer()
    first = analyzer.simulate([2.0, -1.0, 3.0], initial_equity=10.0, simulations=20, seed=7)
    second = analyzer.simulate([2.0, -1.0, 3.0], initial_equity=10.0, simulations=20, seed=7)
    assert first == second


def test_regime_classifier_identifies_trend() -> None:
    close = [100 + index * 0.5 for index in range(25)]
    frame = pd.DataFrame({"close": close})
    assert classify_regime(frame) == "trending"
