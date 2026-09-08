from __future__ import annotations

from dataclasses import dataclass
from math import floor


class RiskCalculationError(ValueError):
    """Raised when a position cannot be sized safely."""


@dataclass(frozen=True)
class RiskConfig:
    risk_fraction: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    def __post_init__(self) -> None:
        if not 0 < self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        if not 0 < self.min_lot <= self.max_lot:
            raise ValueError("lot limits are invalid")
        if self.lot_step <= 0:
            raise ValueError("lot_step must be positive")


@dataclass(frozen=True)
class PositionSize:
    risk_amount: float
    stop_distance: float
    quantity: float
    lot_size: float


class RiskEngine:
    """Calculate position size from account risk and instrument economics."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def size_position(
        self,
        *,
        account_equity: float,
        entry: float,
        stop_loss: float,
        value_per_price_unit: float,
        units_per_lot: float = 1.0,
    ) -> PositionSize:
        if account_equity <= 0 or entry <= 0 or stop_loss <= 0:
            raise RiskCalculationError("equity and prices must be positive")
        if value_per_price_unit <= 0 or units_per_lot <= 0:
            raise RiskCalculationError("instrument economics must be positive")
        stop_distance = abs(entry - stop_loss)
        if stop_distance == 0:
            raise RiskCalculationError("stop loss must differ from entry")
        risk_amount = account_equity * self.config.risk_fraction
        quantity = risk_amount / (stop_distance * value_per_price_unit)
        raw_lot = quantity / units_per_lot
        step_count = floor((raw_lot / self.config.lot_step) + 1e-9)
        stepped_lot = step_count * self.config.lot_step
        lot_size = min(self.config.max_lot, max(self.config.min_lot, stepped_lot))
        return PositionSize(
            risk_amount=risk_amount,
            stop_distance=stop_distance,
            quantity=quantity,
            lot_size=round(lot_size, 8),
        )
