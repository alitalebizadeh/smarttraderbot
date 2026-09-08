from datetime import datetime, timezone

import pytest

from src.decision_engine import DecisionEngine
from src.mtf_engine import MarketBias, TimeframeManager
from src.risk_engine import RiskCalculationError, RiskEngine


def _alignment():
    now = datetime.now(timezone.utc)
    return TimeframeManager().analyze(
        {
            timeframe: MarketBias("bullish", timeframe, 80.0, "confirmed", now)
            for timeframe in ("D1", "H4", "H1", "M15", "M5")
        }
    )


def test_decision_requires_all_confirmations() -> None:
    signal = DecisionEngine().evaluate(
        symbol="XAUUSD",
        timeframe="M5",
        alignment=_alignment(),
        liquidity_confirmed=True,
        structure_shift_confirmed=False,
        poi_confirmed=True,
        entry=100.0,
        stop_loss=99.0,
        take_profit=102.0,
    )

    assert signal.direction == "NO TRADE"
    assert any("market structure shift" in reason for reason in signal.reasoning)


def test_decision_accepts_valid_bullish_setup() -> None:
    signal = DecisionEngine().evaluate(
        symbol="XAUUSD",
        timeframe="M5",
        alignment=_alignment(),
        liquidity_confirmed=True,
        structure_shift_confirmed=True,
        poi_confirmed=True,
        entry=100.0,
        stop_loss=99.0,
        take_profit=102.0,
    )

    assert signal.direction == "BUY"
    assert signal.risk_reward == 2.0


def test_risk_engine_sizes_from_account_risk() -> None:
    size = RiskEngine().size_position(
        account_equity=10_000,
        entry=100,
        stop_loss=98,
        value_per_price_unit=1,
        units_per_lot=100,
    )

    assert size.risk_amount == 100
    assert size.quantity == 50
    assert size.lot_size == 0.5


def test_risk_engine_rejects_zero_stop_distance() -> None:
    with pytest.raises(RiskCalculationError):
        RiskEngine().size_position(
            account_equity=10_000,
            entry=100,
            stop_loss=100,
            value_per_price_unit=1,
        )
