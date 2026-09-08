import pytest

from src.core.instrument_config import get_instrument_config
from src.risk_engine.position_sizer import calculate_position_size


def test_xauusd_config_returns_correct_pip_size() -> None:
    """XAUUSD uses a hundredth price pip."""
    assert get_instrument_config("XAUUSD").pip_size == 0.01


def test_eurusd_config_returns_correct_pip_size() -> None:
    """EURUSD uses a ten-thousandth price pip."""
    assert get_instrument_config("EURUSD").pip_size == 0.0001


def test_unknown_symbol_raises_key_error() -> None:
    """Unknown symbols fail with an explicit configuration error."""
    with pytest.raises(KeyError, match="Unknown instrument"):
        get_instrument_config("UNKNOWN")


def test_position_size_uses_instrument_pip_size() -> None:
    """Position sizing converts the same price distance differently by instrument."""
    xau = calculate_position_size(10000.0, 1.0, 100.0, 99.0, 10.0, "XAUUSD")
    eur = calculate_position_size(10000.0, 1.0, 1.1000, 1.0990, 10.0, "EURUSD")
    assert xau.pip_risk == 100.0
    assert eur.pip_risk == 10.0
