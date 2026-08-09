from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

import numpy as np
import pandas as pd

__all__ = [
    "DisplacementEngine",
    "DisplacementEngineError",
    "create_engine",
    "Displacement",
    "DisplacementResult",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ATR_PERIOD: int = 14
BODY_ATR_THRESHOLD: float = 0.8
MIN_BODY_RATIO: float = 0.6
RECENT_LOOKBACK: int = 30
STRUCTURE_LOOKBACK: int = 10

_REQUIRED_COLUMNS: frozenset[str] = frozenset({"open", "high", "low", "close"})
_MINIMUM_ROWS: int = ATR_PERIOD + 2


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class DisplacementEngineError(Exception):
    """Raised when DisplacementEngine encounters an unrecoverable input error."""


# ---------------------------------------------------------------------------
# Private model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Displacement:
    """A single detected displacement candle.

    Attributes:
        index: Zero-based candle index within the source DataFrame.
        time: UTC timestamp of the candle.
        direction: ``"bullish"`` when close > open, ``"bearish"`` otherwise.
        body_size: Absolute body size — ``abs(close - open)``.
        candle_range: Total candle range — ``high - low``.
        body_ratio: Fraction of range occupied by body —
            ``body_size / candle_range``.
        atr_multiple: Body size relative to ATR at that point —
            ``body_size / ATR``.
        strength: Qualitative classification of the displacement.
        created_fvg: ``True`` when the 3-candle Fair Value Gap pattern
            formed at this candle.
        broke_structure: ``True`` when this candle's close exceeded the
            previous ``STRUCTURE_LOOKBACK`` candles' swing extreme.
    """

    index: int
    time: datetime
    direction: Literal["bullish", "bearish"]
    body_size: float
    candle_range: float
    body_ratio: float
    atr_multiple: float
    strength: Literal["weak", "moderate", "strong"]
    created_fvg: bool
    broke_structure: bool

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
            ``datetime`` is converted to ISO 8601.
            Numeric fields are rounded to 6 decimal places.
        """
        return {
            "index": self.index,
            "time": self.time.isoformat(),
            "direction": self.direction,
            "body_size": round(self.body_size, 6),
            "candle_range": round(self.candle_range, 6),
            "body_ratio": round(self.body_ratio, 6),
            "atr_multiple": round(self.atr_multiple, 6),
            "strength": self.strength,
            "created_fvg": self.created_fvg,
            "broke_structure": self.broke_structure,
        }


@dataclass
class DisplacementResult:
    """Complete displacement analysis for one symbol / timeframe.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"M1"``.
        analyzed_at: UTC timestamp when the analysis was run.
        candle_count: Total candles in the source DataFrame.
        displacements: All detected :class:`Displacement` objects,
            chronologically ordered.
        last_displacement: The most recent :class:`Displacement`, or
            ``None`` when none were found.
        has_recent_displacement: ``True`` when at least one displacement
            occurred within the last ``RECENT_LOOKBACK`` candles.
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    displacements: list[Displacement] = field(default_factory=list)
    last_displacement: Optional[Displacement] = field(default=None)
    has_recent_displacement: bool = field(default=False)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
            Nested :class:`Displacement` objects are serialised via their
            own ``to_dict()`` methods.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "displacements": [d.to_dict() for d in self.displacements],
            "last_displacement": (
                self.last_displacement.to_dict()
                if self.last_displacement is not None
                else None
            ),
            "has_recent_displacement": self.has_recent_displacement,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DisplacementEngine:
    """Detects institutional displacement candles from OHLCV price data.

    A displacement is a strong, impulsive candle that signals institutional
    participation.  It is characterised by a large body relative to the
    recent ATR, a clear directional close, and often precedes Order Block
    and Fair Value Gap formation.

    This engine is a **pure detection** module.  It does not produce trade
    signals, manage positions, or connect to external data sources.

    Parameters
    ----------
    atr_period:
        Rolling window for ATR computation.  Must be >= 2.  Default 14.
    body_atr_threshold:
        Minimum ratio of candle body to ATR required for a candle to be
        considered a displacement.  Default 0.8.
    min_body_ratio:
        Minimum ratio of body size to total candle range.  Candles with a
        smaller ratio (e.g. doji candles) are excluded.  Default 0.6.
    """

    def __init__(
        self,
        atr_period: int = ATR_PERIOD,
        body_atr_threshold: float = BODY_ATR_THRESHOLD,
        min_body_ratio: float = MIN_BODY_RATIO,
    ) -> None:
        if atr_period < 2:
            raise DisplacementEngineError(
                f"atr_period must be >= 2, got {atr_period}."
            )
        if body_atr_threshold <= 0:
            raise DisplacementEngineError(
                f"body_atr_threshold must be > 0, got {body_atr_threshold}."
            )
        if not (0 < min_body_ratio < 1):
            raise DisplacementEngineError(
                f"min_body_ratio must be in the open interval (0, 1), "
                f"got {min_body_ratio}."
            )

        self.atr_period = atr_period
        self.body_atr_threshold = body_atr_threshold
        self.min_body_ratio = min_body_ratio
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> DisplacementResult:
        """Detect all displacement candles in *df*.

        Parameters
        ----------
        df:
            OHLCV DataFrame sorted oldest-first with integer index.
            Required columns: ``open``, ``high``, ``low``, ``close``.
            Optional column: ``timestamp`` (used for candle time if present).
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"M1"``.

        Returns
        -------
        DisplacementResult
            Fully populated result.  Returns an empty result (with
            ``displacements=[]``) on validation failure — never raises.
        """
        empty = DisplacementResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.utcnow(),
            candle_count=len(df) if isinstance(df, pd.DataFrame) else 0,
        )

        if not self._validate(df, symbol, timeframe):
            return empty

        df = df.reset_index(drop=True)
        n = len(df)

        opens  = df["open"].to_numpy(dtype=float)
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        # Resolve timestamps
        if "timestamp" in df.columns:
            timestamps = df["timestamp"].tolist()
        elif "time" in df.columns:
            timestamps = df["time"].tolist()
        else:
            timestamps = [datetime.utcnow()] * n

        atr = self._compute_atr(df)
        displacements: list[Displacement] = []

        for i in range(self.atr_period, n):
            atr_val = atr[i]
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            candle_range = highs[i] - lows[i]
            if candle_range <= 0:
                # Doji / zero-range candle — skip
                continue

            body_size = abs(closes[i] - opens[i])
            body_ratio = body_size / candle_range

            # Body filter
            if body_size < atr_val * self.body_atr_threshold:
                continue
            if body_ratio < self.min_body_ratio:
                continue

            direction: Literal["bullish", "bearish"] = (
                "bullish" if closes[i] > opens[i] else "bearish"
            )

            atr_multiple = body_size / atr_val
            strength = self._classify_strength(atr_multiple)

            created_fvg = self._check_fvg(i, highs, lows, direction)
            broke_structure = self._check_structure_break(
                i, highs, lows, closes, direction
            )

            ts = timestamps[i]
            if not isinstance(ts, datetime):
                try:
                    ts = pd.Timestamp(ts).to_pydatetime()
                except Exception:
                    ts = datetime.utcnow()

            displacements.append(
                Displacement(
                    index=i,
                    time=ts,
                    direction=direction,
                    body_size=float(body_size),
                    candle_range=float(candle_range),
                    body_ratio=float(body_ratio),
                    atr_multiple=float(atr_multiple),
                    strength=strength,
                    created_fvg=created_fvg,
                    broke_structure=broke_structure,
                )
            )

        last_displacement: Optional[Displacement] = (
            displacements[-1] if displacements else None
        )

        has_recent = any(
            d.index >= n - RECENT_LOOKBACK for d in displacements
        )

        self._log.info(
            "[%s/%s] Displacement analysis complete — found=%d  recent=%s",
            symbol, timeframe, len(displacements), has_recent,
        )

        return DisplacementResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.utcnow(),
            candle_count=n,
            displacements=displacements,
            last_displacement=last_displacement,
            has_recent_displacement=has_recent,
        )

    # ------------------------------------------------------------------
    # Private helpers
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

        min_rows = self.atr_period + 2
        if len(df) < min_rows:
            self._log.warning(
                "[%s/%s] Insufficient rows (%d < %d) for displacement analysis.",
                symbol, timeframe, len(df), min_rows,
            )
            return False

        return True

    def _compute_atr(self, df: pd.DataFrame) -> np.ndarray:
        """Compute a rolling Average True Range for every candle.

        True range for candle *i* is:
        ``max(high[i] - low[i],
               abs(high[i] - close[i-1]),
               abs(low[i]  - close[i-1]))``

        The first candle's true range falls back to ``high[0] - low[0]``
        because there is no prior close.

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.

        Returns
        -------
        np.ndarray
            Rolling ATR array of the same length as *df*.
            The first ``atr_period - 1`` values are ``NaN``.
        """
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        tr = np.empty(n, dtype=float)
        tr[0] = highs[0] - lows[0]

        for i in range(1, n):
            hl   = highs[i] - lows[i]
            hpc  = abs(highs[i] - closes[i - 1])
            lpc  = abs(lows[i]  - closes[i - 1])
            tr[i] = max(hl, hpc, lpc)

        atr = (
            pd.Series(tr)
            .rolling(window=self.atr_period, min_periods=self.atr_period)
            .mean()
            .to_numpy(dtype=float)
        )
        return atr

    def _classify_strength(
        self, atr_multiple: float
    ) -> Literal["weak", "moderate", "strong"]:
        """Map an ATR multiple to a qualitative strength label.

        Parameters
        ----------
        atr_multiple:
            ``body_size / ATR`` for the candle being classified.

        Returns
        -------
        Literal["weak", "moderate", "strong"]
            - ``"strong"``   when ``atr_multiple >= 2.5``
            - ``"moderate"`` when ``1.5 <= atr_multiple < 2.5``
            - ``"weak"``     when ``atr_multiple < 1.5``
        """
        if atr_multiple >= 2.5:
            return "strong"
        if atr_multiple >= 1.5:
            return "moderate"
        return "weak"

    def _check_fvg(
        self,
        i: int,
        highs: np.ndarray,
        lows: np.ndarray,
        direction: Literal["bullish", "bearish"],
    ) -> bool:
        """Check whether candle *i* completes a 3-candle Fair Value Gap.

        Parameters
        ----------
        i:
            Current candle index.
        highs:
            Array of all candle highs.
        lows:
            Array of all candle lows.
        direction:
            Direction of the displacement candle.

        Returns
        -------
        bool
            ``True`` when the FVG pattern is confirmed:

            - **Bullish FVG**: ``lows[i] > highs[i-2]``
            - **Bearish FVG**: ``highs[i] < lows[i-2]``
        """
        if i < 2:
            return False

        if direction == "bullish":
            return bool(lows[i] > highs[i - 2])
        return bool(highs[i] < lows[i - 2])

    def _check_structure_break(
        self,
        i: int,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        direction: Literal["bullish", "bearish"],
    ) -> bool:
        """Check whether candle *i* breaks recent swing structure.

        A structure break is confirmed when the close price exceeds the
        extreme of the previous ``STRUCTURE_LOOKBACK`` candles.

        Parameters
        ----------
        i:
            Current candle index.
        highs:
            Array of all candle highs.
        lows:
            Array of all candle lows.
        closes:
            Array of all candle closes.
        direction:
            Direction of the displacement candle.

        Returns
        -------
        bool
            ``True`` when:

            - **Bullish**: ``closes[i] > max(highs[i-STRUCTURE_LOOKBACK : i])``
            - **Bearish**: ``closes[i] < min(lows[i-STRUCTURE_LOOKBACK : i])``
        """
        if i < STRUCTURE_LOOKBACK:
            return False

        prev_highs = highs[i - STRUCTURE_LOOKBACK : i]
        prev_lows  = lows[i - STRUCTURE_LOOKBACK : i]

        if direction == "bullish":
            return bool(closes[i] > prev_highs.max())
        return bool(closes[i] < prev_lows.min())


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_engine(
    atr_period: int = ATR_PERIOD,
    body_atr_threshold: float = BODY_ATR_THRESHOLD,
    min_body_ratio: float = MIN_BODY_RATIO,
) -> DisplacementEngine:
    """Factory — return a configured :class:`DisplacementEngine`.

    Parameters
    ----------
    atr_period:
        Rolling ATR window.  Default ``14``.
    body_atr_threshold:
        Minimum body-to-ATR ratio for displacement qualification.
        Default ``0.8``.
    min_body_ratio:
        Minimum body-to-range ratio.  Default ``0.6``.

    Returns
    -------
    DisplacementEngine
        Ready-to-use engine instance.
    """
    return DisplacementEngine(
        atr_period=atr_period,
        body_atr_threshold=body_atr_threshold,
        min_body_ratio=min_body_ratio,
    )