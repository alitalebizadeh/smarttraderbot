from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.database.models import BACKTEST_RESULTS_SCHEMA, TRADE_SETUPS_SCHEMA


class TradeRepository:
    """Persist generated setups and batch backtest results in SQLite."""

    def __init__(self, db_path: str) -> None:
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(TRADE_SETUPS_SCHEMA)
        self.connection.execute(BACKTEST_RESULTS_SCHEMA)
        self.connection.commit()

    def save_setup(self, signal: Any) -> str:
        """Insert a signal setup once and return its stable setup identifier."""
        setup_id = str(signal.signal_id)
        existing = self.connection.execute("SELECT setup_id FROM trade_setups WHERE setup_id = ?", (setup_id,)).fetchone()
        if existing is not None:
            return setup_id
        ob = getattr(signal, "ob_used", None)
        fvg = getattr(signal, "fvg_used", None)
        self.connection.execute(
            """INSERT INTO trade_setups
            (setup_id, symbol, timeframe, direction, formed_at, entry_price, stop_loss,
             take_profit_1, take_profit_2, ob_score, fvg_score, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                setup_id, signal.symbol, getattr(signal.mtf_alignment.higher_tf_bias, "timeframe", ""),
                signal.direction, signal.formed_at.isoformat(), signal.entry_price,
                signal.stop_loss, signal.take_profit_1, signal.take_profit_2,
                getattr(ob, "score", None), getattr(fvg, "score", None), signal.confidence,
                json.dumps(signal.reasoning),
            ),
        )
        self.connection.commit()
        return setup_id

    def save_result(self, trade: Any) -> None:
        """Insert one batch replay result."""
        signal = trade.signal
        self.connection.execute(
            """INSERT INTO backtest_results
            (trade_id, setup_id, entry_time, exit_time, exit_price, exit_reason,
             pnl_pips, pnl_pct, rr_achieved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.trade_id, signal.signal_id, trade.entry_time.isoformat(),
                trade.exit_time.isoformat() if trade.exit_time is not None else None,
                trade.exit_price, trade.exit_reason, trade.pnl_pips, trade.pnl_pct, trade.rr_achieved,
            ),
        )
        self.connection.commit()

    def get_all_setups(self) -> list[dict]:
        """Return all persisted setup rows as dictionaries."""
        return [dict(row) for row in self.connection.execute("SELECT * FROM trade_setups ORDER BY id")]

    def get_results_by_symbol(self, symbol: str) -> list[dict]:
        """Return persisted results whose setup symbol matches the requested symbol."""
        return [
            dict(row)
            for row in self.connection.execute(
                """SELECT backtest_results.* FROM backtest_results
                JOIN trade_setups ON trade_setups.setup_id = backtest_results.setup_id
                WHERE trade_setups.symbol = ? ORDER BY backtest_results.id""",
                (symbol,),
            )
        ]

    def close(self) -> None:
        """Close the repository SQLite connection."""
        self.connection.close()
