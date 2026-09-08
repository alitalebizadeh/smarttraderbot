from __future__ import annotations

TRADE_SETUPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_setups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    formed_at TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit_1 REAL NOT NULL,
    take_profit_2 REAL NOT NULL,
    ob_score REAL,
    fvg_score REAL,
    confidence REAL,
    reasoning TEXT
)
"""

BACKTEST_RESULTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT NOT NULL,
    setup_id TEXT NOT NULL,
    entry_time TEXT,
    exit_time TEXT,
    exit_price REAL,
    exit_reason TEXT,
    pnl_pips REAL,
    pnl_pct REAL,
    rr_achieved REAL
)
"""
