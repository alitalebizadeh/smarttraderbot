# Migration Plan

## 1. Objective

The project must evolve from a scanner into a professional Smart Money Concept (SMC) trading research and backtesting platform while preserving existing useful logic where it is valid and testable.

This migration must avoid random file moves. The mapping below preserves the current codebase and organizes it into a cleaner architecture that reflects the required target system.

## 2. Target architecture

The target architecture is:

- `core/`
  - Shared types, configuration contracts, enumerations, constants, and engine base classes.
- `market_data/`
  - Candle loading, OHLCV validation, symbol metadata, timeframe validation, and future-data protection.
- `market_structure/`
  - Swing detection, internal/external structure, BOS, CHoCH, and trend state logic.
- `liquidity_engine/`
  - External and internal liquidity detection, liquidity sweeps, and event scoring.
- `smc_engine/`
  - Combined SMC detection logic using structure, liquidity, displacement, FVG, and OB evaluation.
- `mtf_engine/`
  - Daily/H4/H1/M15/M5 hierarchy and dominant regime bias generation.
- `decision_engine/`
  - Final NO TRADE / BUY / SELL decision logic with confidence and reasoning.
- `risk_engine/`
  - Risk percentage, position sizing, max loss, and execution controls.
- `backtester/`
  - Historical replay, trade simulation, metrics, drawdown, equity curve, and validation.
- `database/`
  - SQLite storage for setup records, trade records, and validation data.
- `tests/`
  - Unit and integration tests for each engine and for backtesting behavior.

## 3. Mapping from current repository to target architecture

### 3.1 Current `src/data/` -> target `market_data/`

Current files:

- `src/data/candle_provider.py`
- `src/data/mt5_connection.py`
- `src/data/mt5_loader.py`
- `src/data/symbol_provider.py`

Target mapping:

- `market_data/candle_provider.py` – normalized OHLCV fetch and caching layer.
- `market_data/mt5_connection.py` – broker connector abstraction.
- `market_data/mt5_loader.py` – historical loader and validation utilities.
- `market_data/symbol_provider.py` – symbol/timeframe registry and metadata.

Required upgrades:

- support OHLCV for M5, M15, H1, H4, and Daily
- block future data leakage
- proper timestamp sorting and validation
- data quality checks and completeness checks

### 3.2 Current `src/engine/market_structure_engine.py` -> target `market_structure/`

Current file:

- `src/engine/market_structure_engine.py`

Target mapping:

- `market_structure/engine.py` or `structure_engine.py`

Required upgrades:

- strict swing high/low detection
- internal/external structure classification
- valid BOS detection with close break, ATR distance, displacement, and HTF confirmation
- valid CHoCH detection with liquidity event + structure shift + confirmation candle
- current regime state and bias output structure

### 3.3 Current `src/engine/liquidity_engine.py` -> target `liquidity_engine/`

Current file:

- `src/engine/liquidity_engine.py`

Target mapping:

- `liquidity_engine/engine.py`

Required upgrades:

- external liquidity detection: PDH/PDL, WH/WL, equal high/equal low
- internal liquidity detection: minor swing pools
- liquidity sweep detection: take liquidity + reject + structure shift
- `LiquidityEvent` object with `type`, `price`, `timestamp`, `strength`, `confirmed`

### 3.4 Current `src/engine/order_block_engine.py` -> target `smc_engine/` or dedicated module

Current file:

- `src/engine/order_block_engine.py`

Target mapping:

- `smc_engine/order_block_engine.py`
- or a dedicated `order_block/` package under `smc_engine/`

Required upgrades:

- valid OB requires prior liquidity sweep, displacement, BOS confirmation, fresh zone, no mitigation, HTF alignment
- do not use the simplistic "last opposite candle" definition
- `OrderBlockScore` with range `0-100`

### 3.5 Current `src/engine/fvg_engine.py` -> target `smc_engine/`

Current file:

- `src/engine/fvg_engine.py`

Target mapping:

- `smc_engine/fvg_engine.py`

Required upgrades:

- normal FVG
- inversion FVG
- balanced price range
- consequent encroachment
- score components: HTF alignment, liquidity relation, BOS relation, freshness

### 3.6 Current `src/engine/displacement_engine.py` -> target `smc_engine/` or `market_structure/`

Current file:

- `src/engine/displacement_engine.py`

Target mapping:

- `market_structure/displacement_engine.py` or `smc_engine/displacement_engine.py`

Required upgrades:

- confirm directional displacement using candle body and range ratio
- integrate with BOS logic and order block validation

### 3.7 Current `src/engine/entry_point_engine.py` -> target `decision_engine/` or `smc_engine/`

Current file:

- `src/engine/entry_point_engine.py`

Target mapping:

- `decision_engine/entry_logic.py`

Required upgrades:

- final entry/exit contextualization
- risk-adjusted trade plan generation

### 3.8 Current `src/scanner/timeframe_scanner.py` -> target `mtf_engine/` + `decision_engine/`

Current file:

- `src/scanner/timeframe_scanner.py`

Target mapping:

- `mtf_engine/regime_engine.py`
- `decision_engine/trade_decision_engine.py`

Required upgrades:

- Daily/H4/H1/M15/M5 analysis and dominant direction
- final bias generation with HTF precedence
- signal output for BUY / SELL / NO TRADE

### 3.9 Current `src/output/` and `src/dashboard/` -> target reporting layer

Current files:

- `src/output/report_generator.py`
- `src/output/signals_exporter.py`
- `src/dashboard/dashboard.py`
- `src/dashboard/tables.py`
- `src/dashboard/formatter.py`

Target mapping:

- reporting/export utilities under a new `reporting/` or `output/` package

Required upgrades:

- clean research output
- support backtest metrics export
- support CSV/JSON/SQLite export

### 3.10 Current `src/scoring/` -> target `decision_engine/` and `smc_engine/`

Current files:

- `src/scoring/score_classifier.py`
- `src/scoring/score_rules.py`
- `src/scoring/zone_scorer.py`

Target mapping:

- `decision_engine/scoring.py`
- `smc_engine/zonescore.py`

Required upgrades:

- scoring tied directly to valid structural logic, not generic heuristic totals only

## 4. Implementation sequence

### Phase 1 – Architecture cleanup

1. Establish the target package layout.
2. Introduce base contracts for engines and models.
3. Keep existing modules unchanged until mapped and verified.
4. Build new package wrappers where necessary.

### Phase 2 – Market data layer

1. Build robust candle ingestion.
2. Validate supported timeframes: M5, M15, H1, H4, Daily.
3. Prevent future leakage by using last-complete-bar logic and historical-only retrieval.
4. Build symbol registry and data availability checks.

### Phase 3 – Market structure engine

1. Replace weak structure logic with strict pivot detection.
2. Implement valid BOS and valid CHoCH rules.
3. Add internal/external structure analysis.
4. Ensure confirmation uses objective rules rather than generic candle counts.

### Phase 4 – Liquidity engine

1. Detect external and internal liquidity clusters.
2. Detect sweep confirmations.
3. Produce `LiquidityEvent` objects.
4. Tie liquidity sweeps to structure shifts.

### Phase 5 – Order blocks and FVG

1. Rebuild valid order block detection.
2. Add `OrderBlockScore` with 0–100 scoring.
3. Rebuild FVG and inversion logic with proper relations and scoring.
4. Add premium/discount engine.

### Phase 6 – Multi-timeframe engine

1. Set time hierarchy: Daily > H4 > H1 > M15 > M5.
2. Derive bullish/bearish/neutral bias.
3. Ensure higher timeframe dominates lower timeframe.

### Phase 7 – Decision engine and risk

1. Implement final NO TRADE / BUY / SELL logic.
2. Require HTF bias + liquidity + structure shift + POI + confirmation.
3. Implement risk percentage, sizing, lot calculation, and stop distance logic.

### Phase 8 – Backtesting

1. Add historical candle replay.
2. Simulate entries, SL, TP, partial exits, break-even, and trailing stops.
3. Compute only real metrics from executed trades.
4. Produce equity curve and performance reports.

### Phase 9 – Database and testing

1. Store trade setups and results in SQLite.
2. Create unit/integration tests.
3. Reach minimum 80% coverage.
4. Run historical validation on XAUUSD.

## 5. Planned migrations by file

| Current file | New location | Notes |
|---|---|---|
| `main.py` | `main.py` (keep entrypoint) | CLI remains but may be reworked to include new architecture entrypoints |
| `config.yaml` | `config.yaml` | Updated for new platform settings |
| `src/data/*.py` | `market_data/*.py` | Move with adaptation |
| `src/engine/market_structure_engine.py` | `market_structure/*.py` | Rebuild strict logic |
| `src/engine/liquidity_engine.py` | `liquidity_engine/*.py` | Rebuild with detailed events |
| `src/engine/order_block_engine.py` | `smc_engine/order_block_engine.py` | Strict validity rewrite |
| `src/engine/fvg_engine.py` | `smc_engine/fvg_engine.py` | Score-aware rewrite |
| `src/engine/displacement_engine.py` | `market_structure/displacement_engine.py` | Reframe as structural confirmation logic |
| `src/engine/poi_engine.py` | `decision_engine/poi_engine.py` | Align with POI final decision process |
| `src/scanner/timeframe_scanner.py` | `mtf_engine/*.py` / `decision_engine/*.py` | Split responsibilities |
| `src/scoring/*.py` | `decision_engine/*.py` | Rework according to real signal logic |
| `src/output/*.py` | `reporting/*.py` | Keep reports and exports but align with backtesting |
| `src/dashboard/*.py` | `reporting/dashboard/*.py` | Optional visualization layer |
| `src/utils/*.py` | `core/utils/*.py` | Keep shared helper support |

## 6. Guardrails

- Do not delete existing useful functionality without explicit sign-off.
- Do not replace real logic with placeholders.
- Keep robust type hints and docstrings on new modules.
- Do not use broad `except Exception` where a narrower exception is possible.
- Every new module must be backed by unit tests.
- Historical verification must use real data and real metrics.

## 7. Validation gate before proceeding to implementation

The project may proceed to code migration only after:

1. architecture review is recorded,
2. target module map is approved,
3. the required data contracts are defined,
4. the tests and validation strategy are designed.

This document satisfies the required migration planning gate before any implementation work begins.
