from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

from src.utils.logger import get_logger, setup_logging
from src.utils.time_utils import (
    format_datetime,
    format_duration_ms,
    get_next_scan_time,
    seconds_until,
    utcnow,
)
from src.utils.validators import validate_symbols, validate_timeframes

# ─────────────────────────────────────────────
#  Default configuration
# ─────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "symbols":               ["XAUUSD"],
    "timeframes":            ["M1"],
    "interval_seconds":      60,
    "run_mode":              "single",
    "log_level":             "INFO",
    "log_to_file":           True,
    "log_dir":               "logs",
    "log_filename":          "smarttrader.log",
    "output_dir":            "output_files",
    "dashboard_filename":    "dashboard.html",
    "auto_refresh_seconds":  60,
    "dashboard_title":       "SmartTraderBot — Market Scanner",
}

_DEFAULT_CONFIG_PATH = Path("config.yaml")


# ─────────────────────────────────────────────
#  Config loading
# ─────────────────────────────────────────────

def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from a YAML file and merge with defaults.

    If the file is missing, unreadable, or YAML is not installed,
    a warning is printed and the default configuration is returned.
    Values present in the file override the corresponding defaults.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dict containing the merged configuration. Never raises.
    """
    cfg: dict[str, Any] = dict(DEFAULTS)

    if not _YAML_AVAILABLE:
        print(
            "WARNING: PyYAML is not installed — using default configuration.",
            file=sys.stderr,
        )
        return cfg

    if not config_path.exists():
        print(
            f"WARNING: Config file '{config_path}' not found — using defaults.",
            file=sys.stderr,
        )
        return cfg

    try:
        with open(config_path, encoding="utf-8") as fh:
            raw: Any = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            print(
                f"WARNING: Config file '{config_path}' has unexpected structure "
                "— using defaults.",
                file=sys.stderr,
            )
            return cfg

        # Flatten nested YAML structure into the flat DEFAULTS shape
        scanner_cfg   = raw.get("scanner",   {}) or {}
        logging_cfg   = raw.get("logging",   {}) or {}
        dashboard_cfg = raw.get("dashboard", {}) or {}

        cfg["symbols"]              = scanner_cfg.get("symbols",          cfg["symbols"])
        cfg["timeframes"]           = scanner_cfg.get("timeframes",        cfg["timeframes"])
        cfg["interval_seconds"]     = scanner_cfg.get("interval_seconds",  cfg["interval_seconds"])
        cfg["run_mode"]             = scanner_cfg.get("run_mode",          cfg["run_mode"])

        cfg["log_level"]            = logging_cfg.get("level",             cfg["log_level"])
        cfg["log_to_file"]          = logging_cfg.get("log_to_file",       cfg["log_to_file"])
        cfg["log_dir"]              = logging_cfg.get("log_dir",           cfg["log_dir"])
        cfg["log_filename"]         = logging_cfg.get("log_filename",      cfg["log_filename"])

        cfg["output_dir"]           = dashboard_cfg.get("output_dir",              cfg["output_dir"])
        cfg["dashboard_filename"]   = dashboard_cfg.get("filename",                cfg["dashboard_filename"])
        cfg["auto_refresh_seconds"] = dashboard_cfg.get("auto_refresh_seconds",    cfg["auto_refresh_seconds"])
        cfg["dashboard_title"]      = dashboard_cfg.get("title",                   cfg["dashboard_title"])

    except Exception as exc:
        print(
            f"WARNING: Could not parse config file '{config_path}': {exc} "
            "— using defaults.",
            file=sys.stderr,
        )

    return cfg


# ─────────────────────────────────────────────
#  CLI argument parsing
# ─────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser for SmartTraderBot.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="smarttraderbot",
        description="SmartTraderBot — Market Scanner & Confluence Engine",
    )
    parser.add_argument(
        "--mode",
        choices=["single", "loop"],
        default=None,
        help="Run mode: 'single' (one scan then exit) or 'loop' (continuous).",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        metavar="SYMBOL",
        help="Override configured symbols with a single symbol (e.g. XAUUSD).",
    )
    parser.add_argument(
        "--timeframe",
        default=None,
        metavar="TF",
        help="Override configured timeframes with a single timeframe (e.g. H1).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Override the scan interval in seconds (loop mode only).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG_PATH,
        metavar="PATH",
        help="Path to the YAML configuration file. Default: config.yaml.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        dest="log_level",
        help="Override the log level from config.",
    )
    return parser


def apply_cli_overrides(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    """Apply CLI argument overrides onto the configuration dict in place.

    Args:
        cfg: Mutable configuration dict to update.
        args: Parsed CLI arguments from argparse.
    """
    if args.mode is not None:
        cfg["run_mode"] = args.mode
    if args.symbol is not None:
        cfg["symbols"] = [args.symbol]
    if args.timeframe is not None:
        cfg["timeframes"] = [args.timeframe]
    if args.interval is not None:
        cfg["interval_seconds"] = args.interval
    if args.log_level is not None:
        cfg["log_level"] = args.log_level


# ─────────────────────────────────────────────
#  Scanner / dashboard construction
# ─────────────────────────────────────────────

def build_scanner(cfg: dict[str, Any], symbols: list[str], timeframes: list[str]) -> Any:
    """Instantiate and return the MarketScanner with the given configuration.

    Args:
        cfg: Merged configuration dict.
        symbols: Validated list of symbols to scan.
        timeframes: Validated list of timeframes to scan.

    Returns:
        Configured MarketScanner instance.
    """
    from src.scanner.market_scanner import MarketScanner

    scanner_cfg = {
        "symbols":          symbols,
        "timeframes":       timeframes,
        "interval_seconds": cfg["interval_seconds"],
        "run_mode":         cfg["run_mode"],
    }
    return MarketScanner(config=scanner_cfg)


def build_dashboard(cfg: dict[str, Any]) -> Any:
    """Instantiate and return the Dashboard with the given configuration.

    Args:
        cfg: Merged configuration dict.

    Returns:
        Configured Dashboard instance.
    """
    from src.dashboard.dashboard import Dashboard

    return Dashboard(
        output_dir=cfg["output_dir"],
        filename=cfg["dashboard_filename"],
        auto_refresh_seconds=cfg["auto_refresh_seconds"],
    )


# ─────────────────────────────────────────────
#  Run modes
# ─────────────────────────────────────────────

def run_single(
    scanner: Any,
    dashboard: Any,
    cfg: dict[str, Any],
    logger: Any,
) -> None:
    """Execute one full scan cycle and save the dashboard.

    Args:
        scanner: MarketScanner instance.
        dashboard: Dashboard instance.
        cfg: Merged configuration dict.
        logger: Application logger.
    """
    logger.info("Starting single scan …")
    start = utcnow()

    outputs = scanner.scan_all()

    duration_ms = (utcnow() - start).total_seconds() * 1_000
    logger.info(
        "Scan complete — %d output(s) in %s.",
        len(outputs),
        format_duration_ms(duration_ms),
    )

    path = dashboard.render_and_save(outputs, title=cfg["dashboard_title"])
    if path:
        logger.info("Dashboard saved: %s", path)
    else:
        logger.warning("Dashboard was not saved (render_and_save returned empty path).")


def run_loop(
    scanner: Any,
    dashboard: Any,
    cfg: dict[str, Any],
    logger: Any,
) -> None:
    """Run scan cycles continuously until interrupted.

    Sleeps between scans so that each cycle starts exactly
    interval_seconds after the previous one began.

    Args:
        scanner: MarketScanner instance.
        dashboard: Dashboard instance.
        cfg: Merged configuration dict.
        logger: Application logger.
    """
    interval_seconds = int(cfg["interval_seconds"])
    logger.info(
        "Entering loop mode — scan interval: %ds. Press Ctrl+C to stop.",
        interval_seconds,
    )

    while True:
        start_time = utcnow()
        logger.info(
            "Scan cycle starting at %s …",
            format_datetime(start_time, "%H:%M:%S"),
        )

        try:
            outputs = scanner.scan_all()
            duration_ms = (utcnow() - start_time).total_seconds() * 1_000
            logger.info(
                "Scan complete — %d output(s) in %s.",
                len(outputs),
                format_duration_ms(duration_ms),
            )

            path = dashboard.render_and_save(outputs, title=cfg["dashboard_title"])
            if path:
                logger.info("Dashboard saved: %s", path)
            else:
                logger.warning("Dashboard was not saved.")

        except Exception as exc:
            logger.error("Error during scan cycle: %s", exc)

        next_scan = get_next_scan_time(start_time, interval_seconds)
        sleep_secs = seconds_until(next_scan)
        if sleep_secs > 0:
            logger.info("Next scan in %.1fs.", sleep_secs)
            time.sleep(sleep_secs)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def main() -> None:
    """Entry point — orchestrates config loading, validation, and scan execution.

    Parses CLI arguments, loads and merges configuration, sets up logging,
    validates symbols/timeframes, builds the scanner and dashboard, then
    runs in either single or loop mode.

    Exits with code 0 on success or clean shutdown.
    Exits with code 1 on a fatal setup error.
    """
    # ── Parse CLI ─────────────────────────────────────────────────────────
    parser = build_arg_parser()
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────
    cfg = load_config(args.config)
    apply_cli_overrides(cfg, args)

    # ── Setup logging (must be first after config) ────────────────────────
    setup_logging(
        level=cfg["log_level"],
        log_to_file=cfg["log_to_file"],
        log_dir=cfg["log_dir"],
        log_filename=cfg["log_filename"],
    )
    logger = get_logger(__name__)
    logger.info("SmartTraderBot starting up.")
    logger.info("Config loaded from: %s", args.config)

    # ── Validate symbols and timeframes ───────────────────────────────────
    raw_symbols: list[str] = cfg.get("symbols") or []
    raw_timeframes: list[str] = cfg.get("timeframes") or []

    valid_symbols, invalid_symbols = validate_symbols(raw_symbols)
    valid_timeframes, invalid_timeframes = validate_timeframes(raw_timeframes)

    for sym in invalid_symbols:
        logger.warning("Invalid symbol skipped: '%s'", sym)
    for tf in invalid_timeframes:
        logger.warning("Invalid timeframe skipped: '%s'", tf)

    if not valid_symbols:
        logger.error("No valid symbols configured — cannot proceed. Exiting.")
        sys.exit(1)

    if not valid_timeframes:
        logger.error("No valid timeframes configured — cannot proceed. Exiting.")
        sys.exit(1)

    logger.info("Symbols: %s", valid_symbols)
    logger.info("Timeframes: %s", valid_timeframes)

    # ── Build scanner and dashboard ───────────────────────────────────────
    try:
        scanner = build_scanner(cfg, valid_symbols, valid_timeframes)
        dashboard = build_dashboard(cfg)
    except Exception as exc:
        logger.error("Failed to initialise scanner or dashboard: %s", exc)
        sys.exit(1)

    # ── Execute run mode ──────────────────────────────────────────────────
    run_mode: str = str(cfg.get("run_mode", "single")).strip().lower()
    logger.info("Run mode: %s", run_mode)

    try:
        if run_mode == "loop":
            run_loop(scanner, dashboard, cfg, logger)
    elif run_mode in ("single", "test"):
        run_single(scanner, dashboard, cfg, logger)
    else:
        logger.warning("Unknown run_mode '%s' — falling back to single.", run_mode)
        run_single(scanner, dashboard, cfg, logger)
        else:
            run_single(scanner, dashboard, cfg, logger)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C). Exiting cleanly.")
        sys.exit(0)

    except Exception as exc:
        logger.error("Unexpected fatal error: %s", exc)
        sys.exit(1)

    logger.info("SmartTraderBot finished. Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    main()