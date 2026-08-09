from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

__all__ = ["setup_logging", "get_logger", "get_log_level", "ColoredFormatter"]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

_ANSI_COLORS: dict[int, str] = {
    logging.DEBUG:    "\033[37m",
    logging.INFO:     "\033[36m",
    logging.WARNING:  "\033[33m",
    logging.ERROR:    "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_ANSI_RESET: str = "\033[0m"

_CONSOLE_FORMAT: str = "{color}[{time}] [{level}] [{name}] {message}{reset}"
_FILE_FORMAT: str    = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_TIME_FORMAT: str    = "%H:%M:%S"

_MAX_BYTES: int  = 5 * 1024 * 1024   # 5 MB
_BACKUP_COUNT: int = 3

_LEVEL_MAP: dict[str, int] = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


# ─────────────────────────────────────────────
#  ColoredFormatter
# ─────────────────────────────────────────────

class ColoredFormatter(logging.Formatter):
    """A logging Formatter that applies ANSI color codes to console output.

    Colors are applied based on the log level:
        DEBUG    → white
        INFO     → cyan
        WARNING  → yellow
        ERROR    → red
        CRITICAL → bold red

    The formatter never raises — on any internal exception it falls back to
    a plain, uncolored representation of the log record.

    Example:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter())
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with ANSI color codes.

        Args:
            record: The log record to format.

        Returns:
            A formatted string with ANSI color prefix and reset suffix.
            Falls back to the default formatter output on any exception.
        """
        try:
            color = _ANSI_COLORS.get(record.levelno, "")
            # Format time manually to honour _TIME_FORMAT
            time_str = self.formatTime(record, _TIME_FORMAT)
            message = record.getMessage()
            # Include exception info if present
            if record.exc_info and not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                message = f"{message}\n{record.exc_text}"
            if record.stack_info:
                message = f"{message}\n{self.formatStack(record.stack_info)}"

            return _CONSOLE_FORMAT.format(
                color=color,
                time=time_str,
                level=record.levelname,
                name=record.name,
                message=message,
                reset=_ANSI_RESET,
            )
        except Exception:
            # Absolute fallback — never let the formatter crash the app
            try:
                return super().format(record)
            except Exception:
                return str(record)


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def get_log_level(level_str: str) -> int:
    """Convert a string log level name to its logging integer constant.

    Unrecognized strings return logging.INFO — this function never raises.

    Args:
        level_str: Case-insensitive level name, e.g. "DEBUG", "WARNING".

    Returns:
        The corresponding logging constant (e.g. logging.DEBUG = 10).
        Returns logging.INFO for any unrecognized input.

    Example:
        level = get_log_level("DEBUG")   # → 10
        level = get_log_level("banana")  # → 20 (INFO)
    """
    return _LEVEL_MAP.get(level_str.upper().strip(), logging.INFO)


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: str = "logs",
    log_filename: str = "smarttrader.log",
) -> None:
    """Configure the root logger for the entire SmartTraderBot application.

    Must be called exactly once from main.py before any other module logs.
    Calling it multiple times is safe — existing handlers are cleared first.

    Sets up:
    - A StreamHandler (console) with ANSI colored output via ColoredFormatter.
    - A RotatingFileHandler (file) with plain text output when log_to_file=True.
      Max 5 MB per file, 3 rotating backups.

    Args:
        level: Minimum log level to capture. One of "DEBUG", "INFO",
            "WARNING", "ERROR", "CRITICAL". Defaults to "INFO".
            Unrecognized values fall back to INFO.
        log_to_file: Whether to write logs to a rotating file in addition
            to the console. Defaults to True.
        log_dir: Directory path for log files. Created automatically if it
            does not exist. Defaults to "logs".
        log_filename: Name of the rotating log file. Defaults to
            "smarttrader.log".

    Example:
        setup_logging(level="DEBUG", log_to_file=True, log_dir="logs")
    """
    numeric_level = get_log_level(level)
    root_logger = logging.getLogger()

    # Clear any handlers added by previous calls (idempotent)
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            root_logger.removeHandler(handler)

    root_logger.setLevel(numeric_level)

    # ── Console handler ────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # ── File handler (optional) ────────────────────────────────────────
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        log_filepath = log_path / log_filename

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_filepath),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_formatter = logging.Formatter(
            fmt=_FILE_FORMAT,
            datefmt=_TIME_FORMAT,
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for use in any SmartTraderBot module.

    This is the only function that src/ modules should call to obtain
    a logger. setup_logging() in main.py configures the root logger
    once; all named loggers inherit that configuration automatically.

    Args:
        name: Logger name — pass __name__ from the calling module.
            This produces hierarchical names like "src.engine.liquidity_engine"
            which appear in log output for easy filtering.

    Returns:
        A logging.Logger instance bound to the given name.

    Example:
        from src.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Engine initialized.")
    """
    return logging.getLogger(name)