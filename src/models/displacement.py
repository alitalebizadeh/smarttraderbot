from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["DisplacementCandle", "Displacement", "DisplacementMap"]


@dataclass(eq=True)
class DisplacementCandle:
    """A single candle identified as a displacement candle.

    A displacement candle is driven by institutional order flow and is
    characterised by a large body relative to its total range and a range
    significantly larger than the recent average (ATR).

    Attributes:
        index: Zero-based candle index in the source DataFrame.
        time: UTC timestamp of the candle.
        open: Opening price of the candle.
        high: Highest price reached during the candle.
        low: Lowest price reached during the candle.
        close: Closing price of the candle.
        body_size: Absolute difference between close and open (``abs(close - open)``).
        total_range: Distance from high to low (``high - low``).
        body_ratio: Fraction of the total range occupied by the body
            (``body_size / total_range``), in the range ``[0.0, 1.0]``.
        direction: ``"bullish"`` when ``close > open``, ``"bearish"`` when
            ``close < open``.
        volume: Tick volume if available from the data source, otherwise ``None``.
        atr_ratio: Candle range divided by the ATR at the time of the candle.
            Values above ``1.5`` indicate a strong displacement.  Set by the
            engine after creation; defaults to ``0.0``.
    """

    index: int
    time: datetime
    open: float
    high: float
    low: float
    close: float
    body_size: float
    total_range: float
    body_ratio: float
    direction: Literal["bullish", "bearish"]
    volume: Optional[float] = field(default=None)
    atr_ratio: float = field(default=0.0)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``high`` must be >= ``low``.
                - ``high`` must be > 0.
                - ``open`` must be > 0.
                - ``close`` must be > 0.
                - ``body_size`` must be >= 0.
                - ``total_range`` must be > 0.
                - ``body_ratio`` must be in the range ``[0.0, 1.0]``.
                - ``atr_ratio`` must be >= 0.0.
                - ``index`` must be >= 0.
        """
        if self.high < self.low:
            raise ValueError(
                f"DisplacementCandle.high ({self.high}) must be >= low ({self.low})."
            )
        if self.high <= 0:
            raise ValueError(
                f"DisplacementCandle.high must be > 0, got {self.high}."
            )
        if self.open <= 0:
            raise ValueError(
                f"DisplacementCandle.open must be > 0, got {self.open}."
            )
        if self.close <= 0:
            raise ValueError(
                f"DisplacementCandle.close must be > 0, got {self.close}."
            )
        if self.body_size < 0:
            raise ValueError(
                f"DisplacementCandle.body_size must be >= 0, got {self.body_size}."
            )
        if self.total_range <= 0:
            raise ValueError(
                f"DisplacementCandle.total_range must be > 0, got {self.total_range}."
            )
        if not (0.0 <= self.body_ratio <= 1.0):
            raise ValueError(
                f"DisplacementCandle.body_ratio must be between 0.0 and 1.0 "
                f"(inclusive), got {self.body_ratio}."
            )
        if self.atr_ratio < 0.0:
            raise ValueError(
                f"DisplacementCandle.atr_ratio must be >= 0.0, got {self.atr_ratio}."
            )
        if self.index < 0:
            raise ValueError(
                f"DisplacementCandle.index must be >= 0, got {self.index}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields and ratios are rounded to 6 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        ``None`` optional fields are preserved as ``None``.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
        """
        return {
            "index": self.index,
            "time": self.time.isoformat(),
            "open": round(self.open, 6),
            "high": round(self.high, 6),
            "low": round(self.low, 6),
            "close": round(self.close, 6),
            "body_size": round(self.body_size, 6),
            "total_range": round(self.total_range, 6),
            "body_ratio": round(self.body_ratio, 6),
            "direction": self.direction,
            "volume": (
                round(self.volume, 6) if self.volume is not None else None
            ),
            "atr_ratio": round(self.atr_ratio, 6),
        }


@dataclass(eq=True)
class Displacement:
    """A confirmed institutional displacement move.

    A displacement is one or more consecutive :class:`DisplacementCandle` objects
    moving in the same direction that together form a single impulsive institutional
    impulse.  Displacements precede Order Block formation and often leave Fair
    Value Gaps (imbalances) behind.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        direction: ``"bullish"`` for an upward impulse, ``"bearish"`` for a
            downward impulse.
        candles: All :class:`DisplacementCandle` objects forming this move,
            ordered chronologically.  At least one candle is required.
        start_index: DataFrame index of the first candle in the displacement.
        end_index: DataFrame index of the last candle in the displacement.
        start_time: UTC timestamp of the first candle.
        end_time: UTC timestamp of the last candle.
        start_price: Open price of the first candle.
        end_price: Close price of the last candle.
        highest_high: Maximum high across all candles in the displacement.
        lowest_low: Minimum low across all candles in the displacement.
        total_range: ``highest_high - lowest_low``.
        avg_body_ratio: Mean ``body_ratio`` across all candles.
        avg_atr_ratio: Mean ``atr_ratio`` across all candles.
        left_fvg: ``True`` when the displacement left at least one Fair Value Gap.
        candle_count: Number of candles in the displacement.  Must equal
            ``len(candles)``.
    """

    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    candles: list[DisplacementCandle]
    start_index: int
    end_index: int
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    highest_high: float
    lowest_low: float
    total_range: float
    avg_body_ratio: float
    avg_atr_ratio: float
    left_fvg: bool = field(default=False)
    candle_count: int = field(default=1)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candles`` must not be empty.
                - ``end_index`` must be >= ``start_index``.
                - ``highest_high`` must be >= ``lowest_low``.
                - ``highest_high`` must be > 0.
                - ``total_range`` must be > 0.
                - ``avg_body_ratio`` must be in the range ``[0.0, 1.0]``.
                - ``avg_atr_ratio`` must be >= 0.0.
                - ``candle_count`` must equal ``len(candles)``.
        """
        if not self.symbol:
            raise ValueError("Displacement.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("Displacement.timeframe must not be an empty string.")
        if not self.candles:
            raise ValueError(
                "Displacement.candles must not be empty — at least one "
                "DisplacementCandle is required."
            )
        if self.end_index < self.start_index:
            raise ValueError(
                f"Displacement.end_index ({self.end_index}) must be >= "
                f"start_index ({self.start_index})."
            )
        if self.highest_high < self.lowest_low:
            raise ValueError(
                f"Displacement.highest_high ({self.highest_high}) must be >= "
                f"lowest_low ({self.lowest_low})."
            )
        if self.highest_high <= 0:
            raise ValueError(
                f"Displacement.highest_high must be > 0, got {self.highest_high}."
            )
        if self.total_range <= 0:
            raise ValueError(
                f"Displacement.total_range must be > 0, got {self.total_range}."
            )
        if not (0.0 <= self.avg_body_ratio <= 1.0):
            raise ValueError(
                f"Displacement.avg_body_ratio must be between 0.0 and 1.0 "
                f"(inclusive), got {self.avg_body_ratio}."
            )
        if self.avg_atr_ratio < 0.0:
            raise ValueError(
                f"Displacement.avg_atr_ratio must be >= 0.0, "
                f"got {self.avg_atr_ratio}."
            )
        if self.candle_count != len(self.candles):
            raise ValueError(
                f"Displacement.candle_count ({self.candle_count}) must equal "
                f"len(candles) ({len(self.candles)})."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Price fields and ratios are rounded to 6 decimal places.
        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`DisplacementCandle` objects are serialised via their
        own ``to_dict()`` methods.

        Returns:
            A JSON-serialisable dictionary of all fields.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "candles": [c.to_dict() for c in self.candles],
            "start_index": self.start_index,
            "end_index": self.end_index,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "start_price": round(self.start_price, 6),
            "end_price": round(self.end_price, 6),
            "highest_high": round(self.highest_high, 6),
            "lowest_low": round(self.lowest_low, 6),
            "total_range": round(self.total_range, 6),
            "avg_body_ratio": round(self.avg_body_ratio, 6),
            "avg_atr_ratio": round(self.avg_atr_ratio, 6),
            "left_fvg": self.left_fvg,
            "candle_count": self.candle_count,
        }


@dataclass(eq=False)
class DisplacementMap:
    """Complete displacement analysis result for one symbol and timeframe.

    Created by ``src/engine/displacement_engine.py`` and consumed by the
    Order Block engine, POI engine, and confluence engine.  Acts as the
    single source of truth for all displacement data on a given instrument /
    timeframe combination.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Total number of candles that were analysed.
        displacements: All :class:`Displacement` objects detected, in
            chronological order.
        bullish_count: Number of bullish displacements found.
        bearish_count: Number of bearish displacements found.
        last_displacement: The most recent :class:`Displacement`, or ``None``
            when no displacements were detected.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    displacements: list[Displacement] = field(default_factory=list)
    bullish_count: int = field(default=0)
    bearish_count: int = field(default=0)
    last_displacement: Optional[Displacement] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - ``candle_count`` must be >= 0.
                - ``bullish_count`` must be >= 0.
                - ``bearish_count`` must be >= 0.
        """
        if not self.symbol:
            raise ValueError("DisplacementMap.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError(
                "DisplacementMap.timeframe must not be an empty string."
            )
        if self.candle_count < 0:
            raise ValueError(
                f"DisplacementMap.candle_count must be >= 0, "
                f"got {self.candle_count}."
            )
        if self.bullish_count < 0:
            raise ValueError(
                f"DisplacementMap.bullish_count must be >= 0, "
                f"got {self.bullish_count}."
            )
        if self.bearish_count < 0:
            raise ValueError(
                f"DisplacementMap.bearish_count must be >= 0, "
                f"got {self.bearish_count}."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        ``datetime`` values are converted to ISO 8601 strings.
        Nested :class:`Displacement` objects are serialised via their own
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
            "displacements": [d.to_dict() for d in self.displacements],
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "last_displacement": (
                self.last_displacement.to_dict()
                if self.last_displacement is not None
                else None
            ),
        }