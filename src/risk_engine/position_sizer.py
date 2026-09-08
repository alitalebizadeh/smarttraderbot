from __future__ import annotations

from dataclasses import dataclass

from src.core.instrument_config import InstrumentConfig, get_instrument_config


@dataclass
class PositionSize:
    """Position sizing result expressed in account and pip terms."""

    symbol: str
    account_balance: float
    risk_pct: float
    risk_amount: float
    entry_price: float
    stop_loss: float
    pip_risk: float
    lot_size: float
    pip_value: float


def calculate_position_size(
    account_balance: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    pip_value: float,
    symbol: str,
    lot_size_precision: int | None = None,
    config: InstrumentConfig | None = None,
) -> PositionSize:
    """Calculate percentage-risk lot sizing using symbol-specific pip settings."""
    config = config or get_instrument_config(symbol)
    if account_balance <= 0:
        raise ValueError("account_balance must be positive")
    if risk_pct <= 0 or risk_pct > 10:
        raise ValueError("risk_pct must be greater than 0 and no more than 10")
    if entry_price == stop_loss:
        raise ValueError("entry_price and stop_loss must differ")
    if pip_value <= 0:
        raise ValueError("pip_value must be positive")
    risk_amount = account_balance * (risk_pct / 100.0)
    pip_risk = round(abs(entry_price - stop_loss) / config.pip_size, 10)
    precision = config.lot_precision if lot_size_precision is None else lot_size_precision
    lot_size = round(risk_amount / (pip_risk * pip_value), precision)
    return PositionSize(symbol, account_balance, risk_pct, risk_amount, entry_price, stop_loss, pip_risk, lot_size, pip_value)
