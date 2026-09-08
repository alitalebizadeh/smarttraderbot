from types import SimpleNamespace

import pandas as pd

from src.database.repository import TradeRepository


def _signal(symbol: str = "XAUUSD") -> SimpleNamespace:
    """Create a synthetic setup for repository tests."""
    return SimpleNamespace(
        signal_id="setup-1", symbol=symbol, direction="buy", formed_at=pd.Timestamp("2024-01-01", tz="UTC"),
        entry_price=100.0, stop_loss=99.0, take_profit_1=102.0, take_profit_2=103.0,
        confidence=0.8, reasoning=["test"],
        mtf_alignment=SimpleNamespace(higher_tf_bias=SimpleNamespace(timeframe="H4")),
        ob_used=SimpleNamespace(score=100.0), fvg_used=SimpleNamespace(score=60.0),
    )


def _trade(symbol: str = "XAUUSD") -> SimpleNamespace:
    """Create a synthetic batch replay result."""
    signal = _signal(symbol)
    signal.signal_id = "setup-1" if symbol == "XAUUSD" else "setup-2"
    return SimpleNamespace(
        trade_id="trade-1", signal=signal, entry_time=pd.Timestamp("2024-01-01 00:05", tz="UTC"),
        exit_time=pd.Timestamp("2024-01-01 00:10", tz="UTC"), exit_price=102.0,
        exit_reason="tp1", pnl_pips=200.0, pnl_pct=2.0, rr_achieved=2.0,
    )


def test_setup_saved_and_retrieved() -> None:
    """Saved setup rows are returned with their stable setup ID."""
    repo = TradeRepository(":memory:")
    assert repo.save_setup(_signal()) == "setup-1"
    assert repo.get_all_setups()[0]["symbol"] == "XAUUSD"
    repo.close()


def test_result_saved_and_retrieved() -> None:
    """Saved results are retrievable through symbol filtering."""
    repo = TradeRepository(":memory:")
    repo.save_setup(_signal())
    repo.save_result(_trade())
    assert len(repo.get_results_by_symbol("XAUUSD")) == 1
    repo.close()


def test_get_results_by_symbol_filters_correctly() -> None:
    """Symbol filtering excludes results from other setup symbols."""
    repo = TradeRepository(":memory:")
    repo.save_setup(_signal("XAUUSD"))
    repo.save_result(_trade("XAUUSD"))
    other = _signal("EURUSD")
    other.signal_id = "setup-2"
    repo.save_setup(other)
    repo.save_result(_trade("EURUSD"))
    assert len(repo.get_results_by_symbol("XAUUSD")) == 1
    repo.close()


def test_duplicate_setup_id_handled() -> None:
    """Saving the same setup ID twice is idempotent."""
    repo = TradeRepository(":memory:")
    assert repo.save_setup(_signal()) == repo.save_setup(_signal())
    assert len(repo.get_all_setups()) == 1
    repo.close()


def test_db_closes_without_error() -> None:
    """The repository connection can be closed cleanly."""
    repo = TradeRepository(":memory:")
    repo.close()
