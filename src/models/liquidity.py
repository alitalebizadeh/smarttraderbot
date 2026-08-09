from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

__all__ = ["LiquidityLevel", "EqualHighLow", "LiquiditySweep", "LiquidityMap"]


@dataclass(eq=True)
class LiquidityLevel:
    """A single price level where resting liquidity (stop orders) is accumulated.

    In ICT methodology, liquidity rests above Swing Highs (Buy-Side Liquidity / BSL)
    and below Swing Lows (Sell-Side Liquidity / SSL).  Price tends to seek these
    levels before reversing.

    Attributes:
        level_id: Unique identifier for this level, e.g. ``"BSL_XAUUSD_M1_42"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        price: Exact price at which liquidity is resting.
        level_type: ``"BSL"`` for Buy-Side Liquidity (above highs),
            ``"SSL"`` for Sell-Side Liquidity (below lows).
        candle_index: Zero-based index of the candle that created this level.
        candle_time: UTC timestamp of that candle.
        touch_count: Number of times price has tested this level (minimum 1).
        is_swept: ``True`` when price has already taken this liquidity.
        swept_at_time: UTC timestamp of the sweep event, or ``None`` if not yet swept.
    """

    level_id: str
    symbol: str
    timeframe: str
    price: float
    level_type: Literal["BSL", "SSL"]
    candle_index: int
    candle_time: datetime
    touch_count: int = field(default=1)
    is_swept: bool = field(default=False)
    swept_at_time: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``price`` must be > 0.
                - ``touch_count`` must be >= 1.
                - ``candle_index`` must be >= 0.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - When ``is_swept`` is ``True``, ``swept_at_time`` must not be ``None``.
        """
        if self.price <= 0:
            raise ValueError(
                f"LiquidityLevel.price must be > 0, got {self.price}."
            )
        if self.touch_count < 1:
            raise ValueError(
                f"LiquidityLevel.touch_count must be >= 1, got {self.touch_count}."
            )
        if self.candle_index < 0:
            raise ValueError(
                f"LiquidityLevel.candle_index must be >= 0, got {self.candle_index}."
            )
        if not self.symbol:
            raise ValueError("LiquidityLevel.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("LiquidityLevel.timeframe must not be an empty string.")
        if self.is_swept and self.swept_at_time is None:
            raise ValueError(
                "LiquidityLevel.swept_at_time must not be None when is_swept is True."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat dictionary with all fields serialised to JSON-safe types.
            ``datetime`` values are converted to ISO 8601 strings.
            ``None`` optional fields are preserved as ``None``.
        """
        return {
            "level_id": self.level_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": self.price,
            "level_type": self.level_type,
            "candle_index": self.candle_index,
            "candle_time": self.candle_time.isoformat(),
            "touch_count": self.touch_count,
            "is_swept": self.is_swept,
            "swept_at_time": (
                self.swept_at_time.isoformat()
                if self.swept_at_time is not None
                else None
            ),
        }


@dataclass(eq=True)
class EqualHighLow:
    """A cluster of Equal Highs (EQH) or Equal Lows (EQL).

    Equal Highs / Lows form when price tests the same price level multiple times
    within a configurable tolerance, creating a dense pocket of stop orders.
    In ICT methodology these are high-probability liquidity targets.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        price: Average price of all touches in the cluster.
        level_type: ``"EQH"`` for Equal Highs, ``"EQL"`` for Equal Lows.
        touch_count: Number of touches that formed the cluster (minimum 2).
        first_touch_time: UTC timestamp of the first touch.
        last_touch_time: UTC timestamp of the most recent touch.
        tolerance_pct: Relative tolerance used to group touches,
            e.g. ``0.001`` represents 0.1 %.
        is_swept: ``True`` when price has already taken this liquidity cluster.
        swept_at_time: UTC timestamp of the sweep event, or ``None`` if not swept.
    """

    symbol: str
    timeframe: str
    price: float
    level_type: Literal["EQH", "EQL"]
    touch_count: int
    first_touch_time: datetime
    last_touch_time: datetime
    tolerance_pct: float
    is_swept: bool = field(default=False)
    swept_at_time: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``price`` must be > 0.
                - ``touch_count`` must be >= 2.
                - ``tolerance_pct`` must be > 0.
                - ``last_touch_time`` must be >= ``first_touch_time``.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
                - When ``is_swept`` is ``True``, ``swept_at_time`` must not be ``None``.
        """
        if self.price <= 0:
            raise ValueError(
                f"EqualHighLow.price must be > 0, got {self.price}."
            )
        if self.touch_count < 2:
            raise ValueError(
                f"EqualHighLow.touch_count must be >= 2 (EQH/EQL requires at least "
                f"2 touches), got {self.touch_count}."
            )
        if self.tolerance_pct <= 0:
            raise ValueError(
                f"EqualHighLow.tolerance_pct must be > 0, got {self.tolerance_pct}."
            )
        if self.last_touch_time < self.first_touch_time:
            raise ValueError(
                f"EqualHighLow.last_touch_time ({self.last_touch_time.isoformat()}) "
                f"must be >= first_touch_time ({self.first_touch_time.isoformat()})."
            )
        if not self.symbol:
            raise ValueError("EqualHighLow.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("EqualHighLow.timeframe must not be an empty string.")
        if self.is_swept and self.swept_at_time is None:
            raise ValueError(
                "EqualHighLow.swept_at_time must not be None when is_swept is True."
            )

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat dictionary with all fields serialised to JSON-safe types.
            ``datetime`` values are converted to ISO 8601 strings.
            ``None`` optional fields are preserved as ``None``.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": self.price,
            "level_type": self.level_type,
            "touch_count": self.touch_count,
            "first_touch_time": self.first_touch_time.isoformat(),
            "last_touch_time": self.last_touch_time.isoformat(),
            "tolerance_pct": self.tolerance_pct,
            "is_swept": self.is_swept,
            "swept_at_time": (
                self.swept_at_time.isoformat()
                if self.swept_at_time is not None
                else None
            ),
        }


@dataclass(eq=True)
class LiquiditySweep:
    """A confirmed liquidity sweep event.

    A sweep occurs when price aggressively takes out a liquidity level — hunting
    retail stop losses — before reversing.  The key confirmation is that the sweep
    candle's wick penetrates the level while its body closes back on the other side
    (``returned_inside=True``).

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        sweep_type: ``"BSL_sweep"`` when buy-side liquidity was taken (potential
            bearish reversal); ``"SSL_sweep"`` when sell-side liquidity was taken
            (potential bullish reversal).
        swept_level: The :class:`LiquidityLevel` that was consumed by this sweep.
        sweep_candle_index: Zero-based index of the candle that performed the sweep.
        sweep_candle_time: UTC timestamp of the sweep candle.
        sweep_high: Highest price reached during the sweep candle.
        sweep_low: Lowest price reached during the sweep candle.
        close_price: Closing price of the sweep candle.
        returned_inside: ``True`` when the close price returned back inside the
            pre-sweep range — the primary confirmation of a true liquidity sweep.
        imbalance_left: ``True`` when the sweep candle left a Fair Value Gap /
            imbalance behind it.
    """

    symbol: str
    timeframe: str
    sweep_type: Literal["BSL_sweep", "SSL_sweep"]
    swept_level: LiquidityLevel
    sweep_candle_index: int
    sweep_candle_time: datetime
    sweep_high: float
    sweep_low: float
    close_price: float
    returned_inside: bool
    imbalance_left: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``sweep_high`` must be > ``sweep_low``.
                - ``sweep_high`` must be > 0.
                - ``close_price`` must be > 0.
                - ``sweep_candle_index`` must be strictly greater than
                  ``swept_level.candle_index``.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
        """
        if self.sweep_high <= self.sweep_low:
            raise ValueError(
                f"LiquiditySweep.sweep_high ({self.sweep_high}) must be > "
                f"sweep_low ({self.sweep_low})."
            )
        if self.sweep_high <= 0:
            raise ValueError(
                f"LiquiditySweep.sweep_high must be > 0, got {self.sweep_high}."
            )
        if self.close_price <= 0:
            raise ValueError(
                f"LiquiditySweep.close_price must be > 0, got {self.close_price}."
            )
        if self.sweep_candle_index <= self.swept_level.candle_index:
            raise ValueError(
                f"LiquiditySweep.sweep_candle_index ({self.sweep_candle_index}) "
                f"must be > swept_level.candle_index ({self.swept_level.candle_index}). "
                "The sweep must occur after the level was created."
            )
        if not self.symbol:
            raise ValueError("LiquiditySweep.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("LiquiditySweep.timeframe must not be an empty string.")

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A dictionary with all fields serialised to JSON-safe types.
            ``datetime`` values are converted to ISO 8601 strings.
            The nested ``swept_level`` is serialised via its own ``to_dict()``.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "sweep_type": self.sweep_type,
            "swept_level": self.swept_level.to_dict(),
            "sweep_candle_index": self.sweep_candle_index,
            "sweep_candle_time": self.sweep_candle_time.isoformat(),
            "sweep_high": self.sweep_high,
            "sweep_low": self.sweep_low,
            "close_price": self.close_price,
            "returned_inside": self.returned_inside,
            "imbalance_left": self.imbalance_left,
        }


@dataclass(eq=False)
class LiquidityMap:
    """The complete liquidity picture for one symbol and timeframe.

    Created by ``src/engine/liquidity_engine.py`` and consumed by the POI engine,
    confluence engine, scanner, and dashboard.  Acts as the single source of truth
    for all liquidity data on a given instrument / timeframe combination.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``, ``"H4"``.
        analyzed_at: UTC timestamp when the analysis was executed.
        candle_count: Number of candles that were analysed.
        bsl_levels: All active Buy-Side Liquidity levels, chronological.
        ssl_levels: All active Sell-Side Liquidity levels, chronological.
        equal_highs: All Equal High clusters detected.
        equal_lows: All Equal Low clusters detected.
        sweeps: All liquidity sweep events detected, chronological.
        recent_sweep: The most recent :class:`LiquiditySweep`, or ``None``.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    bsl_levels: list[LiquidityLevel] = field(default_factory=list)
    ssl_levels: list[LiquidityLevel] = field(default_factory=list)
    equal_highs: list[EqualHighLow] = field(default_factory=list)
    equal_lows: list[EqualHighLow] = field(default_factory=list)
    sweeps: list[LiquiditySweep] = field(default_factory=list)
    recent_sweep: Optional[LiquiditySweep] = field(default=None)

    def __post_init__(self) -> None:
        """Validate field values after initialisation.

        Raises:
            ValueError: If any of the following conditions are violated:

                - ``candle_count`` must be >= 0.
                - ``symbol`` must not be empty.
                - ``timeframe`` must not be empty.
        """
        if self.candle_count < 0:
            raise ValueError(
                f"LiquidityMap.candle_count must be >= 0, got {self.candle_count}."
            )
        if not self.symbol:
            raise ValueError("LiquidityMap.symbol must not be an empty string.")
        if not self.timeframe:
            raise ValueError("LiquidityMap.timeframe must not be an empty string.")

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A dictionary with all fields serialised to JSON-safe types.

            - ``datetime`` values → ISO 8601 strings.
            - Nested dataclasses → serialised via their own ``to_dict()``.
            - Lists of dataclasses → lists of dicts.
            - ``None`` optional fields → ``None`` (not omitted).
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "bsl_levels": [lv.to_dict() for lv in self.bsl_levels],
            "ssl_levels": [lv.to_dict() for lv in self.ssl_levels],
            "equal_highs": [eq.to_dict() for eq in self.equal_highs],
            "equal_lows": [eq.to_dict() for eq in self.equal_lows],
            "sweeps": [sw.to_dict() for sw in self.sweeps],
            "recent_sweep": (
                self.recent_sweep.to_dict()
                if self.recent_sweep is not None
                else None
            ),
        }