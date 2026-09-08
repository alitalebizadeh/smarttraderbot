from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from src.engine.displacement_engine import Displacement, DisplacementResult
from src.utils.candle_utils import resolve_candle_timestamps, resolve_timestamp

__all__ = [
    "OrderBlockEngine",
    "OrderBlockEngineError",
    "create_engine",
    "OrderBlock",
    "OrderBlockResult",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OB_LOOKBACK: int = 10
STRENGTH_MAP: dict[str, float] = {"weak": 0.4, "moderate": 0.7, "strong": 1.0}
MIN_CANDLES_REQUIRED: int = 20
_SIMPLE_BODY_MULTIPLIER: float = 1.5
_SIMPLE_BODY_WINDOW: int = 20
_REQUIRED_COLUMNS: frozenset[str] = frozenset({"open", "high", "low", "close"})


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class OrderBlockEngineError(Exception):
    """Raised when OrderBlockEngine encounters an unrecoverable input error."""


# ---------------------------------------------------------------------------
# Model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OrderBlock:
    """A single detected institutional Order Block zone.

    An Order Block is the last opposing candle before a displacement move.
    It marks a price area where institutional limit orders were placed before
    a strong directional impulse.

    Attributes:
        ob_id: Unique identifier in the format
            ``"OB_{direction}_{symbol}_{timeframe}_{origin_index}"``.
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        direction: ``"bullish"`` for a demand OB, ``"bearish"`` for a supply OB.
        zone_top: Upper price boundary of the OB zone.
        zone_bottom: Lower price boundary of the OB zone.
        zone_midpoint: Midpoint of the zone — ``(zone_top + zone_bottom) / 2``.
        origin_index: Zero-based DataFrame index of the OB candle itself.
        origin_time: UTC timestamp of the OB candle.
        displacement_index: Zero-based DataFrame index of the displacement
            candle that validated this OB.
        displacement_time: UTC timestamp of the displacement candle.
        is_mitigated: ``True`` once price has returned into the OB zone.
        mitigated_at_index: DataFrame index of the mitigation candle, or
            ``None``.
        mitigated_at_time: UTC timestamp of mitigation, or ``None``.
        strength: Quality score in ``[0.0, 1.0]`` derived from displacement
            strength — ``0.4`` (weak), ``0.7`` (moderate), ``1.0`` (strong).
    """

    ob_id: str
    symbol: str
    timeframe: str
    direction: Literal["bullish", "bearish"]
    zone_top: float
    zone_bottom: float
    zone_midpoint: float
    origin_index: int
    origin_time: datetime
    displacement_index: int
    displacement_time: datetime
    is_mitigated: bool = field(default=False)
    is_broken_retested: bool = field(default=False)
    mitigated_at_index: Optional[int] = field(default=None)
    mitigated_at_time: Optional[datetime] = field(default=None)
    strength: float = field(default=0.0)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A flat, JSON-serialisable dictionary of all fields.
            ``datetime`` values are ISO 8601 strings.
            Price fields are rounded to 6 decimal places.
            ``strength`` is rounded to 4 decimal places.
        """
        return {
            "ob_id": self.ob_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "zone_top": round(self.zone_top, 6),
            "zone_bottom": round(self.zone_bottom, 6),
            "zone_midpoint": round(self.zone_midpoint, 6),
            "origin_index": self.origin_index,
            "origin_time": self.origin_time.isoformat(),
            "displacement_index": self.displacement_index,
            "displacement_time": self.displacement_time.isoformat(),
            "is_mitigated": self.is_mitigated,
            "is_broken_retested": self.is_broken_retested,
            "mitigated_at_index": self.mitigated_at_index,
            "mitigated_at_time": (
                self.mitigated_at_time.isoformat()
                if self.mitigated_at_time is not None
                else None
            ),
            "strength": round(self.strength, 4),
        }


@dataclass
class OrderBlockResult:
    """Complete Order Block detection result for one symbol / timeframe.

    Attributes:
        symbol: Instrument name, e.g. ``"XAUUSD"``.
        timeframe: Timeframe string, e.g. ``"H1"``.
        analyzed_at: UTC timestamp when the analysis was run.
        candle_count: Total candles in the source DataFrame.
        bullish_obs: All detected bullish :class:`OrderBlock` objects,
            chronologically ordered.
        bearish_obs: All detected bearish :class:`OrderBlock` objects,
            chronologically ordered.
        active_obs: Unmitigated :class:`OrderBlock` objects across both
            directions, sorted by ``origin_index`` descending (most recent
            first).
    """

    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    bullish_obs: list[OrderBlock] = field(default_factory=list)
    bearish_obs: list[OrderBlock] = field(default_factory=list)
    active_obs: list[OrderBlock] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary.

        Returns:
            A JSON-serialisable dictionary of all fields.
            Nested :class:`OrderBlock` objects are serialised via their own
            ``to_dict()`` methods.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "analyzed_at": self.analyzed_at.isoformat(),
            "candle_count": self.candle_count,
            "bullish_obs": [ob.to_dict() for ob in self.bullish_obs],
            "bearish_obs": [ob.to_dict() for ob in self.bearish_obs],
            "active_obs": [ob.to_dict() for ob in self.active_obs],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class OrderBlockEngine:
    """Detects institutional Order Blocks from OHLCV candle data.

    An Order Block is the last opposing candle before a strong displacement
    move.  This engine accepts an optional :class:`~src.engine.displacement_engine.DisplacementResult`
    from the upstream displacement engine and falls back to simple internal
    detection when one is not provided.

    This class is a **pure detection** module.  It does not produce trade
    signals, manage positions, or connect to external data sources.

    Parameters
    ----------
    ob_lookback:
        Maximum number of candles to look back from a displacement candle
        when searching for the opposing OB candle.  Must be >= 1.
        Default ``10``.
    """

    def __init__(self, ob_lookback: int = OB_LOOKBACK) -> None:
        if ob_lookback < 1:
            raise OrderBlockEngineError(
                f"ob_lookback must be >= 1, got {ob_lookback}."
            )
        self.ob_lookback = ob_lookback
        self._log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        displacement_result: Optional[Any] = None,
    ) -> OrderBlockResult:
        """Detect all Order Blocks in *df*.

        Parameters
        ----------
        df:
            OHLCV DataFrame sorted oldest-first with integer index.
            Required columns: ``open``, ``high``, ``low``, ``close``.
        symbol:
            Instrument name, e.g. ``"XAUUSD"``.
        timeframe:
            Timeframe label, e.g. ``"H1"``.
        displacement_result:
            Optional :class:`~src.engine.displacement_engine.DisplacementResult`
            from the displacement engine.  When ``None``, a simple internal
            fallback detector is used.

        Returns
        -------
        OrderBlockResult
            Fully populated result.  Returns an empty result on validation
            failure — never raises.
        """
        empty = OrderBlockResult(
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

        # Obtain displacement list
        displacements: list[Any]
        if (
            displacement_result is not None
            and hasattr(displacement_result, "displacements")
            and displacement_result.displacements
        ):
            displacements = displacement_result.displacements
            self._log.debug(
                "[%s/%s] Using %d displacements from provided DisplacementResult.",
                symbol, timeframe, len(displacements),
            )
        else:
            displacements = self._detect_displacements_simple(df)
            self._log.debug(
                "[%s/%s] Using %d displacements from simple fallback detector.",
                symbol, timeframe, len(displacements),
            )

        bullish_obs: list[OrderBlock] = []
        bearish_obs: list[OrderBlock] = []

        for disp in displacements:
            ob_info = self._find_ob_candle(df, disp)
            if ob_info is None:
                continue

            ob_idx = ob_info["ob_index"]
            direction: Literal["bullish", "bearish"] = ob_info["direction"]
            disp_idx = self._get_attr(disp, "index")
            disp_strength_str: str = self._get_attr(disp, "strength", default="moderate")
            strength = STRENGTH_MAP.get(disp_strength_str, 0.7)

            opens  = df["open"].to_numpy(dtype=float)
            highs  = df["high"].to_numpy(dtype=float)
            lows   = df["low"].to_numpy(dtype=float)

            if direction == "bullish":
                zone_top    = float(highs[ob_idx])
                zone_bottom = float(min(opens[ob_idx], lows[ob_idx]))
            else:
                zone_top    = float(max(opens[ob_idx], highs[ob_idx]))
                zone_bottom = float(lows[ob_idx])

            if zone_top <= zone_bottom:
                self._log.debug(
                    "[%s/%s] Skipping degenerate OB zone at index %d.",
                    symbol, timeframe, ob_idx,
                )
                continue

            zone_midpoint = (zone_top + zone_bottom) / 2.0

            ob_ts = self._resolve_ts(timestamps, ob_idx)
            disp_ts = self._resolve_ts(timestamps, disp_idx)

            ob_id = (
                f"OB_{direction.upper()}_{symbol}_{timeframe}_{ob_idx}"
            )

            ob = OrderBlock(
                ob_id=ob_id,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                zone_top=zone_top,
                zone_bottom=zone_bottom,
                zone_midpoint=zone_midpoint,
                origin_index=ob_idx,
                origin_time=ob_ts,
                displacement_index=disp_idx,
                displacement_time=disp_ts,
                strength=strength,
            )

            if direction == "bullish":
                bullish_obs.append(ob)
            else:
                bearish_obs.append(ob)

        all_obs = bullish_obs + bearish_obs
        all_obs = self._dedupe_obs(all_obs)
        self._check_broken_retested(df, all_obs)
        self._check_mitigation(df, all_obs, timestamps)

        active_obs = sorted(
            [
                ob for ob in all_obs
                if not ob.is_mitigated and not ob.is_broken_retested
            ],
            key=lambda ob: ob.origin_index,
            reverse=True,
        )

        self._log.info(
            "[%s/%s] OB analysis complete — bullish=%d  bearish=%d  active=%d",
            symbol, timeframe, len(bullish_obs), len(bearish_obs), len(active_obs),
        )

        return OrderBlockResult(
            symbol=symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=timezone.utc),
            candle_count=len(df),
            bullish_obs=bullish_obs,
            bearish_obs=bearish_obs,
            active_obs=active_obs,
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
                "[%s/%s] Insufficient rows (%d < %d) for OB analysis.",
                symbol, timeframe, len(df), MIN_CANDLES_REQUIRED,
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Private: simple fallback displacement detector
    # ------------------------------------------------------------------

    def _detect_displacements_simple(
        self, df: pd.DataFrame
    ) -> list[dict]:
        """Detect displacement-like candles using a simple body-size filter.

        A candle qualifies when its body size exceeds ``_SIMPLE_BODY_MULTIPLIER``
        times the rolling mean body over the previous ``_SIMPLE_BODY_WINDOW``
        candles.

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.

        Returns
        -------
        list[dict]
            Each element contains ``{"index": int, "direction": str,
            "strength": str}``.
        """
        opens  = df["open"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        bodies = np.abs(closes - opens)

        mean_bodies = (
            pd.Series(bodies)
            .rolling(window=_SIMPLE_BODY_WINDOW, min_periods=1)
            .mean()
            .to_numpy(dtype=float)
        )

        results: list[dict] = []
        for i in range(1, len(df)):
            threshold = mean_bodies[i] * _SIMPLE_BODY_MULTIPLIER
            if bodies[i] >= threshold:
                direction = "bullish" if closes[i] > opens[i] else "bearish"
                results.append(
                    {"index": i, "direction": direction, "strength": "moderate"}
                )

        return results

    # ------------------------------------------------------------------
    # Private: OB candle finder
    # ------------------------------------------------------------------

    def _find_ob_candle(
        self,
        df: pd.DataFrame,
        displacement: Any,
    ) -> Optional[dict]:
        """Locate the Order Block candle preceding a displacement.

        For a **bullish** displacement, scans backwards from ``disp_index - 1``
        looking for the last bearish candle (``close < open``).

        For a **bearish** displacement, scans backwards looking for the last
        bullish candle (``close > open``).

        Parameters
        ----------
        df:
            OHLCV DataFrame, integer-indexed.
        displacement:
            Either a :class:`~src.engine.displacement_engine.Displacement`
            object or a ``dict`` with ``"index"`` and ``"direction"`` keys.

        Returns
        -------
        Optional[dict]
            ``{"ob_index": int, "direction": str}`` or ``None`` when no
            suitable candle is found within ``ob_lookback`` candles.
        """
        disp_idx: int = self._get_attr(displacement, "index")
        disp_dir: str = self._get_attr(displacement, "direction")

        if disp_idx < 1:
            return None

        opens  = df["open"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        # ob direction is opposite to the displacement direction
        if disp_dir == "bullish":
            ob_direction: Literal["bullish", "bearish"] = "bullish"
            # Look for the last BEARISH candle before the displacement
            for back in range(1, self.ob_lookback + 1):
                idx = disp_idx - back
                if idx < 0:
                    break
                if closes[idx] < opens[idx]:   # bearish candle
                    return {"ob_index": idx, "direction": ob_direction}
        else:
            ob_direction = "bearish"
            # Look for the last BULLISH candle before the displacement
            for back in range(1, self.ob_lookback + 1):
                idx = disp_idx - back
                if idx < 0:
                    break
                if closes[idx] > opens[idx]:   # bullish candle
                    return {"ob_index": idx, "direction": ob_direction}

        return None

    # ------------------------------------------------------------------
    # Private: mitigation
    # ------------------------------------------------------------------

    def _check_broken_retested(
        self, df: pd.DataFrame, obs: list[OrderBlock]
    ) -> None:
        """Mark zones that were broken and subsequently retested."""
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        for ob in obs:
            broken = False
            start = ob.origin_index + 1
            for i in range(start, len(df)):
                if ob.direction == "bearish":
                    if not broken and closes[i] < ob.zone_bottom:
                        broken = True
                    elif broken and lows[i] <= ob.zone_top and highs[i] >= ob.zone_bottom:
                        ob.is_broken_retested = True
                        break
                else:
                    if not broken and closes[i] > ob.zone_top:
                        broken = True
                    elif broken and lows[i] <= ob.zone_top and highs[i] >= ob.zone_bottom:
                        ob.is_broken_retested = True
                        break

            if ob.is_broken_retested:
                self._log.info("OB %s marked broken and retested.", ob.ob_id)

    def _check_mitigation(
        self,
        df: pd.DataFrame,
        obs: list[OrderBlock],
        timestamps: list,
    ) -> None:
        """Mark mitigated Order Blocks by scanning post-displacement candles.

        Mitigation conditions (checked on candles *after* ``displacement_index``):

        - **Bullish OB**: ``low[i] <= zone_top`` **and** ``close[i] < zone_top``
          (price entered the zone from above / below).
        - **Bearish OB**: ``high[i] >= zone_bottom`` **and** ``close[i] > zone_bottom``
          (price entered the zone from below / above).

        Mutates *obs* in-place.  Each OB is only mitigated once.

        Parameters
        ----------
        df:
            Full OHLCV DataFrame.
        obs:
            Combined list of bullish and bearish Order Block objects.
        timestamps:
            Resolved timestamp list aligned with *df* rows.
        """
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n      = len(df)

        for ob in obs:
            start = ob.displacement_index + 1
            if start >= n:
                continue

            for i in range(start, n):
                if ob.is_mitigated:
                    break

                if ob.direction == "bullish":
                    entered = lows[i] <= ob.zone_top and highs[i] >= ob.zone_bottom
                else:
                    entered = highs[i] >= ob.zone_bottom and lows[i] <= ob.zone_top

                if entered:
                    ob.is_mitigated      = True
                    ob.mitigated_at_index = i
                    ob.mitigated_at_time  = resolve_timestamp(timestamps, i)
                    self._log.debug(
                        "%s OB %s mitigated at candle %d.",
                        ob.direction, ob.ob_id, i,
                    )

    @staticmethod
    def _dedupe_obs(obs: list[OrderBlock]) -> list[OrderBlock]:
        """Keep one OB per origin candle (most recent displacement wins)."""
        seen: dict[tuple[str, int], OrderBlock] = {}
        for ob in obs:
            key = (ob.direction, ob.origin_index)
            prev = seen.get(key)
            if prev is None or ob.displacement_index >= prev.displacement_index:
                seen[key] = ob
        return list(seen.values())

    # ------------------------------------------------------------------
    # Private: utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_attr(obj: Any, attr: str, default: Any = 0) -> Any:
        """Retrieve an attribute from either an object or a dict.

        Parameters
        ----------
        obj:
            Source object or dictionary.
        attr:
            Attribute / key name.
        default:
            Value returned when attribute / key is absent.

        Returns
        -------
        Any
            The resolved value.
        """
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

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

def create_engine(ob_lookback: int = OB_LOOKBACK) -> OrderBlockEngine:
    """Factory — return a configured :class:`OrderBlockEngine`.

    Parameters
    ----------
    ob_lookback:
        Maximum candles to look back for an OB candle.  Default ``10``.

    Returns
    -------
    OrderBlockEngine
        Ready-to-use engine instance.
    """
    return OrderBlockEngine(ob_lookback=ob_lookback)