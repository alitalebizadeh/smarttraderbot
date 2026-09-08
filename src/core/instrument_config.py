from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentConfig:
    """Instrument-specific price and lot conventions."""

    symbol: str
    pip_size: float
    pip_value_per_lot: float
    min_lot: float
    max_lot: float
    lot_precision: int


INSTRUMENT_CONFIGS: dict[str, InstrumentConfig] = {
    "XAUUSD": InstrumentConfig("XAUUSD", 0.01, 1.0, 0.01, 100.0, 2),
    "EURUSD": InstrumentConfig("EURUSD", 0.0001, 10.0, 0.01, 100.0, 2),
    "GBPUSD": InstrumentConfig("GBPUSD", 0.0001, 10.0, 0.01, 100.0, 2),
}


def get_instrument_config(symbol: str) -> InstrumentConfig:
    """Return configuration for a known symbol or raise a clear KeyError."""
    try:
        return INSTRUMENT_CONFIGS[symbol.upper()]
    except KeyError as exc:
        raise KeyError(f"Unknown instrument symbol: {symbol}") from exc
