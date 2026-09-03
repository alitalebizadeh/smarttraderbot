from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

__all__ = ["SymbolTimeframePair", "TimeframeScanResult"]


@dataclass(eq=True)
class SymbolTimeframePair:
    """A symbol + timeframe combination to be scanned.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        display_name: Human-readable label, e.g. ``"XAUUSD M1"``.
    """

    symbol: str
    timeframe: str
    display_name: str = field(default="")

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = f"{self.symbol} {self.timeframe}"


@dataclass
class TimeframeScanResult:
    """The output of a single symbol / timeframe scan.

    Produced by :class:`~src.scanner.timeframe_scanner.TimeframeScanner`
    and collected by the market scanner.

    Attributes:
        symbol: Instrument name.
        timeframe: Timeframe label.
        display_name: Human-readable label.
        success: ``True`` when the pipeline completed without a fatal error.
        scanned_at: UTC timestamp when the scan finished.
        scan_duration_ms: Wall-clock scan time in milliseconds.
        snapshot: The :class:`~src.models.market_snapshot.MarketSnapshot`
            assembled during the scan, or ``None`` on fatal failure.
        scoring_output: The :class:`~src.models.scoring.ScoringOutput`
            produced by the scorer, or ``None`` on failure.
        error_message: Description of the fatal error, or ``None``.
    """

    symbol: str
    timeframe: str
    display_name: str
    success: bool
    scanned_at: datetime
    scan_duration_ms: float
    snapshot: Optional[object] = field(default=None)
    scoring_output: Optional[object] = field(default=None)
    entry_map: Optional[object] = field(default=None)
    error_message: Optional[str] = field(default=None)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.  Nested objects
            are serialised via their own ``to_dict()`` when available.
        """
        def _safe_dict(obj: object) -> Optional[dict]:
            if obj is None:
                return None
            if hasattr(obj, "to_dict"):
                return obj.to_dict()  # type: ignore[return-value]
            return None

        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "display_name": self.display_name,
            "success": self.success,
            "scanned_at": self.scanned_at.isoformat(),
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "snapshot": _safe_dict(self.snapshot),
            "scoring_output": _safe_dict(self.scoring_output),
            "entry_map": _safe_dict(self.entry_map),
            "error_message": self.error_message,
        }