# Architecture Migration Report

## Principle

The existing scanner remains available while new contracts and services are introduced beside it. A module is promoted only after focused tests establish behavior and causal constraints.

| Old file or area | New module | Reason |
|---|---|---|
| `src/data/candle_provider.py`, `src/data/mt5_loader.py` | `src/market_data/` | Centralize validation, UTC normalization, completed-bar policy, gap checks, and point-in-time access. |
| `src/models/market_structure.py`, `src/engine/market_structure_engine.py` | `src/market_structure/` | Separate causal structure detection from legacy scanner orchestration. |
| `src/engine/liquidity_engine.py` | `src/liquidity_engine/` | Require level provenance, rejection, and confirmation for sweeps. |
| `src/engine/fvg_engine.py`, `src/engine/order_block_engine.py`, `src/engine/supply_demand_engine.py`, `src/engine/poi_engine.py` | `src/smc_engine/` | Unify zone contracts and point-in-time lifecycle state. |
| `src/mtf_engine/` | `src/mtf_engine/` | Retain the approved hierarchy implementation and connect it through explicit decision contracts. |
| `src/engine/entry_point_engine.py`, `src/engine/confluence_engine.py`, `src/scoring/` | `src/decision_engine/` | Make `NO TRADE`, `BUY`, and `SELL` an explicit, explainable gate. |
| No current equivalent | `src/risk_engine/` | Add account-risk sizing, instrument constraints, and trade management rules. |
| No current equivalent | `src/backtester/` | Add causal candle replay and realistic execution simulation. |
| No current equivalent | `src/database/` | Persist setups, signals, trades, executions, and backtest runs in SQLite. |
| No current equivalent | `src/analytics/` | Calculate performance, drawdown, regime, split, and Monte Carlo statistics from actual records. |
| `src/scanner/` | Legacy adapter plus new application orchestration | Keep existing runtime stable while new services are integrated behind tested contracts. |
| `src/dashboard/`, `src/output/` | Presentation adapters | Consume versioned domain contracts instead of engine-local fields. |

## Promotion Gates

1. New domain contract has type hints, validation, serialization, and unit tests.
2. Historical evaluation uses only data available at the evaluation timestamp.
3. Existing tests and new focused tests pass.
4. Integration is additive until the replacement path has equivalent coverage.
5. No backtest or performance claim is made without supplied historical data and explicit execution assumptions.

## Planned Sequence

1. Shared contracts and market-data validation.
2. Causal structure and liquidity services.
3. Unified SMC zone lifecycle and premium/discount location.
4. MTF connection and explainable decision gate.
5. Risk and session/news filters.
6. Historical replay and SQLite persistence.
7. Analytics, train/validation/test split, Monte Carlo, regime analysis, and chart-review artifacts.
8. Final audit with leakage and security checks.
