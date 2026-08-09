from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

__all__ = [
    "MT5ConnectionConfig",
    "MT5ConnectionError",
    "MT5Connection",
    "create_connection",
    "MT5_AVAILABLE",
]

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_TIMEOUT_SEC: int = 30
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SEC: float = 2.0


# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────

@dataclass
class MT5ConnectionConfig:
    """Configuration parameters for a MetaTrader 5 terminal connection.

    Attributes:
        login: MT5 account login number.
        password: MT5 account password.
        server: MT5 broker server name (e.g. "MetaQuotes-Demo").
        path: Absolute path to terminal64.exe. Auto-detected by MT5 if None.
        timeout_sec: Connection timeout in seconds.
        max_retries: Maximum number of connection attempts before raising.
        retry_delay_sec: Seconds to wait between retry attempts.
        portable: Whether to run MT5 terminal in portable mode.
    """

    login: int
    password: str
    server: str
    path: Optional[str] = field(default=None)
    timeout_sec: int = field(default=DEFAULT_TIMEOUT_SEC)
    max_retries: int = field(default=DEFAULT_MAX_RETRIES)
    retry_delay_sec: float = field(default=DEFAULT_RETRY_DELAY_SEC)
    portable: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate all connection parameters.

        Raises:
            ValueError: If any field contains an invalid value.
        """
        if self.login <= 0:
            raise ValueError(f"login must be > 0, got {self.login}.")
        if not self.password:
            raise ValueError("password must not be empty.")
        if not self.server:
            raise ValueError("server must not be empty.")
        if self.timeout_sec <= 0:
            raise ValueError(f"timeout_sec must be > 0, got {self.timeout_sec}.")
        if self.max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got {self.max_retries}.")
        if self.retry_delay_sec < 0.0:
            raise ValueError(
                f"retry_delay_sec must be >= 0.0, got {self.retry_delay_sec}."
            )


# ─────────────────────────────────────────────
#  Custom Exception
# ─────────────────────────────────────────────

class MT5ConnectionError(Exception):
    """Raised when a MetaTrader 5 connection attempt fails.

    Attributes:
        message: Human-readable description of the failure.
        cause: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        """Initialize with a message and optional root cause.

        Args:
            message: Description of the connection failure.
            cause: Optional underlying exception that caused this error.
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
#  Connection Manager
# ─────────────────────────────────────────────

class MT5Connection:
    """Manages the MetaTrader 5 terminal connection lifecycle.

    Handles initializing the MT5 terminal, verifying connection status,
    retrying on failure, and shutting down gracefully. Supports use as
    a context manager.

    This class is thread-safe: the internal connected flag is protected
    by a threading.Lock.

    Example:
        config = MT5ConnectionConfig(
            login=12345678,
            password="secret",
            server="MetaQuotes-Demo",
        )

        with MT5Connection(config) as conn:
            info = conn.get_account_info()
    """

    def __init__(self, config: MT5ConnectionConfig) -> None:
        """Initialize the connection manager with the given configuration.

        Args:
            config: Connection parameters for the MT5 terminal.
        """
        self._config = config
        self._connected: bool = False
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Initialize the MT5 terminal and establish a connection.

        Attempts to connect up to `config.max_retries` times, waiting
        `config.retry_delay_sec` seconds between each attempt.

        Returns:
            True if the connection was established successfully.

        Raises:
            MT5ConnectionError: If MT5 is not available (non-Windows),
                or if all retry attempts are exhausted.
        """
        if not MT5_AVAILABLE:
            msg = (
                "MetaTrader5 package not available. "
                "Run on Windows with MT5 installed."
            )
            self._logger.error(msg)
            raise MT5ConnectionError(msg)

        last_error: Any = None

        for attempt in range(1, self._config.max_retries + 1):
            self._logger.info(
                "MT5 connection attempt %d/%d to server '%s' (login=%d).",
                attempt,
                self._config.max_retries,
                self._config.server,
                self._config.login,
            )

            init_kwargs: dict[str, Any] = {
                "login": self._config.login,
                "password": self._config.password,
                "server": self._config.server,
                "timeout": self._config.timeout_sec * 1000,  # MT5 expects milliseconds
                "portable": self._config.portable,
            }
            if self._config.path is not None:
                init_kwargs["path"] = self._config.path

            try:
                success = mt5.initialize(**init_kwargs)  # type: ignore[union-attr]
            except Exception as exc:
                self._logger.warning(
                    "MT5 initialize raised an exception on attempt %d: %s",
                    attempt,
                    exc,
                )
                last_error = exc
                if attempt < self._config.max_retries:
                    time.sleep(self._config.retry_delay_sec)
                continue

            if success:
                with self._lock:
                    self._connected = True

                account = mt5.account_info()  # type: ignore[union-attr]
                account_repr = (
                    f"login={account.login}, name={account.name}, "
                    f"server={account.server}, balance={account.balance}"
                    if account is not None
                    else "account info unavailable"
                )
                self._logger.info(
                    "MT5 connected successfully. Account: %s", account_repr
                )
                return True

            last_error = mt5.last_error()  # type: ignore[union-attr]
            self._logger.warning(
                "MT5 initialize failed on attempt %d/%d. Error: %s",
                attempt,
                self._config.max_retries,
                last_error,
            )

            if attempt < self._config.max_retries:
                time.sleep(self._config.retry_delay_sec)

        with self._lock:
            self._connected = False

        raise MT5ConnectionError(
            f"Failed to connect to MT5 after {self._config.max_retries} attempt(s). "
            f"Last error: {last_error}"
        )

    def disconnect(self) -> None:
        """Shut down the MT5 terminal connection gracefully.

        Safe to call even if not currently connected. Sets the internal
        connected flag to False regardless of MT5 availability.
        """
        with self._lock:
            was_connected = self._connected
            self._connected = False

        if was_connected and MT5_AVAILABLE:
            try:
                mt5.shutdown()  # type: ignore[union-attr]
                self._logger.info(
                    "MT5 disconnected from server '%s' (login=%d).",
                    self._config.server,
                    self._config.login,
                )
            except Exception as exc:
                self._logger.warning("MT5 shutdown raised an exception: %s", exc)
        else:
            self._logger.info("MT5 disconnect called (was not connected).")

    def is_connected(self) -> bool:
        """Check whether the MT5 terminal connection is currently active.

        Performs a lightweight live check via terminal_info() when MT5
        is available, in addition to verifying the internal flag.

        Returns:
            True if connected and the terminal is reachable.
        """
        with self._lock:
            flag = self._connected

        if not flag:
            return False

        if MT5_AVAILABLE:
            try:
                return mt5.terminal_info() is not None  # type: ignore[union-attr]
            except Exception:
                return False

        return flag

    def get_account_info(self) -> Optional[dict[str, Any]]:
        """Retrieve the current MT5 account information.

        Returns:
            A dictionary of account fields, or None if not connected
            or if the call fails.
        """
        if not self.is_connected():
            self._logger.debug("get_account_info called while not connected.")
            return None

        try:
            info = mt5.account_info()  # type: ignore[union-attr]
            if info is None:
                return None
            return info._asdict()
        except Exception as exc:
            self._logger.warning("get_account_info failed: %s", exc)
            return None

    def get_terminal_info(self) -> Optional[dict[str, Any]]:
        """Retrieve the current MT5 terminal information.

        Returns:
            A dictionary of terminal fields, or None if not connected
            or if the call fails.
        """
        if not self.is_connected():
            self._logger.debug("get_terminal_info called while not connected.")
            return None

        try:
            info = mt5.terminal_info()  # type: ignore[union-attr]
            if info is None:
                return None
            return info._asdict()
        except Exception as exc:
            self._logger.warning("get_terminal_info failed: %s", exc)
            return None

    def __enter__(self) -> MT5Connection:
        """Enter the context manager by establishing a connection.

        Returns:
            This MT5Connection instance.

        Raises:
            MT5ConnectionError: If the connection cannot be established.
        """
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """Exit the context manager by disconnecting from MT5.

        Args:
            exc_type: Exception type, if an exception occurred.
            exc_val: Exception value, if an exception occurred.
            exc_tb: Exception traceback, if an exception occurred.

        Returns:
            False — exceptions are not suppressed.
        """
        self.disconnect()
        return False

    def __repr__(self) -> str:
        """Return a developer-friendly string representation.

        Returns:
            String showing server, login, and connection state.
        """
        with self._lock:
            connected = self._connected
        return (
            f"MT5Connection("
            f"server={self._config.server!r}, "
            f"login={self._config.login}, "
            f"connected={connected})"
        )


# ─────────────────────────────────────────────
#  Factory Helper
# ─────────────────────────────────────────────

def create_connection(
    login: int,
    password: str,
    server: str,
    path: Optional[str] = None,
    **kwargs: Any,
) -> MT5Connection:
    """Factory function to create an MT5Connection from individual parameters.

    Constructs an MT5ConnectionConfig and wraps it in an MT5Connection.
    Additional keyword arguments are forwarded to MT5ConnectionConfig.

    Args:
        login: MT5 account login number.
        password: MT5 account password.
        server: MT5 broker server name (e.g. "MetaQuotes-Demo").
        path: Optional path to terminal64.exe. Auto-detected if None.
        **kwargs: Additional keyword arguments passed to MT5ConnectionConfig
            (e.g. timeout_sec, max_retries, retry_delay_sec, portable).

    Returns:
        A configured, ready-to-use MT5Connection instance.

    Example:
        conn = create_connection(
            login=12345678,
            password="secret",
            server="MetaQuotes-Demo",
            max_retries=5,
        )
        with conn:
            print(conn.get_account_info())
    """
    config = MT5ConnectionConfig(
        login=login,
        password=password,
        server=server,
        path=path,
        **kwargs,
    )
    return MT5Connection(config)