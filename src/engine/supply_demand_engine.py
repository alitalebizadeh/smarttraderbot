from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

import numpy as np
import pandas as pd

__all__ = [
    "SupplyDemandEngine",
    "SupplyDemandEngineError",
    "create_engine",
    "SupplyDemandZone",
    "SupplyDemandResult",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_BODY_RATIO: float = 0.4
MIN_BASE_CANDLES: int = 2
MAX_BASE_CANDLES: int = 10
EXPLOSION_ATR_THRESHOLD: float = 1.2
EXPLOSION_BODY_RATIO: float = 0.5
EXPLOSION_LOOKFORWARD: int = 3
ATR_PERIOD: int = 14
MIN_CANDLES_REQUIRED: int = 30

_REQUIRED_COLUMNS: frozenset[str] = frozenset({"open", "high", "low", "close"})


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class SupplyDemandEngineError(Exception):
    """Raised when SupplyDemandEngine encounters an unrecoverable input error."""


# ---------------------------------------------------------------------------
# Model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SupplyDemandZone:
    """A single institutional Supply or Demand zone.

    A zone forms when a base (consolidation) area is followed by a strong
    explosive directional move.  The zone boundaries are defined by the
    highest and lowest prices of the base candles.

    Attributes:
        zone_id: Unique identifier —
            ``"SD_{zone_type}_{symbol}_{timeframe}_{explosion_index}"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        zone_type: ``"supply"`` (bearish explosion) or ``"demand"``
            (bullish explosion).
        zone_top: Highest high across all base candles.
        zone_bottom: Lowest low across all base candles.
        zone_midpoint: Midpoint of the zone.
        zone_size: Width of the zone — ``zone_top - zone_bottom``.
        base_start_index: Zero-based index of the first base candle.
        base_end_index: Zero-based index of the last base candle.
        base_start_time: UTC timestamp of the first base candle.
        base_end_time: UTC timestamp of the last base candle.
        explosion_index: Zero-based index of the explosion candle.
        explosion_time: UTC timestamp of the explosion candle.
        explosion_strength: Body size of the explosion candle relative to
            ATR — ``body_size / ATR``.
        is_tested: ``True`` once price has returned into the zone.
        is_broken: ``True`` once price has closed fully through the zone's
            far boundary (zone is invalidated).
        tested_at_index: DataFrame index of the first test candle, or
            ``None``.
        tested_at_time: UTC timestamp of the first test, or ``None``.
        broken_at_index: DataFrame index of the break candle, or ``None``.
        broken_at_time: UTC timestamp of the break, or ``None``.
    """

    zone_id: str
    symbol: str
    timeframe: str
    zone_type: Literal["supply", "demand"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    zone_size: float
    base_start_index: int
    base_end_index: int
    base_start_time: datetime
    base_end_time: datetime
    explosion_index: int
    explosion_time: datetime
    explosion_strength: float
    is_tested: bool = field(default=False)
    is_broken: bool = field(default=False)
    tested_at_index: Optional[int] = field(default=None)
    tested_at_time: Optional[datetime] = field(default=None)
    broken_at_index: Optional[int] = field(default=None)
    broken_at_time: Optional[datetime] = field(default=None)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
            ``datetime`` values are ISO 8601 strings.
            Price fields are rounded to 6 decimal places.
            ``explosion_strength`` is rounded to 4 decimal places.
        """
        return {
            "zone_id": self.zone_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "zone_type": self.zone_type,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "zone_size": round(self.zone_size, 6),
            "base_start_index": self.base_start_index,
            "base_end_index": self.base_end_index,
            "base_start_time": self.base_start_time.isoformat(),
            "base_end_time": self.base_end_time.isoformat(),
            "explosion_index": self.explosion_index,
            "explosion_time": self.explosion_time.isoformat(),
            "explosion_strength": round(self.explosion_strength, 4),
            "is_tested": self.is_tested,
            "is_broken": self.is_broken,
            "tested_at_index": self.tested_at_index,
            "tested_at_time": (
                self.tested_at_time.isoformat()
                if self.tested_at_time is not None
                else None
            ),
            "broken_at_index": self.broken_at_index,
            "broken_at_time": (
                self.broken_at_time.isoformat()
                if self.broken_at_time is not None
                else None
            ),
        }


@dataclass
class SupplyDemandResult:
    """Complete Supply and Demand detection result for one symbol / timeframe.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        analyzed_at: UTC timestamp when the analysis was run.
        candle_count: Total candles in the source DataFrame.
        supply_zones: All detected supply :class:`SupplyDemandZone` objects,
            chronologically ordered.
        demand_zones: All detected demand :class:`SupplyDemandZone` objects,
            chronologically ordered.
        active_zones: Unbroken :class:`SupplyDemandZone` objects across both
            types, sorted by ``explosion_index`` descending (most recent
            first).
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    supply_zones: list[SupplyDemandZone] = field(default_factory=list)
    demand_zones: list[SupplyDemandZone] = field(default_factory=list)
    active_zones: list[SupplyDemandZone] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
            Nested :class:`SupplyDemandZone` objects are serialised via their
            own ``to_dict()`` methods.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "supply_zones": [z.to_dict() for z in self.supply_zones],
            "demand_zones": [z.to_dict() for z in self.demand_zones],
            "active_zones": [z.to_dict() for z in self.active_zones],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SupplyDemandEngine:
    """Detects institutional Supply and Demand zones from OHLCV candle data.

    A zone is formed when a base (quiet consolidation) is immediately followed
    by a strong explosive directional move.  Supply zones originate from
    bearish explosions; demand zones from bullish explosions.

    This engine is a **pure detection** module.  It does not produce trade
    signals, manage positions, or connect to external data sources.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> SupplyDemandResult:
        """Detect all Supply and Demand zones in *df*.

        Parameters
        ----------
        df:
            OHLCV DataFrame sorted oldest-first with integer index.
            Required columns: ``open``, ``high``, ``low``, ``close``.
            Timestamps are read from a ``timestamp`` or ``time`` column when
            available.
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"H1"``.

        Returns
        -------
        SupplyDemandResult
            Fully populated result.  Returns an empty result on validation
            failure — never raises.
        """
        empty = SupplyDemandResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=len(df) if isinstance(df, pd.DataFrame) else 0,
        )

        if not self._validate(df, symbol, timeframe):
            return empty

        df = df.reset_index(drop=True)
        n = len(df)

        # Resolve timestamps
        if "timestamp" in df.columns:
            timestamps = df["timestamp"].tolist()
        elif "time" in df.columns:
            timestamps = df["time"].tolist()
        else:
            timestamps = [datetime.now(tz=timezone.utc)] * n

        atr    = self._compute_atr(df)
        bases  = self._find_bases(df, atr)

        opens  = df["open"].to_numpy(dtype=float)
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        supply_zones: list[SupplyDemandZone] = []
        demand_zones: list[SupplyDemandZone] = []

        for base in bases:
            explosion = self._find_explosion(df, base, atr)
            if explosion is None:
                continue

            exp_idx   = explosion["index"]
            direction = explosion["direction"]

            base_indices: list[int] = base["candles"]
            base_highs = highs[base_indices]
            base_lows  = lows[base_indices]

            zone_top    = float(base_highs.max())
            zone_bottom = float(base_lows.min())

            if zone_top <= zone_bottom:
                self._log.debug(
                    "[%s/%s] Degenerate zone at base %d–%d, skipping.",
                    symbol, timeframe, base["start"], base["end"],
                )
                continue

            zone_midpoint = (zone_top + zone_bottom) / 2.0
            zone_size     = zone_top - zone_bottom

            atr_at_exp     = atr[exp_idx]
            body_size_exp  = abs(closes[exp_idx] - opens[exp_idx])
            explosion_str  = (
                float(body_size_exp / atr_at_exp)
                if atr_at_exp > 0
                else 0.0
            )

            zone_type: Literal["supply", "demand"] = (
                "demand" if direction == "bullish" else "supply"
            )

            zone_id = (
                f"SD_{zone_type.upper()}_{symbol}_{timeframe}_{exp_idx}"
            )

            zone = SupplyDemandZone(
                zone_id=zone_id,
                symbol=symbol,
                timeframe=timeframe,
                zone_type=zone_type,
                zone_top=zone_top,
                zone_bottom=zone_bottom,
                zone_midpoint=zone_midpoint,
                zone_size=zone_size,
                base_start_index=base["start"],
                base_end_index=base["end"],
                base_start_time=self._resolve_ts(timestamps, base["start"]),
                base_end_time=self._resolve_ts(timestamps, base["end"]),
                explosion_index=exp_idx,
                explosion_time=self._resolve_ts(timestamps, exp_idx),
                explosion_strength=explosion_str,
            )

            if zone_type == "supply":
                supply_zones.append(zone)
            else:
                demand_zones.append(zone)

        all_zones = supply_zones + demand_zones
        self._check_tests(df, all_zones, timestamps)

        active_zones = sorted(
            [z for z in all_zones if not z.is_broken],
            key=lambda z: z.explosion_index,
            reverse=True,
        )

        self._log.info(
            "[%s/%s] S&D analysis complete — supply=%d  demand=%d  active=%d",
            symbol, timeframe,
            len(supply_zones), len(demand_zones), len(active_zones),
        )

        return SupplyDemandResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=n,
            supply_zones=supply_zones,
            demand_zones=demand_zones,
            active_zones=active_zones,
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
                "[%s/%s] Insufficient rows (%d < %d) for S&D analysis.",
                symbol, timeframe, len(df), MIN_CANDLES_REQUIRED,
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Private: ATR
    # ------------------------------------------------------------------

    def _compute_atr(self, df: pd.DataFrame) -> np.ndarray:
        """Compute a rolling Average True Range for every candle.

        True range for candle *i* is:
        ``max(high[i] - low[i],
               abs(high[i] - close[i-1]),
               abs(low[i]  - close[i-1]))``

        The first candle falls back to ``high[0] - low[0]``.

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.

        Returns
        -------
        np.ndarray
            Rolling ATR array of the same length as *df*.
            The first ``ATR_PERIOD - 1`` values are ``NaN``.
        """
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        tr = np.empty(n, dtype=float)
        tr[0] = highs[0] - lows[0]

        for i in range(1, n):
            hl  = highs[i] - lows[i]
            hpc = abs(highs[i] - closes[i - 1])
            lpc = abs(lows[i]  - closes[i - 1])
            tr[i] = max(hl, hpc, lpc)

        atr = (
            pd.Series(tr)
            .rolling(window=ATR_PERIOD, min_periods=ATR_PERIOD)
            .mean()
            .to_numpy(dtype=float)
        )
        return atr

    # ------------------------------------------------------------------
    # Private: base detection
    # ------------------------------------------------------------------

    def _find_bases(
        self,
        df: pd.DataFrame,
        atr: np.ndarray,
    ) -> list[dict]:
        """Identify consolidation (base) periods in the candle data.

        A base is a run of consecutive candles whose body size is below
        ``BASE_BODY_RATIO × ATR``.  Only runs with a length in
        ``[MIN_BASE_CANDLES, MAX_BASE_CANDLES]`` are returned, and bases
        are non-overlapping (scanning resumes after the end of each base).

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.
        atr:
            Rolling ATR array of the same length as *df*.

        Returns
        -------
        list[dict]
            Each element: ``{"start": int, "end": int, "candles": list[int]}``.
        """
        opens  = df["open"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        bases: list[dict] = []
        i = ATR_PERIOD  # skip candles where ATR is not yet available

        while i < n:
            atr_val = atr[i]
            if np.isnan(atr_val) or atr_val <= 0:
                i += 1
                continue

            body = abs(closes[i] - opens[i])
            if body < atr_val * BASE_BODY_RATIO:
                # Start accumulating a base
                run: list[int] = [i]
                j = i + 1
                while j < n and len(run) < MAX_BASE_CANDLES:
                    atr_j = atr[j]
                    if np.isnan(atr_j) or atr_j <= 0:
                        break
                    body_j = abs(closes[j] - opens[j])
                    if body_j < atr_j * BASE_BODY_RATIO:
                        run.append(j)
                        j += 1
                    else:
                        break

                if len(run) >= MIN_BASE_CANDLES:
                    bases.append(
                        {"start": run[0], "end": run[-1], "candles": run}
                    )
                    i = run[-1] + 1  # non-overlapping scan
                else:
                    i += 1
            else:
                i += 1

        self._log.debug("Found %d base(s).", len(bases))
        return bases

    # ------------------------------------------------------------------
    # Private: explosion detection
    # ------------------------------------------------------------------

    def _find_explosion(
        self,
        df: pd.DataFrame,
        base: dict,
        atr: np.ndarray,
    ) -> Optional[dict]:
        """Find the first explosive candle after a base.

        Scans up to ``EXPLOSION_LOOKFORWARD`` candles after
        ``base["end"]``.  A candle qualifies when its body size meets
        ``EXPLOSION_ATR_THRESHOLD × ATR`` and its body-to-range ratio
        meets ``EXPLOSION_BODY_RATIO``.

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.
        base:
            Base dict from ``_find_bases``.
        atr:
            Rolling ATR array.

        Returns
        -------
        Optional[dict]
            ``{"index": int, "direction": str}`` or ``None``.
        """
        opens  = df["open"].to_numpy(dtype=float)
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        start  = base["end"] + 1
        end    = min(start + EXPLOSION_LOOKFORWARD, n)

        for i in range(start, end):
            atr_val = atr[i]
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            body        = abs(closes[i] - opens[i])
            candle_range = highs[i] - lows[i]

            if candle_range <= 0:
                continue

            body_ratio = body / candle_range

            if (
                body >= atr_val * EXPLOSION_ATR_THRESHOLD
                and body_ratio >= EXPLOSION_BODY_RATIO
            ):
                direction = "bullish" if closes[i] > opens[i] else "bearish"
                return {"index": i, "direction": direction}

        return None

    # ------------------------------------------------------------------
    # Private: test and break detection
    # ------------------------------------------------------------------

    def _check_tests(
        self,
        df: pd.DataFrame,
        zones: list[SupplyDemandZone],
        timestamps: list,
    ) -> None:
        """Scan post-explosion candles and mark tested / broken zones.

        Test conditions (candles strictly after ``explosion_index``):

        - **Demand zone tested**: ``low[i] <= zone_top``
        - **Supply zone tested**: ``high[i] >= zone_bottom``

        Break conditions:

        - **Demand zone broken**: ``close[i] < zone_bottom``
        - **Supply zone broken**: ``close[i] > zone_top``

        ``is_tested`` is recorded on first occurrence and does not stop
        scanning.  ``is_broken`` stops further scanning for that zone.

        Mutates *zones* in-place.

        Parameters
        ----------
        df:
            Full OHLCV DataFrame.
        zones:
            All detected zones to evaluate.
        timestamps:
            Resolved timestamp list aligned with *df* rows.
        """
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        for zone in zones:
            start = zone.explosion_index + 1
            if start >= n:
                continue

            for i in range(start, n):
                if zone.is_broken:
                    break

                if zone.zone_type == "demand":
                    # Test
                    if not zone.is_tested and lows[i] <= zone.zone_top:
                        zone.is_tested      = True
                        zone.tested_at_index = i
                        zone.tested_at_time  = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Demand zone %s tested at candle %d.",
                            zone.zone_id, i,
                        )
                    # Break
                    if closes[i] < zone.zone_bottom:
                        zone.is_broken      = True
                        zone.broken_at_index = i
                        zone.broken_at_time  = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Demand zone %s broken at candle %d.",
                            zone.zone_id, i,
                        )

                else:  # supply
                    # Test
                    if not zone.is_tested and highs[i] >= zone.zone_bottom:
                        zone.is_tested      = True
                        zone.tested_at_index = i
                        zone.tested_at_time  = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Supply zone %s tested at candle %d.",
                            zone.zone_id, i,
                        )
                    # Break
                    if closes[i] > zone.zone_top:
                        zone.is_broken      = True
                        zone.broken_at_index = i
                        zone.broken_at_time  = self._resolve_ts(timestamps, i)
                        self._log.debug(
                            "Supply zone %s broken at candle %d.",
                            zone.zone_id, i,
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

def create_engine() -> SupplyDemandEngine:
    """Factory — return a configured :class:`SupplyDemandEngine`.

    Returns
    -------
    SupplyDemandEngine
        Ready-to-use engine instance.
    """
    return SupplyDemandEngine()