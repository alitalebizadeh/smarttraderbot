from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["FairValueGap", "FVGMap"]


@dataclass(eq=True)
class FairValueGap:
    """A single Fair Value Gap (FVG) / imbalance zone.

    A Fair Value Gap is a 3-candle pattern where the middle candle moves so
    strongly that it leaves a price gap between the first and third candles.
    These zones act as magnets — price tends to return and fill them.

    3-candle pattern structure:
        - ``candle[i-2]`` → ``formation_candle_index``  (first candle)
        - ``candle[i-1]`` → ``middle_candle_index``     (displacement candle)
        - ``candle[i]``   → ``candle_index``            (gap confirmation candle)

    Zone boundaries:
        - **Bullish FVG**: ``gap_bottom = candle[i-2].high``,
          ``gap_top = candle[i].low``.  Acts as support on retest.
        - **Bearish FVG**: ``gap_bottom = candle[i].high``,
          ``gap_top = candle[i-2].low``.  Acts as resistance on retest.

    The ``equilibrium`` (50 % level) is a key intra-zone reaction reference.

    Attributes:
        fvg_id: Unique identifier, e.g. ``"FVG_BULL_XAUUSD_M1_101"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        fvg_type: ``"bullish"`` for a support gap, ``"bearish"`` for a
            resistance gap.
        candle_index: Zero-based DataFrame index of ``candle[i]`` — the third
            candle that confirmed the gap.  Must be >= 2.
        candle_time: UTC timestamp of ``candle[i]``.
        gap_top: Upper price boundary of the FVG zone.
        gap_bottom: Lower price boundary of the FVG zone.
        gap_size: Width of the gap — ``gap_top - gap_bottom`` (always positive).
        equilibrium: Midpoint of the zone — ``(gap_top + gap_bottom) / 2``.
        fill_status: Current fill state of the zone — ``"unfilled"``,
            ``"partial"``, or ``"filled"``.
        filled_at_time: UTC timestamp when the gap was fully filled, or
            ``None`` if not yet filled.
        fill_percentage: Fraction of the gap that has been filled, in
            ``[0.0, 1.0]``.
        is_valid: ``False`` when the gap size is too small to be significant
            (set by the engine based on minimum gap thresholds).
        formation_candle_index: Zero-based DataFrame index of ``candle[i-2]``
            (the first candle of the pattern).
        middle_candle_index: Zero-based DataFrame index of ``candle[i-1]``
            (the displacement candle in the middle of the pattern).
    """

    fvg_id: str
    symbol: str
    timeframe: str
    fvg_type: Literal["bullish", "bearish"]
    candle_index: int
    candle_time: datetime
    gap_top: float
    gap_bottom: float
    gap_size: float
    equilibrium: float
    fill_status: Literal["unfilled", "partial", "filled"] = field(
        default="unfilled"
    )
    filled_at_time: Optional[datetime] = field(default=None)
    fill_percentage: float = field(default=0.0)
    is_valid: bool = field(default=True)
    formation_candle_index: int = field(default=0)
    middle_candle_index: int = field(default=0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``gap_top`` must be > ``gap_bottom``.
                - ``gap_top`` must be > 0.
                - ``gap_bottom`` must be > 0.
                - ``gap_size`` must be > 0.
                - ``equilibrium`` must be in the range
                  ``[gap_bottom, gap_top]`` (inclusive).
                - ``fill_percentage`` must be in the range ``[0.0, 1.0]``
                  (inclusive).
                - ``candle_index`` must be >= 2.
                - ``formation_candle_index`` must be >= 0.
                - ``middle_candle_index`` must be >= 0.
                - When ``fill_status`` is ``"filled"``, ``filled_at_time``
                  must not be ``None``.
                - ``fvg_id`` must not be empty.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
        """
        if self.gap_top <= self.gap_bottom:
            raise ValueError(
                f"FairValueGap.gap_top ({self.gap_top}) must be > "
                f"gap_bottom ({self.gap_bottom})."
            )
        if self.gap_top <= 0:
            raise ValueError(
                f"FairValueGap.gap_top must be > 0, got {self.gap_top}."
            )
        if self.gap_bottom <= 0:
            raise ValueError(
                f"FairValueGap.gap_bottom must be > 0, got {self.gap_bottom}."
            )
        if self.gap_size <= 0:
            raise ValueError(
                f"FairValueGap.gap_size must be > 0, got {self.gap_size}."
            )
        if not (self.gap_bottom <= self.equilibrium <= self.gap_top):
            raise ValueError(
                f"FairValueGap.equilibrium ({self.equilibrium}) must be between "
                f"gap_bottom ({self.gap_bottom}) and gap_top ({self.gap_top}) "
                "inclusive."
            )
        if not (0.0 <= self.fill_percentage <= 1.0):
            raise ValueError(
                f"FairValueGap.fill_percentage must be between 0.0 and 1.0 "
                f"(inclusive), got {self.fill_percentage}."
            )
        if self.candle_index < 2:
            raise ValueError(
                f"FairValueGap.candle_index must be >= 2 (the FVG pattern "
                f"requires at least 3 candles), got {self.candle_index}."
            )
        if self.formation_candle_index < 0:
            raise ValueError(
                f"FairValueGap.formation_candle_index must be >= 0, "
                f"got {self.formation_candle_index}."
            )
        if self.middle_candle_index < 0:
            raise ValueError(
                f"FairValueGap.middle_candle_index must be >= 0, "
                f"got {self.middle_candle_index}."
            )
        if self.fill_status == "filled" and self.filled_at_time is None:
            raise ValueError(
                "FairValueGap.filled_at_time must not be None "
                "when fill_status is \"filled\"."
            )
        if not self.fvg_id:
            raise ValueError("FairValueGap.fvg_id must not be an empty string.")
        if not self.symbol:
            raise ValueError("FairValueGap.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError(
                "FairValueGap.timeframe must not be an empty string."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields are rounded to 6 decimal places.
        Ratio and percentage fields are rounded to 4 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "fvg_id": self.fvg_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "fvg_type": self.fvg_type,
            "candle_index": self.candle_index,
            "candle_time": self.candle_time.isoformat(),
            "gap_top": round(self.gap_top, 6),
            "gap_bottom": round(self.gap_bottom, 6),
            "gap_size": round(self.gap_size, 6),
            "equilibrium": round(self.equilibrium, 6),
            "fill_status": self.fill_status,
            "filled_at_time": (
                self.filled_at_time.isoformat()
                if self.filled_at_time is not None
                else None
            ),
            "fill_percentage": round(self.fill_percentage, 4),
            "is_valid": self.is_valid,
            "formation_candle_index": self.formation_candle_index,
            "middle_candle_index": self.middle_candle_index,
        }


@dataclass(eq=False)
class FVGMap:
    """Complete Fair Value Gap analysis result for one symbol and timeframe.

    Created by ``src/engine/fvg_engine.py`` and consumed by the POI engine,
    confluence engine, scanner, and dashboard.  Acts as the single source of
    truth for all FVG / imbalance data on a given instrument / timeframe
    combination.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Total number of candles that were analysed.
        bullish_fvgs: All active (unfilled / partial) bullish
            :class:`FairValueGap` objects in chronological order.
        bearish_fvgs: All active (unfilled / partial) bearish
            :class:`FairValueGap` objects in chronological order.
        filled_fvgs: All fully filled :class:`FairValueGap` objects kept for
            historical reference, in chronological order.
        last_bullish_fvg: The most recent unfilled bullish
            :class:`FairValueGap`, or ``None`` when none exist.
        last_bearish_fvg: The most recent unfilled bearish
            :class:`FairValueGap`, or ``None`` when none exist.
        total_count: Total number of FVGs detected across all categories
            (bullish + bearish + filled).
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    bullish_fvgs: list[FairValueGap] = field(default_factory=list)
    bearish_fvgs: list[FairValueGap] = field(default_factory=list)
    filled_fvgs: list[FairValueGap] = field(default_factory=list)
    last_bullish_fvg: Optional[FairValueGap] = field(default=None)
    last_bearish_fvg: Optional[FairValueGap] = field(default=None)
    total_count: int = field(default=0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candle_count`` must be >= 0.
                - ``total_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError("FVGMap.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("FVGMap.timeframe must not be an empty string.")
        if self.candle_count < 0:
            raise ValueError(
                f"FVGMap.candle_count must be >= 0, got {self.candle_count}."
            )
        if self.total_count < 0:
            raise ValueError(
                f"FVGMap.total_count must be >= 0, got {self.total_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`FairValueGap` objects are serialised via their own
        ``to_dict()`` methods.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "bullish_fvgs": [fvg.to_dict() for fvg in self.bullish_fvgs],
            "bearish_fvgs": [fvg.to_dict() for fvg in self.bearish_fvgs],
            "filled_fvgs": [fvg.to_dict() for fvg in self.filled_fvgs],
            "last_bullish_fvg": (
                self.last_bullish_fvg.to_dict()
                if self.last_bullish_fvg is not None
                else None
            ),
            "last_bearish_fvg": (
                self.last_bearish_fvg.to_dict()
                if self.last_bearish_fvg is not None
                else None
            ),
            "total_count": self.total_count,
        }