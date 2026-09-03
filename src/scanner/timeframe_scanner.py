from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from src.engine.confluence_engine import ConfluenceEngine
from src.engine.displacement_engine import DisplacementEngine
from src.engine.entry_point_engine import EntryPointEngine
from src.engine.fvg_engine import FVGEngine
from src.engine.order_block_engine import OrderBlockEngine
from src.engine.poi_engine import POIEngine
from src.engine.supply_demand_engine import SupplyDemandEngine
from src.models.market_snapshot import MarketSnapshot
from src.models.scan_result import SymbolTimeframePair, TimeframeScanResult
from src.models.scoring import ScoringOutput
from src.scoring.zone_scorer import ZoneScorer
from src.engine.zone_cluster_engine import ZoneClusterEngine

__all__ = ["TimeframeScanner", "TimeframeScannerError", "create_scanner"]

# ---------------------------------------------------------------------------
# Lazy import for engines that may not exist yet at import time
# ---------------------------------------------------------------------------

_MS_ENGINE_AVAILABLE = True
_LIQ_ENGINE_AVAILABLE = True

try:
    from src.engine.market_structure_engine import MarketStructureEngine
except ImportError:
    _MS_ENGINE_AVAILABLE = False  # type: ignore[assignment]

try:
    from src.engine.liquidity_engine import LiquidityEngine
except ImportError:
    _LIQ_ENGINE_AVAILABLE = False  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SWING_LENGTH: int = 5
_MIN_CANDLES_FOR_PRICE: int = 1


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class TimeframeScannerError(Exception):
    """Raised when TimeframeScanner encounters an unrecoverable setup error."""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class TimeframeScanner:
    """Orchestrates the full SMC analysis pipeline for one symbol / timeframe.

    Calls all analytical engines in sequence, assembles a
    :class:`~src.models.market_snapshot.MarketSnapshot`, runs confluence
    scoring, and returns a :class:`~src.models.scan_result.TimeframeScanResult`.

    Each engine is wrapped in an isolated ``try / except`` block — a single
    engine failure does not abort the rest of the pipeline.

    The public :meth:`scan` method never raises; it always returns a
    :class:`~src.models.scan_result.TimeframeScanResult`.

    Parameters
    ----------
    candle_provider:
        Any object implementing ``get_candles(symbol, timeframe) → DataFrame``
        and ``get_latest_price(symbol, timeframe) → Optional[float]``.
    config:
        Optional configuration dictionary.  Recognised keys:

        - ``"swing_length"`` (int): Swing detection window for the market
          structure engine.  Default ``5``.
    """

    def __init__(
        self,
        candle_provider: Any,
        config: Optional[dict] = None,
    ) -> None:
        self._provider = candle_provider
        self._config   = config or {}
        self._log      = logging.getLogger(__name__)

        swing_length: int = int(
            self._config.get("swing_length", _DEFAULT_SWING_LENGTH)
        )

        # Market Structure Engine
        if _MS_ENGINE_AVAILABLE:
            self._ms_engine: Optional[Any] = MarketStructureEngine(
                swing_length=swing_length
            )
        else:
            self._ms_engine = None
            self._log.warning("MarketStructureEngine not available — skipping.")

        # Liquidity Engine
        if _LIQ_ENGINE_AVAILABLE:
            self._liq_engine: Optional[Any] = LiquidityEngine()
        else:
            self._liq_engine = None
            self._log.warning("LiquidityEngine not available — skipping.")

        self._disp_engine: DisplacementEngine = DisplacementEngine()
        self._ob_engine:   OrderBlockEngine    = OrderBlockEngine()
        self._fvg_engine:  FVGEngine           = FVGEngine()
        self._sd_engine:   SupplyDemandEngine  = SupplyDemandEngine()
        self._poi_engine:  POIEngine           = POIEngine()
        self._conf_engine: ConfluenceEngine    = ConfluenceEngine()
        self._scorer:      ZoneScorer          = ZoneScorer()
        self._cluster_engine: ZoneClusterEngine = ZoneClusterEngine(
            pip_size=0.01, cluster_tolerance_pips=20.0, min_factors=1
        )
        self._entry_engine: EntryPointEngine   = EntryPointEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, pair: Any) -> TimeframeScanResult:
        """Run the full analysis pipeline for *pair* and return a result.

        Parameters
        ----------
        pair:
            A :class:`~src.models.scan_result.SymbolTimeframePair` (or any
            object with ``.symbol``, ``.timeframe``, ``.display_name``).

        Returns
        -------
        TimeframeScanResult
            Always a valid result.  ``success=False`` when a fatal error
            prevents pipeline execution.
        """
        symbol:       str = str(getattr(pair, "symbol", ""))
        timeframe:    str = str(getattr(pair, "timeframe", ""))
        display_name: str = str(
            getattr(pair, "display_name", f"{symbol} {timeframe}")
        )

        start_ns = time.perf_counter_ns()

        try:
            snapshot, scoring_output = self._run_pipeline(symbol, timeframe)
            duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            entry_map = getattr(snapshot, "entry_map", None)

            self._log.info(
                "[%s/%s] Scan complete in %.1f ms — success=True",
                symbol, timeframe, duration_ms,
            )

            return TimeframeScanResult(
                symbol=symbol,
                timeframe=timeframe,
                display_name=display_name,
                success=True,
                scanned_at=datetime.utcnow(),
                scan_duration_ms=duration_ms,
                snapshot=snapshot,
                scoring_output=scoring_output,
                entry_map=entry_map,
                error_message=None,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            self._log.error(
                "[%s/%s] Scan failed after %.1f ms: %s",
                symbol, timeframe, duration_ms, exc,
                exc_info=True,
            )
            return TimeframeScanResult(
                symbol=symbol,
                timeframe=timeframe,
                display_name=display_name,
                success=False,
                scanned_at=datetime.utcnow(),
                scan_duration_ms=duration_ms,
                snapshot=None,
                scoring_output=None,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Private: pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        symbol: str,
        timeframe: str,
    ) -> tuple[MarketSnapshot, ScoringOutput]:
        """Execute the full engine pipeline and return results.

        Parameters
        ----------
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.

        Returns
        -------
        tuple[MarketSnapshot, ScoringOutput]
            The assembled snapshot and scored output.

        Raises
        ------
        Exception
            Re-raises any fatal error that prevents pipeline execution
            (e.g. candle loading failure).
        """
        pipeline_start = time.perf_counter_ns()

        # ----------------------------------------------------------
        # Step 1 — Load candles (fatal if this fails)
        # ----------------------------------------------------------
        df: pd.DataFrame = self._provider.get_candles(symbol, timeframe)

        if df is None or (hasattr(df, "__len__") and len(df) == 0):
            raise TimeframeScannerError(
                f"No candle data returned for {symbol}/{timeframe}."
            )

        # ----------------------------------------------------------
        # Step 2 — Resolve current price
        # ----------------------------------------------------------
        current_price: float = 0.0
        try:
            price = self._provider.get_latest_price(symbol, timeframe)
            if price is not None:
                current_price = float(price)
        except Exception:
            pass

        if current_price == 0.0 and "close" in df.columns and len(df) >= _MIN_CANDLES_FOR_PRICE:
            current_price = float(df["close"].iloc[-1])

        # ----------------------------------------------------------
        # Step 3 — Run engines (each isolated)
        # ----------------------------------------------------------
        engines_run:    list[str] = []
        engines_failed: list[str] = []

        market_structure: Optional[Any] = None
        liquidity:        Optional[Any] = None
        displacement:     Optional[Any] = None
        order_blocks:     Optional[Any] = None
        fvgs:             Optional[Any] = None
        supply_demand:    Optional[Any] = None
        pois:             Optional[Any] = None

        # Market Structure
        if self._ms_engine is not None:
            try:
                market_structure = self._ms_engine.analyze(df, symbol, timeframe)
                engines_run.append("market_structure")
            except Exception as exc:
                engines_failed.append("market_structure")
                self._log.warning(
                    "[%s/%s] market_structure_engine failed: %s", symbol, timeframe, exc
                )

        # Liquidity — optionally receive swing points from market structure
        if self._liq_engine is not None:
            try:
                swing_highs: list[Any] = []
                swing_lows:  list[Any] = []
                if market_structure is not None:
                    swing_highs = getattr(market_structure, "swing_highs", []) or []
                    swing_lows  = getattr(market_structure, "swing_lows",  []) or []
                liquidity = self._liq_engine.analyze(
                    df, symbol, timeframe,
                    swing_highs=swing_highs,
                    swing_lows=swing_lows,
                )
                engines_run.append("liquidity")
            except TypeError:
                # Older signature without swing_highs/swing_lows
                try:
                    liquidity = self._liq_engine.analyze(df, symbol, timeframe)
                    engines_run.append("liquidity")
                except Exception as exc:
                    engines_failed.append("liquidity")
                    self._log.warning(
                        "[%s/%s] liquidity_engine failed: %s", symbol, timeframe, exc
                    )
            except Exception as exc:
                engines_failed.append("liquidity")
                self._log.warning(
                    "[%s/%s] liquidity_engine failed: %s", symbol, timeframe, exc
                )

        # Displacement
        try:
            displacement = self._disp_engine.analyze(df, symbol, timeframe)
            engines_run.append("displacement")
        except Exception as exc:
            engines_failed.append("displacement")
            self._log.warning(
                "[%s/%s] displacement_engine failed: %s", symbol, timeframe, exc
            )

        # Order Blocks
        try:
            order_blocks = self._ob_engine.analyze(
                df, symbol, timeframe,
                displacement_result=displacement,
            )
            engines_run.append("order_blocks")
        except Exception as exc:
            engines_failed.append("order_blocks")
            self._log.warning(
                "[%s/%s] order_block_engine failed: %s", symbol, timeframe, exc
            )

        # FVGs
        try:
            fvgs = self._fvg_engine.analyze(df, symbol, timeframe)
            engines_run.append("fvgs")
        except Exception as exc:
            engines_failed.append("fvgs")
            self._log.warning(
                "[%s/%s] fvg_engine failed: %s", symbol, timeframe, exc
            )

        # Supply & Demand
        try:
            supply_demand = self._sd_engine.analyze(df, symbol, timeframe)
            engines_run.append("supply_demand")
        except Exception as exc:
            engines_failed.append("supply_demand")
            self._log.warning(
                "[%s/%s] supply_demand_engine failed: %s", symbol, timeframe, exc
            )

        # POIs
        try:
            pois = self._poi_engine.analyze(
                df, symbol, timeframe,
                ob_result=order_blocks,
                fvg_result=fvgs,
                sd_result=supply_demand,
            )
            engines_run.append("pois")
        except Exception as exc:
            engines_failed.append("pois")
            self._log.warning(
                "[%s/%s] poi_engine failed: %s", symbol, timeframe, exc
            )

        # ----------------------------------------------------------
        # Step 4 — Assemble snapshot
        # ----------------------------------------------------------
        pipeline_ms = (time.perf_counter_ns() - pipeline_start) / 1_000_000.0

        snapshot = self._build_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            df=df,
            ms=market_structure,
            liq=liquidity,
            disp=displacement,
            ob=order_blocks,
            fvg=fvgs,
            sd=supply_demand,
            poi=pois,
            engines_run=engines_run,
            engines_failed=engines_failed,
            duration_ms=pipeline_ms,
        )

        # ----------------------------------------------------------
        # Step 5 — Confluence
        # ----------------------------------------------------------
        confluence_map: Optional[Any] = None
        try:
            confluence_map = self._conf_engine.analyze(
                symbol=symbol,
                timeframe=timeframe,
                poi_result=pois,
                market_structure=market_structure,
                liquidity_map=liquidity,
            )
            bias = "neutral"
            if market_structure is not None:
                bias = str(getattr(market_structure, "current_bias", "neutral"))
            confluence_map = self._conf_engine.filter_by_bias(confluence_map, bias)
        except Exception as exc:
            self._log.warning(
                "[%s/%s] confluence_engine failed: %s", symbol, timeframe, exc
            )

        # ----------------------------------------------------------
        # Step 6 — Scoring
        # ----------------------------------------------------------
        total_ms = (time.perf_counter_ns() - pipeline_start) / 1_000_000.0
        scoring_output: ScoringOutput = self._scorer.score_confluence_map(
            confluence_map=confluence_map,
            current_price=current_price,
            scan_duration_ms=total_ms,
        )

        # Zone Clustering — merge overlapping zones into unified setups
        cluster_map = None
        try:
            cluster_map = self._cluster_engine.analyze(
                snapshot, symbol, timeframe, df
            )
            self._log.info(
                "[%s/%s] Clustering complete — clusters=%d  tradeable=%d  bias=%s",
                symbol, timeframe,
                cluster_map.total_count,
                cluster_map.tradeable_count,
                cluster_map.market_bias,
            )
        except Exception as exc:
            self._log.warning("[%s/%s] Clustering failed: %s", symbol, timeframe, exc)

        snapshot.cluster_map = cluster_map

        # Entry points — best with-trend levels after analysis
        entry_map = None
        try:
            entry_map = self._entry_engine.analyze(
                symbol=symbol,
                timeframe=timeframe,
                current_price=current_price,
                market_structure=market_structure,
                cluster_map=cluster_map,
                scoring_output=scoring_output,
            )
        except Exception as exc:
            self._log.warning("[%s/%s] Entry engine failed: %s", symbol, timeframe, exc)

        snapshot.entry_map = entry_map
        try:
            scoring_output.entry_map = entry_map  # type: ignore[attr-defined]
        except Exception:
            pass

        return snapshot, scoring_output

    # ------------------------------------------------------------------
    # Private: snapshot assembly
    # ------------------------------------------------------------------

    def _build_snapshot(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        ms: Optional[Any],
        liq: Optional[Any],
        disp: Optional[Any],
        ob: Optional[Any],
        fvg: Optional[Any],
        sd: Optional[Any],
        poi: Optional[Any],
        engines_run: list[str],
        engines_failed: list[str],
        duration_ms: float,
    ) -> MarketSnapshot:
        """Assemble a :class:`~src.models.market_snapshot.MarketSnapshot`.

        Parameters
        ----------
        symbol:
            Instrument name.
        timeframe:
            Timeframe label.
        df:
            Source candle DataFrame.
        ms, liq, disp, ob, fvg, sd, poi:
            Engine results (may be ``None`` when an engine failed).
        engines_run:
            Names of engines that completed successfully.
        engines_failed:
            Names of engines that raised an exception.
        duration_ms:
            Pipeline wall-clock time in milliseconds.

        Returns
        -------
        MarketSnapshot
            Fully assembled snapshot.
        """
        current_price: float = 0.0
        candle_count: int = 0

        if df is not None and "close" in df.columns and len(df) > 0:
            current_price = float(df["close"].iloc[-1])
            candle_count  = len(df)

        snapshot_id = f"SNAP_{symbol}_{timeframe}_{int(time.time())}"

        return MarketSnapshot(
            snapshot_id=snapshot_id,
            symbol=symbol,
            timeframe=timeframe,
            captured_at=datetime.utcnow(),
            current_price=current_price,
            candle_count=candle_count,
            market_structure=ms,
            liquidity=liq,
            displacement=disp,
            order_blocks=ob,
            fvgs=fvg,
            supply_demand=sd,
            pois=poi,
            df=df,
            engines_run=list(engines_run),
            engines_failed=list(engines_failed),
            scan_duration_ms=duration_ms,
            is_complete=len(engines_failed) == 0,
        )


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_scanner(
    candle_provider: Any,
    config: Optional[dict] = None,
) -> TimeframeScanner:
    """Factory — return a configured :class:`TimeframeScanner`.

    Parameters
    ----------
    candle_provider:
        Data provider implementing ``get_candles`` and
        ``get_latest_price``.
    config:
        Optional configuration dict (see :class:`TimeframeScanner`).

    Returns
    -------
    TimeframeScanner
        Ready-to-use scanner instance.
    """
    return TimeframeScanner(candle_provider=candle_provider, config=config)
