from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

__all__ = ["MarketSnapshot"]


@dataclass
class MarketSnapshot:
    """Aggregated analysis state for one symbol / timeframe at a point in time.

    Assembled by :class:`~src.scanner.timeframe_scanner.TimeframeScanner`
    after all engines have run.  Consumed by the confluence engine, scoring
    layer, and dashboard.

    Attributes:
        snapshot_id: Unique ID — ``"SNAP_{symbol}_{timeframe}_{unix_ts}"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        captured_at: UTC timestamp when the snapshot was assembled.
        current_price: Most recent market price at snapshot time.
        candle_count: Number of candles used in the analysis.
        market_structure: Result from the market structure engine, or
            ``None`` on failure.
        liquidity: Result from the liquidity engine, or ``None``.
        displacement: Result from the displacement engine, or ``None``.
        order_blocks: Result from the order block engine, or ``None``.
        fvgs: Result from the FVG engine, or ``None``.
        supply_demand: Result from the supply/demand engine, or ``None``.
        pois: Result from the POI engine, or ``None``.
        engines_run: Names of engines that completed successfully.
        engines_failed: Names of engines that raised an exception.
        scan_duration_ms: Wall-clock milliseconds for the full pipeline.
        is_complete: ``True`` when no engines failed.
    """

    snapshot_id: str
    symbol: str
    timeframe: str
    captured_at: datetime
    current_price: float
    candle_count: int
    market_structure: Optional[Any] = field(default=None)
    liquidity: Optional[Any] = field(default=None)
    displacement: Optional[Any] = field(default=None)
    order_blocks: Optional[Any] = field(default=None)
    fvgs: Optional[Any] = field(default=None)
    supply_demand: Optional[Any] = field(default=None)
    pois: Optional[Any] = field(default=None)
    cluster_map: Optional[Any] = field(default=None)
    entry_map: Optional[Any] = field(default=None)
    df: Any = field(default=None)  # Source OHLCV DataFrame
    engines_run: list[str] = field(default_factory=list)
    engines_failed: list[str] = field(default_factory=list)
    scan_duration_ms: float = field(default=0.0)
    is_complete: bool = field(default=True)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of scalar fields.  Engine result
            objects are represented by their class name or ``None``.
        """
        def _name(obj: Any) -> Optional[str]:
            return type(obj).__name__ if obj is not None else None

        return {
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "captured_at": self.captured_at.isoformat(),
            "current_price": round(self.current_price, 6),
            "candle_count": self.candle_count,
            "market_structure": _name(self.market_structure),
            "liquidity": _name(self.liquidity),
            "displacement": _name(self.displacement),
            "order_blocks": _name(self.order_blocks),
            "fvgs": _name(self.fvgs),
            "supply_demand": _name(self.supply_demand),
            "pois": _name(self.pois),
            "cluster_map": _name(self.cluster_map),
            "entry_map": _name(self.entry_map),
            "engines_run": self.engines_run,
            "engines_failed": self.engines_failed,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "is_complete": self.is_complete,
        }