from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

__all__ = ["ScanScheduler", "ScanSchedulerError", "create_scheduler"]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_INTERVAL_SEC: float = 60.0
DEFAULT_MAX_RUNS: Optional[int] = None
MIN_INTERVAL_SEC: float = 5.0


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class ScanSchedulerError(Exception):
    """Raised when the scan scheduler encounters a configuration or runtime error.

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
#  ScanScheduler
# ─────────────────────────────────────────────

class ScanScheduler:
    """Runs MarketScanner on a configurable interval in a background thread.

    Supports one-shot execution (run_once) and continuous loop mode (start/stop).
    An optional callback is invoked after each scan so the dashboard or any
    downstream consumer can be refreshed without polling.

    The background thread is a daemon thread — it will not prevent the process
    from exiting. Sleep between scans is interruptible via threading.Event so
    stop() takes effect immediately without waiting for the full interval.

    Example:
        scheduler = create_scheduler(
            scanner=market_scanner,
            interval_sec=60.0,
            max_runs=10,
            on_scan_complete=lambda r: print(r.scan_id),
        )

        # Continuous mode
        with scheduler:
            time.sleep(600)

        # One-shot
        result = scheduler.run_once()
    """

    def __init__(
        self,
        scanner: Any,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        max_runs: Optional[int] = None,
        on_scan_complete: Optional[Callable[[Any], None]] = None,
    ) -> None:
        """Initialize the scheduler.

        Args:
            scanner: A MarketScanner instance with a .run() method.
            interval_sec: Seconds between consecutive scan runs. Must be >= MIN_INTERVAL_SEC.
            max_runs: Maximum number of scan runs before stopping automatically.
                None means run indefinitely.
            on_scan_complete: Optional callback invoked with the ScanResult after
                each successful scan. Exceptions in the callback are caught and logged.

        Raises:
            ScanSchedulerError: If interval_sec is below MIN_INTERVAL_SEC.
        """
        if interval_sec < MIN_INTERVAL_SEC:
            raise ScanSchedulerError(
                f"interval_sec must be >= {MIN_INTERVAL_SEC}s, got {interval_sec}s."
            )

        self._scanner = scanner
        self._interval_sec = interval_sec
        self._max_runs = max_runs
        self._on_scan_complete = on_scan_complete

        self._running: bool = False
        self._run_count: int = 0
        self._last_result: Optional[Any] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the continuous scan loop in a background daemon thread.

        If already running, logs a warning and returns without starting a
        second thread.
        """
        with self._lock:
            if self._running:
                self._logger.warning(
                    "ScanScheduler is already running — ignoring start() call."
                )
                return
            self._running = True
            self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._loop,
            name="ScanScheduler",
            daemon=True,
        )
        self._thread.start()

        self._logger.info(
            "ScanScheduler started — interval=%.1fs, max_runs=%s.",
            self._interval_sec,
            self._max_runs if self._max_runs is not None else "∞",
        )

    def stop(self) -> None:
        """Signal the background scan loop to stop after the current scan.

        Returns immediately — does not block until the thread finishes.
        The interruptible sleep ensures the thread wakes and exits promptly.
        """
        self._stop_event.set()
        with self._lock:
            self._running = False
        self._logger.info(
            "ScanScheduler stop requested — completed %d run(s).", self._run_count
        )

    # ── One-shot ──────────────────────────────────────────────────────────

    def run_once(self) -> Any:
        """Execute a single scan cycle synchronously.

        Calls scanner.run(), stores the result, increments the run counter,
        and invokes the completion callback if configured.

        Returns:
            The ScanResult returned by scanner.run().

        Raises:
            Any exception raised by scanner.run() is propagated to the caller.
            (Unlike _loop, run_once does not swallow exceptions.)
        """
        self._logger.info("Starting scan run #%d.", self._run_count + 1)
        result = self._scanner.run()

        with self._lock:
            self._run_count += 1
            self._last_result = result

        self._logger.info(
            "Scan run #%d complete — scan_id=%s, duration=%.0fms, "
            "success=%d, failed=%d, dashboard=%d.",
            self._run_count,
            getattr(result, "scan_id", "?"),
            getattr(result, "total_duration_ms", 0.0),
            getattr(result, "successful_scans", 0),
            getattr(result, "failed_scans", 0),
            getattr(result, "total_dashboard_results", 0),
        )

        if self._on_scan_complete is not None:
            try:
                self._on_scan_complete(result)
            except Exception as exc:
                self._logger.warning(
                    "on_scan_complete callback raised an exception: %s", exc
                )

        return result

    # ── State Accessors ───────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Return True if the background scan loop is currently active.

        Returns:
            True when the scheduler is running.
        """
        with self._lock:
            return self._running

    def get_last_result(self) -> Optional[Any]:
        """Return the most recent ScanResult, or None if no scan has run yet.

        Returns:
            The last ScanResult produced by run_once() or the _loop.
        """
        with self._lock:
            return self._last_result

    def get_run_count(self) -> int:
        """Return the total number of scan runs completed so far.

        Returns:
            Count of completed runs (successful or failed).
        """
        with self._lock:
            return self._run_count

    # ── Context Manager ───────────────────────────────────────────────────

    def __enter__(self) -> ScanScheduler:
        """Enter the context manager by starting the scan loop.

        Returns:
            This ScanScheduler instance.
        """
        self.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """Exit the context manager by stopping the scan loop.

        Args:
            exc_type: Exception type, if one occurred.
            exc_val: Exception value, if one occurred.
            exc_tb: Exception traceback, if one occurred.

        Returns:
            False — exceptions are not suppressed.
        """
        self.stop()
        return False

    # ── Private: Background Loop ──────────────────────────────────────────

    def _loop(self) -> None:
        """Background thread target — runs scanner repeatedly until stopped.

        Executes run_once(), checks the max_runs limit, then waits
        interval_sec before the next run. The wait is interruptible via
        _stop_event so stop() takes effect without a full interval delay.

        All exceptions from scanner.run() are caught, logged, and the loop
        continues to the next interval to avoid crashing the background thread.
        """
        self._logger.debug("ScanScheduler background loop started.")

        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                self._logger.error(
                    "scanner.run() raised an unexpected exception on run #%d: %s",
                    self._run_count + 1,
                    exc,
                )

            # Check max_runs limit
            with self._lock:
                run_count = self._run_count
                max_runs = self._max_runs

            if max_runs is not None and run_count >= max_runs:
                self._logger.info(
                    "ScanScheduler reached max_runs=%d — stopping.", max_runs
                )
                with self._lock:
                    self._running = False
                self._stop_event.set()
                break

            # Interruptible sleep — wakes immediately on stop()
            self._logger.debug(
                "Waiting %.1fs before next scan (run #%d complete).",
                self._interval_sec,
                run_count,
            )
            interrupted = self._stop_event.wait(timeout=self._interval_sec)
            if interrupted:
                self._logger.debug("ScanScheduler sleep interrupted by stop signal.")
                break

        self._logger.info(
            "ScanScheduler background loop exited after %d run(s).", self._run_count
        )


# ─────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────

def create_scheduler(
    scanner: Any,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    max_runs: Optional[int] = None,
    on_scan_complete: Optional[Callable[[Any], None]] = None,
) -> ScanScheduler:
    """Factory function — create and return a configured ScanScheduler.

    Args:
        scanner: A MarketScanner instance with a .run() method.
        interval_sec: Seconds between consecutive scan runs. Must be >= 5.0.
        max_runs: Maximum number of runs before auto-stopping. None = forever.
        on_scan_complete: Optional callback invoked with the ScanResult after
            each scan. Callback exceptions are caught and logged.

    Returns:
        A ready-to-use ScanScheduler instance.

    Raises:
        ScanSchedulerError: If interval_sec is below MIN_INTERVAL_SEC.
    """
    return ScanScheduler(
        scanner=scanner,
        interval_sec=interval_sec,
        max_runs=max_runs,
        on_scan_complete=on_scan_complete,
    )