from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.models.scan_result import SymbolTimeframePair, TimeframeScanResult
from src.scoring.score_classifier import ScoreClassifier

__all__ = ["MarketScanner", "MarketScannerError", "ScanResult", "create_scanner"]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

_DEFAULT_MAX_WORKERS: int = 1
_DEFAULT_MIN_SCORE: float = 0.0


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class MarketScannerError(Exception):
    """Raised when the market scanner encounters an unrecoverable error.

    Attributes:
        message: Human-readable description of the failure.
        cause: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        """Initialize with a message and optional root cause.

        Args:
            message: Description of the failure.
            cause: Optional underlying exception.
        """
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        """Return a string representation including the cause if present.

        Returns:
            Formatted error string.
        """
        base = super().__str__()
        if self.cause is not None:
            return f"{base} | Caused by: {type(self.cause).__name__}: {self.cause}"
        return base


# ─────────────────────────────────────────────
#  ScanResult
# ─────────────────────────────────────────────

@dataclass
class ScanResult:
    """Top-level container for one complete scan cycle across all symbols and timeframes.

    Produced by MarketScanner.run() and handed directly to the dashboard renderer
    and to main.py as the final output of a scan cycle.

    Attributes:
        scan_id: Unique identifier in format "SCAN_{unix_timestamp}".
        started_at: Timestamp when the scan cycle started.
        finished_at: Timestamp when the scan cycle finished.
        total_duration_ms: Total wall-clock time in milliseconds.
        symbols_scanned: Unique symbols included in this scan.
        timeframes_scanned: Unique timeframes included in this scan.
        timeframe_results: All individual TimeframeScanResult objects.
        all_score_results: Flat list of all ScoreResult objects across symbols/TFs.
        dashboard_results: Filtered, sorted (desc) show_on_dashboard=True results.
        total_pois_found: Total POIs detected across all symbols and timeframes.
        total_dashboard_results: Count of results in dashboard_results.
        successful_scans: Count of TimeframeScanResult where success=True.
        failed_scans: Count of TimeframeScanResult where success=False.
        scan_errors: Collected error messages from all failed scans.
    """

    scan_id: str
    started_at: datetime
    finished_at: datetime
    total_duration_ms: float
    symbols_scanned: list[str] = field(default_factory=list)
    timeframes_scanned: list[str] = field(default_factory=list)
    timeframe_results: list[TimeframeScanResult] = field(default_factory=list)
    all_score_results: list[Any] = field(default_factory=list)
    dashboard_results: list[Any] = field(default_factory=list)
    total_pois_found: int = 0
    total_dashboard_results: int = 0
    successful_scans: int = 0
    failed_scans: int = 0
    scan_errors: list[str] = field(default_factory=list)

    @property
    def has_results(self) -> bool:
        """Return True if there are any dashboard-worthy results.

        Returns:
            True when dashboard_results is non-empty.
        """
        return len(self.dashboard_results) > 0

    @property
    def top_result(self) -> Optional[Any]:
        """Return the highest-scored dashboard result, if any.

        Returns:
            First item in dashboard_results (highest score), or None.
        """
        return self.dashboard_results[0] if self.dashboard_results else None

    @property
    def success_rate(self) -> float:
        """Return the fraction of scans that completed successfully.

        Returns:
            successful_scans / total_scans if total > 0, else 0.0.
        """
        total = self.successful_scans + self.failed_scans
        return self.successful_scans / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize this ScanResult to a JSON-safe dictionary.

        datetime fields are ISO 8601 strings. Nested objects are serialized
        via their own to_dict(). Never raises an exception.

        Returns:
            Dictionary containing the complete scan cycle output.
        """
        try:
            return {
                "scan_id": self.scan_id,
                "started_at": self.started_at.isoformat(),
                "finished_at": self.finished_at.isoformat(),
                "total_duration_ms": self.total_duration_ms,
                "symbols_scanned": list(self.symbols_scanned),
                "timeframes_scanned": list(self.timeframes_scanned),
                "timeframe_results": [r.to_dict() for r in self.timeframe_results],
                "all_score_results": [r.to_dict() for r in self.all_score_results],
                "dashboard_results": [r.to_dict() for r in self.dashboard_results],
                "total_pois_found": self.total_pois_found,
                "total_dashboard_results": self.total_dashboard_results,
                "successful_scans": self.successful_scans,
                "failed_scans": self.failed_scans,
                "scan_errors": list(self.scan_errors),
                "has_results": self.has_results,
                "top_result": (
                    self.top_result.to_dict() if self.top_result is not None else None
                ),
                "success_rate": self.success_rate,
            }
        except Exception:
            return {}


# ─────────────────────────────────────────────
#  MarketScanner
# ─────────────────────────────────────────────

class MarketScanner:
    """Orchestrates scanning across all configured symbols and timeframes.

    Delegates individual pair analysis to TimeframeScanner, collects the
    results, applies dashboard filtering via ScoreClassifier, and assembles
    the final ScanResult. Supports both sequential and concurrent execution.

    The run() method never raises — it always returns a valid ScanResult,
    even if all individual scans fail.

    Example:
        scanner = create_scanner(
            timeframe_scanner=tf_scanner,
            symbol_provider=provider,
            config={"max_workers": 4},
        )
        result = scanner.run()
        print(result.success_rate)
        print(len(result.dashboard_results))
    """

    def __init__(
        self,
        timeframe_scanner: Any,
        symbol_provider: Any,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the market scanner.

        Args:
            timeframe_scanner: A TimeframeScanner instance with a .scan() method.
            symbol_provider: A SymbolProvider instance with a .get_pairs() method.
            config: Optional configuration dict. Supported keys:
                - "max_workers" (int): Number of threads for concurrent scanning.
                  Default is 1 (sequential).
                - "min_score_threshold" (float): Exclude ScoreResults below this
                  total_score. Default is 0.0 (keep all).
        """
        self._timeframe_scanner = timeframe_scanner
        self._symbol_provider = symbol_provider
        self._classifier = ScoreClassifier()
        self._last_result: Optional[ScanResult] = None
        self._logger = logging.getLogger(__name__)

        cfg = config or {}
        self._max_workers: int = int(cfg.get("max_workers", _DEFAULT_MAX_WORKERS))
        self._min_score_threshold: float = float(
            cfg.get("min_score_threshold", _DEFAULT_MIN_SCORE)
        )

    # ── Public API ────────────────────────────────────────────────────────

    def run(self) -> ScanResult:
        """Execute a full scan cycle across all configured symbols and timeframes.

        Retrieves pairs from the symbol provider, scans each pair via
        TimeframeScanner (sequentially or concurrently based on max_workers),
        assembles and returns a ScanResult.

        This method never raises — all errors are captured and included in
        the returned ScanResult.scan_errors list.

        Returns:
            ScanResult containing all results, stats, and dashboard data.
        """
        started_at = datetime.utcnow()

        try:
            pairs: list[SymbolTimeframePair] = self._symbol_provider.get_pairs()
        except Exception as exc:
            self._logger.error("Failed to retrieve pairs from symbol provider: %s", exc)
            pairs = []

        self._logger.info(
            "Starting scan cycle — %d pair(s), max_workers=%d.",
            len(pairs),
            self._max_workers,
        )

        timeframe_results: list[TimeframeScanResult] = []

        if self._max_workers <= 1:
            for pair in pairs:
                result = self._scan_pair(pair)
                timeframe_results.append(result)
        else:
            timeframe_results = self._scan_concurrent(pairs)

        scan_result = self._build_scan_result(timeframe_results, started_at)
        self._last_result = scan_result

        self._logger.info(
            "Scan cycle complete — scan_id=%s, duration=%.0fms, "
            "success=%d, failed=%d, dashboard=%d.",
            scan_result.scan_id,
            scan_result.total_duration_ms,
            scan_result.successful_scans,
            scan_result.failed_scans,
            scan_result.total_dashboard_results,
        )

        return scan_result

    def run_single(self, symbol: str, timeframe: str) -> TimeframeScanResult:
        """Scan a single symbol/timeframe pair.

        Useful for targeted testing or on-demand scanning of one instrument.

        Args:
            symbol: Instrument symbol (e.g. "XAUUSD").
            timeframe: Chart timeframe string (e.g. "H1").

        Returns:
            TimeframeScanResult for the requested pair.
        """
        pair = SymbolTimeframePair(
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            display_name=f"{symbol.upper()} {timeframe.upper()}",
        )
        return self._scan_pair(pair)

    def get_last_result(self) -> Optional[ScanResult]:
        """Return the most recent ScanResult produced by run().

        Returns:
            The last ScanResult, or None if run() has never been called.
        """
        return self._last_result

    # ── Private: Scanning ─────────────────────────────────────────────────

    def _scan_pair(self, pair: Any) -> TimeframeScanResult:
        """Scan one symbol/timeframe pair and return its result.

        Delegates to timeframe_scanner.scan(). All exceptions are caught
        and converted into a failed TimeframeScanResult.

        Args:
            pair: SymbolTimeframePair to scan.

        Returns:
            TimeframeScanResult — never raises.
        """
        try:
            result: TimeframeScanResult = self._timeframe_scanner.scan(pair)
            status = "✓" if result.success else "✗"
            self._logger.info(
                "[%s] %s — duration=%.0fms%s",
                status,
                pair.display_name,
                result.scan_duration_ms,
                f" | error: {result.error_message}" if not result.success else "",
            )
            return result
        except Exception as exc:
            self._logger.warning(
                "Unexpected exception scanning %s: %s", pair.display_name, exc
            )
            # Build a minimal failed result to keep the pipeline intact
            return TimeframeScanResult(
                symbol=pair.symbol,
                timeframe=pair.timeframe,
                scanned_at=datetime.utcnow(),
                success=False,
                error_message=f"Unhandled exception: {exc}",
                snapshot=None,
                scoring_output=None,
                scan_duration_ms=0.0,
            )

    def _scan_concurrent(
        self, pairs: list[Any]
    ) -> list[TimeframeScanResult]:
        """Scan all pairs concurrently using a thread pool.

        Results are returned in completion order; the caller re-sorts if needed.

        Args:
            pairs: List of SymbolTimeframePair objects to scan.

        Returns:
            List of TimeframeScanResult objects (order may differ from input).
        """
        results: list[TimeframeScanResult] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_pair = {
                executor.submit(self._scan_pair, pair): pair for pair in pairs
            }
            for future in as_completed(future_to_pair):
                pair = future_to_pair[future]
                try:
                    result = future.result()
                except Exception as exc:
                    self._logger.error(
                        "Future for %s raised unexpectedly: %s", pair.display_name, exc
                    )
                    result = TimeframeScanResult(
                        symbol=pair.symbol,
                        timeframe=pair.timeframe,
                        scanned_at=datetime.utcnow(),
                        success=False,
                        error_message=f"Future exception: {exc}",
                        snapshot=None,
                        scoring_output=None,
                        scan_duration_ms=0.0,
                    )
                results.append(result)

        return results

    # ── Private: Result Assembly ──────────────────────────────────────────

    def _build_scan_result(
        self,
        timeframe_results: list[TimeframeScanResult],
        started_at: datetime,
    ) -> ScanResult:
        """Assemble a ScanResult from all collected TimeframeScanResults.

        Extracts ScoreResults from successful scans, applies score threshold
        and dashboard filtering, and computes all aggregate statistics.

        Args:
            timeframe_results: All TimeframeScanResult objects from this cycle.
            started_at: Timestamp when the scan cycle started.

        Returns:
            Fully populated ScanResult.
        """
        finished_at = datetime.utcnow()
        duration_ms = (finished_at - started_at).total_seconds() * 1000.0

        # Collect flat score results from all successful scans
        all_score_results: list[Any] = []
        successful_scans = 0
        failed_scans = 0
        scan_errors: list[str] = []
        symbols_seen: set[str] = set()
        timeframes_seen: set[str] = set()

        for tf_result in timeframe_results:
            symbols_seen.add(tf_result.symbol)
            timeframes_seen.add(tf_result.timeframe)

            if tf_result.success:
                successful_scans += 1
                if tf_result.scoring_output is not None:
                    try:
                        all_score_results.extend(
                            tf_result.scoring_output.all_results
                        )
                    except Exception as exc:
                        self._logger.debug(
                            "Could not extract all_results from scoring_output: %s", exc
                        )
            else:
                failed_scans += 1
                if tf_result.error_message:
                    scan_errors.append(
                        f"{tf_result.symbol} {tf_result.timeframe}: {tf_result.error_message}"
                    )

        # Apply min_score_threshold
        if self._min_score_threshold > _DEFAULT_MIN_SCORE:
            all_score_results = [
                r for r in all_score_results
                if getattr(r, "total_score", 0.0) >= self._min_score_threshold
            ]

        # Dashboard filtering via ScoreClassifier
        try:
            dashboard_results: list[Any] = self._classifier.filter_dashboard(
                all_score_results
            )
        except Exception as exc:
            self._logger.warning(
                "ScoreClassifier.filter_dashboard failed: %s — using empty list.", exc
            )
            dashboard_results = []

        # Sort dashboard results by total_score descending
        try:
            dashboard_results.sort(
                key=lambda r: getattr(r, "total_score", 0.0), reverse=True
            )
        except Exception as exc:
            self._logger.debug("Could not sort dashboard_results: %s", exc)

        total_pois_found = len(all_score_results)

        return ScanResult(
            scan_id=f"SCAN_{int(time.time())}",
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=duration_ms,
            symbols_scanned=sorted(symbols_seen),
            timeframes_scanned=sorted(
                timeframes_seen,
                key=lambda tf: (len(tf), tf),
            ),
            timeframe_results=timeframe_results,
            all_score_results=all_score_results,
            dashboard_results=dashboard_results,
            total_pois_found=total_pois_found,
            total_dashboard_results=len(dashboard_results),
            successful_scans=successful_scans,
            failed_scans=failed_scans,
            scan_errors=scan_errors,
        )


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_scanner(
    timeframe_scanner: Any,
    symbol_provider: Any,
    config: Optional[dict[str, Any]] = None,
) -> MarketScanner:
    """Factory function — create and return a configured MarketScanner.

    Args:
        timeframe_scanner: A TimeframeScanner instance with a .scan() method.
        symbol_provider: A SymbolProvider instance with a .get_pairs() method.
        config: Optional configuration dict. Supported keys:
            - "max_workers" (int): Threads for concurrent scanning. Default: 1.
            - "min_score_threshold" (float): Minimum score to include. Default: 0.0.

    Returns:
        A ready-to-use MarketScanner instance.
    """
    return MarketScanner(
        timeframe_scanner=timeframe_scanner,
        symbol_provider=symbol_provider,
        config=config,
    )