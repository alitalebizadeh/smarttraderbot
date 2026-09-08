from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from src.backtester import BacktestTrade
from src.decision_engine import TradeSignal


class SQLiteStore:
    """Persist signals and replay trades in a small transactional SQLite store."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    risk_reward REAL,
                    confidence REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_time TEXT NOT NULL,
                    exit_price REAL NOT NULL,
                    result TEXT NOT NULL,
                    gross_pnl REAL NOT NULL,
                    costs REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    exit_reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT NOT NULL
                );
                """
            )

    def save_signal(self, signal: TradeSignal) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """INSERT INTO signals
                (symbol, timeframe, direction, entry, stop_loss, take_profit,
                 risk_reward, confidence, reasoning, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.symbol, signal.timeframe, signal.direction, signal.entry,
                    signal.stop_loss, signal.take_profit, signal.risk_reward,
                    signal.confidence, json.dumps(signal.reasoning), signal.timestamp.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def save_trade(self, trade: BacktestTrade) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """INSERT INTO trades
                (symbol, direction, entry_time, entry_price, exit_time, exit_price,
                 result, gross_pnl, costs, net_pnl, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.symbol, trade.direction, trade.entry_time.isoformat(), trade.entry_price,
                    trade.exit_time.isoformat(), trade.exit_price, trade.result,
                    trade.gross_pnl, trade.costs, trade.net_pnl, trade.exit_reason,
                ),
            )
            return int(cursor.lastrowid)

    def save_backtest_run(self, metadata: dict) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "INSERT INTO backtest_runs (metadata) VALUES (?)",
                (json.dumps(metadata, sort_keys=True),),
            )
            return int(cursor.lastrowid)

    def count(self, table: str) -> int:
        if table not in {"signals", "trades", "backtest_runs"}:
            raise ValueError("unsupported table")
        with sqlite3.connect(self.path) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
