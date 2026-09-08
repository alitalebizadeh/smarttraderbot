from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

import numpy as np
import pandas as pd

__all__ = [
    "FVGEngine",
    "FVGEngineError",
    "create_engine",
    "FVG",
    "FVGResult",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_GAP_SIZE_PIPS: float = 2.0
MIN_CANDLES_REQUIRED: int = 5
RECENT_FVG_LOOKBACK: int = 50
_MIN_PIP_SIZE: float = 0.00001
_REQUIRED_COLUMNS: frozenset[str] = frozenset({"high", "low"})
_PIP_RANGE_DIVISOR: float = 10.0


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class FVGEngineError(Exception):
    """Raised when FVGEngine encounters an unrecoverable input error."""


# ---------------------------------------------------------------------------
# Model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FVG:
    """A single detected Fair Value Gap (imbalance) zone.

    A Fair Value Gap is a 3-candle pattern where the middle candle creates
    a price imbalance between candle ``i-2`` and candle ``i``.  These zones
    act as price magnets — institutional algorithms often return to fill them.

    Pattern structure:
        - ``candle[i-2]`` → ``candle_1_index``    (anchor candle)
        - ``candle[i-1]``  → ``candle_2_index``   (impulse / displacement candle)
        - ``candle[i]``    → ``formation_index``  (confirmation candle)

    Zone boundaries:
        - **Bullish FVG**: ``gap_bottom = high[i-2]``, ``gap_top = low[i]``
        - **Bearish FVG**: ``gap_bottom = high[i]``,  ``gap_top = low[i-2]``

    Attributes:
        fvg_id: Unique identifier — ``"FVG_{direction}_{symbol}_{tf}_{index}"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        direction: ``"bullish"`` for a demand gap, ``"bearish"`` for a
            supply gap.
        gap_top: Upper price boundary of the gap.
        gap_bottom: Lower price boundary of the gap.
        gap_size: Absolute width of the gap — ``gap_top - gap_bottom``.
        gap_size_pct: Gap size as a percentage of the mid-price.
        formation_index: Zero-based index of candle ``i`` (the third candle).
        formation_time: UTC timestamp of the formation candle.
        candle_1_index: Zero-based index of candle ``i-2`` (anchor).
        candle_2_index: Zero-based index of candle ``i-1`` (impulse).
        is_filled: ``True`` when price has fully closed through the gap.
        is_partially_filled: ``True`` when price entered the gap without
            fully closing through it.
        filled_at_index: DataFrame index of the fill candle, or ``None``.
        filled_at_time: UTC timestamp of the fill, or ``None``.
    """

    fvg_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    gap_top: float
    gap_bottom: float
    gap_size: float
    gap_size_pct: float
    formation_index: int
    formation_time: datetime
    candle_1_index: int
    candle_2_index: int
    is_filled: bool = field(default=False)
    is_partially_filled: bool = field(default=False)
    filled_at_index: Optional[int] = field(default=None)
    filled_at_time: Optional[datetime] = field(default=None)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
            ``datetime`` values are ISO 8601 strings.
            Price and percentage fields are rounded to 6 decimal places.
        """
        return {
            "fvg_id": self.fvg_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "gap_top": round(self.gap_top, 6),
            "gap_bottom": round(self.gap_bottom, 6),
            "gap_size": round(self.gap_size, 6),
            "gap_size_pct": round(self.gap_size_pct, 6),
            "formation_index": self.formation_index,
            "formation_time": self.formation_time.isoformat(),
            "candle_1_index": self.candle_1_index,
            "candle_2_index": self.candle_2_index,
            "is_filled": self.is_filled,
            "is_partially_filled": self.is_partially_filled,
            "filled_at_index": self.filled_at_index,
            "filled_at_time": (
                self.filled_at_time.isoformat()
                if self.filled_at_time is not None
                else None
            ),
        }


@dataclass
class FVGResult:
    """Complete Fair Value Gap detection result for one symbol / timeframe.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        analyzed_at: UTC timestamp when the analysis was run.
        candle_count: Total candles in the source DataFrame.
        bullish_fvgs: All detected bullish :class:`FVG` objects,
            chronologically ordered.
        bearish_fvgs: All detected bearish :class:`FVG` objects,
            chronologically ordered.
        active_fvgs: Unfilled :class:`FVG` objects across both directions,
            sorted by ``formation_index`` descending (most recent first).
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    bullish_fvgs: list[FVG] = field(default_factory=list)
    bearish_fvgs: list[FVG] = field(default_factory=list)
    active_fvgs: list[FVG] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
            Nested :class:`FVG` objects are serialised via their own
            ``to_dict()`` methods.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "bullish_fvgs": [f.to_dict() for f in self.bullish_fvgs],
            "bearish_fvgs": [f.to_dict() for f in self.bearish_fvgs],
            "active_fvgs": [f.to_dict() for f in self.active_fvgs],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class FVGEngine:
    """Detects Fair Value Gaps (imbalances) from OHLCV candle data.

    A Fair Value Gap is a 3-candle pattern where the middle candle creates
    a price imbalance that institutional algorithms tend to revisit.

    This engine is a **pure detection** module.  It does not produce trade
    signals, manage positions, or connect to external data sources.

    Parameters
    ----------
    min_gap_pips:
        Minimum gap size in pips.  FVGs smaller than this threshold are
        discarded to filter out noise on lower timeframes.  Must be > 0.
        Default ``2.0``.
    """

    def __init__(self, min_gap_pips: float = MIN_GAP_SIZE_PIPS) -> None:
        if min_gap_pips <= 0:
            raise FVGEngineError(
                f"min_gap_pips must be > 0, got {min_gap_pips}."
            )
        self.min_gap_pips = min_gap_pips
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> FVGResult:
        """Detect all Fair Value Gaps in *df*.

        Parameters
        ----------
        df:
            OHLCV DataFrame sorted oldest-first with integer index.
            Required columns: ``high``, ``low``.
            Timestamps are read from a ``timestamp`` or ``time`` column when
            available; otherwise timezone-aware UTC is used as a fallback.
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"M1"``.

        Returns
        -------
        FVGResult
            Fully populated result.  Returns an empty result on validation
            failure — never raises.
        """
        empty = FVGResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=len(df) if isinstance(df, pd.DataFrame) else 0,
        )

        if not self._validate(df, symbol, timeframe):
            return empty

        # Save timestamps before resetting index
        if df.index.name == "time" or isinstance(df.index, pd.DatetimeIndex):
            timestamps = df.index.tolist()
        elif "timestamp" in df.columns:
            timestamps = df["timestamp"].tolist()
        elif "time" in df.columns:
            timestamps = df["time"].tolist()
        else:
            timestamps = [datetime.now(tz=timezone.utc)] * len(df)

        df = df.reset_index(drop=True)
        n = len(df)

        highs = df["high"].to_numpy(dtype=float)
        lows  = df["low"].to_numpy(dtype=float)

        pip_size      = self._estimate_pip_size(df)
        min_gap_size  = self.min_gap_pips * pip_size

        bullish_fvgs: list[FVG] = []
        bearish_fvgs: list[FVG] = []

        for i in range(2, n):
            # --- Bullish FVG ---
            gap_bottom_bull = highs[i - 2]
            gap_top_bull    = lows[i]
            if gap_top_bull > gap_bottom_bull:
                gap_size = gap_top_bull - gap_bottom_bull
                if gap_size >= min_gap_size:
                    mid_price = (gap_top_bull + gap_bottom_bull) / 2.0
                    gap_pct   = (gap_size / mid_price * 100.0) if mid_price > 0 else 0.0
                    ts        = self._resolve_ts(timestamps, i)
                    fvg_id    = f"FVG_BULLISH_{symbol}_{timeframe}_{i}"
                    bullish_fvgs.append(
                        FVG(
                            fvg_id=fvg_id,
                            symbol=symbol,
                            timeframe=timeframe,
                            direction="bullish",
                            gap_top=float(gap_top_bull),
                            gap_bottom=float(gap_bottom_bull),
                            gap_size=float(gap_size),
                            gap_size_pct=float(gap_pct),
                            formation_index=i,
                            formation_time=ts,
                            candle_1_index=i - 2,
                            candle_2_index=i - 1,
                        )
                    )

            # --- Bearish FVG ---
            gap_top_bear    = lows[i - 2]
            gap_bottom_bear = highs[i]
            if gap_top_bear > gap_bottom_bear:
                gap_size = gap_top_bear - gap_bottom_bear
                if gap_size >= min_gap_size:
                    mid_price = (gap_top_bear + gap_bottom_bear) / 2.0
                    gap_pct   = (gap_size / mid_price * 100.0) if mid_price > 0 else 0.0
                    ts        = self._resolve_ts(timestamps, i)
                    fvg_id    = f"FVG_BEARISH_{symbol}_{timeframe}_{i}"
                    bearish_fvgs.append(
                        FVG(
                            fvg_id=fvg_id,
                            symbol=symbol,
                            timeframe=timeframe,
                            direction="bearish",
                            gap_top=float(gap_top_bear),
                            gap_bottom=float(gap_bottom_bear),
                            gap_size=float(gap_size),
                            gap_size_pct=float(gap_pct),
                            formation_index=i,
                            formation_time=ts,
                            candle_1_index=i - 2,
                            candle_2_index=i - 1,
                        )
                    )

        all_fvgs = bullish_fvgs + bearish_fvgs
        self._check_fills(df, all_fvgs, timestamps)

        active_fvgs = sorted(
            [fvg for fvg in all_fvgs if not fvg.is_filled],
            key=lambda fvg: fvg.formation_index,
            reverse=True,
        )

        self._log.info(
            "[%s/%s] FVG analysis complete — "
            "bullish=%d  bearish=%d  active=%d",
            symbol, timeframe,
            len(bullish_fvgs), len(bearish_fvgs), len(active_fvgs),
        )

        return FVGResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=n,
            bullish_fvgs=bullish_fvgs,
            bearish_fvgs=bearish_fvgs,
            active_fvgs=active_fvgs,
        )

    # ------------------------------------------------------------------
    # Private: validation
    # ------------------------------------------------------------------

    def _validate(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Validate the input DataFrame and log any issues.

        Parameters
        ----------
        df:
            DataFrame to validate.
        symbol:
            Instrument name (used in log messages).
        timeframe:
            Timeframe label (used in log messages).

        Returns
        -------
        bool
            ``True`` when the DataFrame is usable, ``False`` otherwise.
        """
        if not isinstance(df, pd.DataFrame):
            self._log.warning(
                "[%s/%s] candles must be a pandas DataFrame.", symbol, timeframe
            )
            return False

        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing:
            self._log.warning(
                "[%s/%s] DataFrame missing required columns: %s.",
                symbol, timeframe, sorted(missing),
            )
            return False

        if len(df) < MIN_CANDLES_REQUIRED:
            self._log.warning(
                "[%s/%s] Insufficient rows (%d < %d) for FVG detection.",
                symbol, timeframe, len(df), MIN_CANDLES_REQUIRED,
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Private: pip size estimation
    # ------------------------------------------------------------------

    def _estimate_pip_size(self, df: pd.DataFrame) -> float:
        """Estimate the instrument pip size from the candle data.

        Uses the median of ``(high - low) / _PIP_RANGE_DIVISOR`` across all
        candles.

        Parameters
        ----------
        df:
            OHLCV DataFrame with ``high`` and ``low`` columns.

        Returns
        -------
        float
            Estimated pip size.  Always >= ``_MIN_PIP_SIZE`` to avoid
            division by zero or degenerate filter thresholds.
        """
        ranges = (df["high"] - df["low"]).to_numpy(dtype=float)
        median_range = float(np.median(ranges))
        pip_size = median_range / _PIP_RANGE_DIVISOR
        return max(pip_size, _MIN_PIP_SIZE)

    # ------------------------------------------------------------------
    # Private: fill detection
    # ------------------------------------------------------------------

    def _check_fills(
        self,
        df: pd.DataFrame,
        fvgs: list[FVG],
        timestamps: list,
    ) -> None:
        """Scan post-formation candles and mark filled / partially filled FVGs.

        Fill rules (only candles strictly after ``formation_index``):

        **Bullish FVG**:
            - *Fully filled*:    ``low[i] <= gap_bottom``
            - *Partially filled*: ``gap_bottom < low[i] <= gap_top``

        **Bearish FVG**:
            - *Fully filled*:    ``high[i] >= gap_top``
            - *Partially filled*: ``gap_bottom <= high[i] < gap_top``

        Partial fill is recorded but scanning continues — a full fill can
        still occur on a later candle.  Once fully filled, scanning stops.

        Mutates *fvgs* in-place.

        Parameters
        ----------
        df:
            Full OHLCV DataFrame.
        fvgs:
            List of :class:`FVG` objects to evaluate.
        timestamps:
            Resolved timestamp list aligned with *df* rows.
        """
        highs = df["high"].to_numpy(dtype=float)
        lows  = df["low"].to_numpy(dtype=float)
        n     = len(df)

        for fvg in fvgs:
            start = fvg.formation_index + 1
            if start >= n:
                continue

            for i in range(start, n):
                if fvg.is_filled:
                    break

                if fvg.direction == "bullish":
                    if lows[i] <= fvg.gap_bottom:
                        # Full fill
                        fvg.is_filled           = True
                        fvg.is_partially_filled = True
                        fvg.filled_at_index     = i
                        fvg.filled_at_time      = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Bullish FVG %s fully filled at candle %d.",
                            fvg.fvg_id, i,
                        )
                    elif lows[i] <= fvg.gap_top and not fvg.is_partially_filled:
                        # Partial fill — keep scanning
                        fvg.is_partially_filled = True
                        self._log.debug(
                            "Bullish FVG %s partially filled at candle %d.",
                            fvg.fvg_id, i,
                        )
                else:  # bearish
                    if highs[i] >= fvg.gap_top:
                        # Full fill
                        fvg.is_filled           = True
                        fvg.is_partially_filled = True
                        fvg.filled_at_index     = i
                        fvg.filled_at_time      = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Bearish FVG %s fully filled at candle %d.",
                            fvg.fvg_id, i,
                        )
                    elif highs[i] >= fvg.gap_bottom and not fvg.is_partially_filled:
                        # Partial fill — keep scanning
                        fvg.is_partially_filled = True
                        self._log.debug(
                            "Bearish FVG %s partially filled at candle %d.",
                            fvg.fvg_id, i,
                        )

    # ------------------------------------------------------------------
    # Private: utility
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_ts(timestamps: list, idx: int) -> datetime:
        """Safely convert a timestamp entry to a :class:`datetime`.

        Parameters
        ----------
        timestamps:
            List of raw timestamp values aligned with the DataFrame.
        idx:
            Row index to resolve.

        Returns
        -------
        datetime
            UTC ``datetime``.  Falls back to the current timezone-aware UTC time on error.
        """
        try:
            ts = timestamps[idx]
            if isinstance(ts, datetime):
                return ts
            return pd.Timestamp(ts).to_pydatetime()
        except Exception:
            return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_engine(min_gap_pips: float = MIN_GAP_SIZE_PIPS) -> FVGEngine:
    """Factory — return a configured :class:`FVGEngine`.

    Parameters
    ----------
    min_gap_pips:
        Minimum gap size in pips.  FVGs smaller than this are filtered out.
        Default ``2.0``.

    Returns
    -------
    FVGEngine
        Ready-to-use engine instance.
    """
    return FVGEngine(min_gap_pips=min_gap_pips)