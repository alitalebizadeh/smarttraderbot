# Project Review

## 1. Current architecture

The repository is structured as a Smart Money Concepts (SMC) market scanner and confluence engine. The project currently has a classic layered design:

- `main.py` – CLI entry point and configuration bootstrapping.
- `config.yaml` – scanner configuration.
- `src/data/` – data access layer for candles, MT5 data, and symbol metadata.
- `src/engine/` – analytical engines for displacement, market structure, FVG, order blocks, POI, supply/demand, confluence, and zone clustering.
- `src/models/` – dataclasses representing market states, structure, liquidity, FVGs, and scoring.
- `src/scanner/` – orchestration of symbol/timeframe scanning.
- `src/scoring/` – point-based ranking and grade assignment.
- `src/output/` – report/export generation.
- `src/dashboard/` – HTML dashboard generation.
- `src/utils/` – common helpers, logging, time handling, and validators.

The codebase is already organized around a multi-engine pipeline and dataclass-driven outputs. The scanner can load candles, run a collection of SMC detection engines, and generate a scan result with a score.

## 2. Existing features

The project already includes a useful foundation:

- Multi-symbol and multi-timeframe scan orchestration.
- CLI configuration and runtime overrides.
- OHLCV ingestion and provider abstraction.
- Market structure detection (swing highs/lows and BOS/CHoCH-like events).
- Liquidity level / sweep detection.
- Displacement detection.
- Order block detection.
- FVG detection.
- Supply & demand zone detection.
- POI / entry model generation.
- Confluence aggregation and scoring.
- HTML dashboard/report output.
- Logging utilities and shared helpers.

This is a functioning research/analysis scanner rather than a full trading system.

## 3. Problems

### 3.1 Architecture drift from the target mission

The existing code is still a scanner and not a research + backtesting engine. The current structure is service-oriented but not aligned with the intended SMC trading research platform architecture. The project needs clear separation between:

- market data access
- market structure analysis
- liquidity analysis
- multi-timeframe regime analysis
- decision making
- execution backtesting
- risk management
- database persistence

### 3.2 Mixed responsibilities across modules

Some engine files are doing both detection and orchestration. This makes them harder to validate, hard to test, and fragile to extend. Responsibilities are not isolated cleanly enough for a production-grade research engine.

### 3.3 Detection logic is descriptive, but not yet robust enough for professional trading research

The current SMC logic is directional and useful, but it is not strict enough for a production-grade system. Several rules are implemented as simplified approximations rather than a rigorous market-structure framework.

Examples of concerns:

- BOS/CHoCH logic is generalized and not sufficiently disciplined around proper confirmation requirements.
- Liquidity sweeps are heuristic rather than precision-driven.
- Order block detection is still too close to a generic last-opposite-candle approach rather than a stricter liquidity + displacement + BOS + fresh-zone framework.
- FVG logic is likely effective as a first pass, but not structured for score weighting or higher-timeframe dominance.

### 3.4 No explicit backtesting system

The repository does not yet contain a true historical replay engine with:

- trade simulation
- SL/TP handling
- partial exits
- break-even logic
- trailing stops
- equity curve generation
- robust performance metrics

This is a missing core capability for the target project mission.

### 3.5 Risk and position-sizing infrastructure is not yet implemented

The repository does not currently implement a formal risk engine with:

- fixed percentage risk
- position sizing by stop distance
- lot size calculation
- account-level aggregation

### 3.6 Database layer is absent

The project currently stores little to no structured research/trade data in a persistent format. A database layer is required for storing setups, scores, results, and validation artifacts.

### 3.7 Validation and testing maturity is incomplete

The repository has no explicit, repository-wide test suite with meaningful coverage around signal logic, structure detection, liquidity detection, validation, and backtesting. This is a major gap for a production research engine.

## 4. Missing components

The following are missing or not sufficiently implemented for the target platform:

- `core/` package with shared contracts, timeframes, and engine lifecycle.
- `market_data/` with reliable OHLCV cache/data handling and future-data leakage protection.
- `market_structure/` with stronger swing and structure definitions.
- `liquidity_engine/` with prioritized liquidity events and structured sweeps.
- `smc_engine/` with consolidated SMC detection logic.
- `mtf_engine/` for multi-timeframe regime analysis and bias dominance.
- `decision_engine/` for final NO TRADE / BUY / SELL signal generation.
- `risk_engine/` for risk-based sizing and drawdown control.
- `backtester/` for historical replay and performance reporting.
- `database/` with SQLite persistence for trade setups and results.
- `tests/` with real behavioral tests and >=80% coverage target.

## 5. Risky code

The following code patterns are risky, brittle, or not production-safe:

- Broad exception handling in many modules, which can hide real issues and make debugging difficult.
- Validation logic that returns empty objects rather than surfacing meaningful failure states.
- Use of heuristics without structured confirmation requirements for critical signals.
- Lack of explicit checks for future data leakage in candle processing.
- Reliance on simple approximations for BOS/CHoCH and order blocks without strong structural proof.
- Incomplete or weak separation between analysis and reporting.
- Potential for inconsistent timestamp handling across DataFrames and engines.
- No explicit model versioning, schema validation, or persistence migration strategy.

## 6. Suggested modification order

1. Freeze the current scanner and create a formal architecture review and migration plan.
2. Define the target module structure and contract boundaries.
3. Create a professional market data layer with validated timeframes and safe historical data gating.
4. Rebuild the market structure engine to enforce swing/structure / BOS / CHoCH rules precisely.
5. Rebuild the liquidity engine around true liquidity events and sweep confirmation.
6. Rebuild the order block engine around strict validity rules instead of last-opposite-candle heuristics.
7. Rebuild the FVG and premium-discount logic with scoring and relation checks.
8. Implement the multi-timeframe bias engine with proper hierarchy: Daily > H4 > H1 > M15 > M5.
9. Build the decision engine for final signal generation.
10. Implement backtesting with realistic trade management and metrics.
11. Add the risk engine and SQLite persistence.
12. Write the tests and run validation.
13. Run historical validation on XAUUSD across H4, H1, and M15.

## 7. Overall assessment

The repository is a promising SMC research foundation, but it is not yet aligned with the required mission of a professional Smart Money trading research engine with backtesting, risk management, and database accountability.

The project is not unsafe to continue, but it does require a disciplined rebuild of the analysis stack and a more rigorous validation framework before it can be treated as a serious trading research platform.

## 8. Immediate next step

The required pre-code gate is complete. The project is now formally reviewed and the next task is to map the current modules to the target architecture in a migration plan before implementing the new professional structure.
