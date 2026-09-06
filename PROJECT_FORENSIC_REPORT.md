# Project Forensic Analysis

## 1. Current architecture

The repository is a Smart Money Concepts (SMC) market scanner that has evolved into a multi-engine analysis pipeline for research-grade pattern detection. It is not yet a full trading research platform or backtesting engine.

Current architecture layers:

- Entry and configuration: `main.py`, `config.yaml`
- Data access: `src/data/`
- Analysis engines: `src/engine/`
- Models: `src/models/`
- Orchestration: `src/scanner/`
- Scoring and classification: `src/scoring/`
- Output/reporting: `src/output/`, `src/dashboard/`
- Shared utilities: `src/utils/`

At a high level, the runtime flow is:

1. Load configuration
2. Build scanner and providers
3. Download or retrieve candle data
4. Run multiple SMC engines on each symbol/timeframe
5. Score confluence zones and structures
6. Export findings to dashboard/report output

The project is organized around modular analyzers, but the architecture is still closer to a scanner/alerting system than to a full professional trading research + simulation engine.

## 2. Existing modules

### Entry and config

- `main.py`
  - Handles CLI arguments and configuration loading.
  - Builds scanner objects and runs the analysis loop.
  - This file is a launcher rather than a research engine core.

- `config.yaml`
  - Declares default market symbols, timeframes, log settings, and dashboard output configuration.
  - Currently defaults to XAUUSD + M1 only, which is a narrow initial setup.

### Data layer

- `src/data/candle_provider.py`
  - Provides candle retrieval abstraction.
  - Exposes OHLCV access patterns for scanner use.

- `src/data/mt5_connection.py`
  - Refers to MetaTrader 5 connection logic and data retrieval.
  - This is broker-dependent and likely operational only in Windows/MT5 environments.

- `src/data/mt5_loader.py`
  - Handles loading of MT5 data and file-based historical candles.

- `src/data/symbol_provider.py`
  - Maintains symbol metadata and supported instrument lookup.

### Engine layer

- `src/engine/market_structure_engine.py`
  - Detects swing highs/lows and structure events such as BOS/CHoCH-style shifts.

- `src/engine/liquidity_engine.py`
  - Detects liquidity levels and sweep behavior.

- `src/engine/displacement_engine.py`
  - Measures directional impulse and movement strength.

- `src/engine/order_block_engine.py`
  - Tries to identify institutional order block zones.

- `src/engine/fvg_engine.py`
  - Detects fair value gaps and gap-related patterns.

- `src/engine/supply_demand_engine.py`
  - Detects demand/supply zones.

- `src/engine/poi_engine.py`
  - Handles point-of-interest logic and entry-related decision inputs.

- `src/engine/confluence_engine.py`
  - Aggregates multiple structural signals into a combined view.

- `src/engine/zone_cluster_engine.py`
  - Clusters related zones into common structures.

- `src/engine/entry_point_engine.py`
  - Attempts to synthesize entry opportunities from the intermediate outputs.

### Models

The project defines a strong dataclass layer for analysis results and trading objects. Key model files include:

- `src/models/market_snapshot.py`
- `src/models/market_structure.py`
- `src/models/liquidity.py`
- `src/models/displacement.py`
- `src/models/order_block.py`
- `src/models/fvg.py`
- `src/models/poi.py`
- `src/models/confluence.py`
- `src/models/supply_demand.py`
- `src/models/scan_result.py`
- `src/models/scoring.py`
- `src/models/zone_cluster.py`

These model objects are structurally useful and represent a professional data-contract layer, which is one of the strongest features of the repository.

### Scanner and scoring

- `src/scanner/timeframe_scanner.py`
  - Orchestrates the end-to-end scan for a single symbol/timeframe.

- `src/scanner/market_scanner.py`
  - Coordinates multiple pairs/timeframes and combines outputs.

- `src/scanning/scan_scheduler.py`
  - Maintains scheduled scanning behavior.

- `src/scoring/score_rules.py`
  - Maps numeric scores to grade labels.

- `src/scoring/zone_scorer.py`
  - Scores zones based on confluence factors.

- `src/scoring/score_classifier.py`
  - Classifies signals based on score bands.

### Output and dashboard

- `src/output/report_generator.py`
  - Generates summary and report artifacts.

- `src/output/signals_exporter.py`
  - Exports findings in output formats.

- `src/dashboard/dashboard.py`
  - Produces an HTML dashboard for visual review.

- `src/dashboard/formatter.py`
  - Formats values for display.

- `src/dashboard/tables.py`
  - Renders table-based output.

### Utilities

- `src/utils/logger.py`
- `src/utils/time_utils.py`
- `src/utils/price_utils.py`
- `src/utils/validators.py`

These utilities provide validation, time helpers, price conversion, and logging, which are necessary foundations for a professional system.

## 3. Data flow

The project’s runtime data flow is roughly:

1. `main.py`
   - Reads config and CLI arguments.
   - Selects symbol/timeframe set.

2. Symbol/timeframe scanner setup
   - Creates `CandleProvider` and scanner objects.

3. Candle retrieval
   - Data provider loads OHLCV data from file or MT5 environment.
   - Candles are expected to be sorted and normalized before engine use.

4. Per-timeframe pipeline
   - `TimeframeScanner.scan()` triggers `_run_pipeline()`.
   - It loads candles, then resolves current price.
   - It executes:
     - market structure analysis
     - liquidity analysis
     - displacement analysis
     - order block detection
     - FVG detection
     - supply/demand detection
     - POI detection
     - confluence aggregation
     - scoring
     - entry-point generation

5. Output generation
   - Results are packaged into `MarketSnapshot` and `TimeframeScanResult`.
   - The scorer assigns grade labels and aggregated score.
   - Dashboard and exports create human-readable output.

The architecture clearly supports a scanner pipeline, but the data flow does not yet include:

- a real database layer
- a risk engine
- a backtest engine
- historical replay
- trade simulation with execution logic

## 4. Trading logic flow

The project intends to operate as an SMC scanner using a confluence-based flow:

- Detect price structure (swing highs/lows, trend changes, BOS/CHoCH-like structure events)
- Measure liquidity and sweep patterns
- Identify displacement and momentum regime
- Detect institutional zones: order blocks, FVGs, supply/demand, POI
- Aggregate confluence components
- Score the setup
- Present a trade idea or entry zone

The current scoring system is a useful research layer, but it is not yet a complete decision framework.

The logic intends to answer questions like:

- Is structure bullish or bearish?
- Is there a valid liquidity sweep?
- Is there institutional displacement?
- Is the structure aligned with higher timeframe bias?
- Is there a valid POI or entry zone?

However, the current system does not enforce a complete decision stack with a strict no-trade gate and real execution logic, which is required for a professional platform.

## 5. Current weaknesses

### 5.1 Architecture mismatch

The repository is still a scanner rather than a proper research engine. The target mission requires:

- market data foundation
- strict structure engine
- liquidity engine
- template-based entry logic
- decision engine
- proper backtesting
- risk management
- DB persistence

These are not yet implemented as a coherent professional stack.

### 5.2 Weak rule discipline

Several components are heuristic-driven and may be too permissive.

Examples:

- BOS/CHoCH logic is not strict enough for professional SMC validation.
- Order blocks may be approximated as generic opposing candles rather than strict liquidity + displacement + structural confirmation zones.
- Liquidity sweeps may be too generalized and not strongly linked to structure shift and rejection.
- FVG logic may be valid as a concept but not fully tied to structural hierarchy and scoring realism.

### 5.3 No true backtesting layer

There is no realistic historical replay system. That means the project cannot yet claim to be backtestable in a professional sense.

### 5.4 No formal risk engine

The project lacks:

- risk percentages
- position sizing
- stop-loss distance evaluation
- lot calculation
- break-even logic
- trailing logic
- partial exits

### 5.5 No persistent database layer for setups or trade records

The system has no formal SQLite persistence for trade plans, historical signal results, or performance tracking.

### 5.6 Validation is not yet production-grade

The codebase uses a useful research pipeline, but it does not yet demonstrate a robust validation loop with:

- historical validation on XAUUSD
- multi-timeframe bias enforcement
- real out-of-sample testing
- formal performance reporting

## 6. Potential bugs

The following issues are likely to exist or be exposed in a real trading workflow:

1. Future data leakage risk
   - If data loaders or scan logic use incomplete or non-historical data incorrectly, the system may leak future information into signal detection.

2. Timestamp inconsistency
   - Some modules may rely on DateTimeIndex or custom time columns; inconsistent formats can cause invalid comparisons between data frames and events.

3. Heuristic BOS/CHoCH detection could generate false positives
   - Without strict structural confirmation, the system may label too many break events as valid structure signals.

4. Order block detection may be overly permissive
   - If the engine identifies an opposing candle without proper displacement and freshness verification, it can produce noisy zone definitions.

5. Liquidity detection may overcount equal highs/lows
   - Closely grouped but non-trading-relevant levels may be treated as valid liquidity clusters without a stronger structural test.

6. Data validation weakness
   - Missing candles, duplicate timestamps, bad symbol metadata, or partial OHLCV files may silently propagate into downstream engine decisions.

7. Broad error handling could hide root causes
   - Some modules use broad exception handling patterns that may suppress true failures rather than exposing the actual bug.

8. Output/reporting risk
   - If a setup is generated without a real internal signal stack, the dashboard may look professional but reflect weak or invalid logic.

9. Multi-timeframe logic may not enforce hierarchy correctly
   - A lower timeframe might overpower higher timeframe decisions if the bias aggregator is not disciplined enough.

10. No robust accounting of trade performance metrics
   - Without proper trade-level simulation, summary statistics can be misleading or fake.

## 7. Missing components

The following components are either absent or insufficient for the requested professional architecture:

- `core/` namespace with foundational contracts, shared types, and system configuration
- `market_data/` with validated OHLCV handling and future-data protection
- `market_structure/` with strict structure analysis and professional BOS/CHoCH validation
- `liquidity_engine/` with detailed liquidity event models and sweep logic
- `smc_engine/` with proper order block, FVG, BPR, and scoring integration
- `mtf_engine/` enforcing HTF dominance for Daily/H4/H1/M15/M5 analysis
- `decision_engine/` producing only valid NO TRADE / BUY / SELL signals
- `risk_engine/` with risk percentage and position sizing
- `backtester/` with historical replay and trade simulation
- `database/` for SQLite storage of setup and trade records
- `tests/` with regression, unit, and integration coverage
- `FINAL_BACKTEST_REPORT.md` and validation pipeline for XAUUSD historical review

## 8. Migration strategy

The migration should happen in a disciplined sequence, not in a single large rewrite.

### Phase A: preserve and map

- Keep the existing repo intact.
- Document functional modules and outputs.
- Map old modules onto the required target architecture without moving or breaking working code prematurely.

### Phase B: strengthen the foundation

- Create a reliable OHLCV layer.
- Standardize timeframes and timestamps.
- Enforce validation on missing candles, duplicates, and plausibility.
- Guarantee historical-only access and no future leakage.

### Phase C: rebuild market structure and liquidity

- Replace shallow pattern detection with formal structural logic.
- Define robust BOS, CHoCH, swing, internal/external structure, and liquidity sweep rules.
- Tie all structural logic to confirmation, not heuristics alone.

### Phase D: rebuild SMC core logic

- Rebuild order blocks around liquidity + displacement + BOS + freshness + HTF alignment.
- Rebuild FVG logic around normal/inversion/BPR rules and explicit scoring.
- Connect structural and liquidity events into a single SMC engine.

### Phase E: implement multi-timeframe and decision logic

- Enforce HTF dominance.
- Require full setup validation before generating trade signals.
- Remove any output that lacks a complete reason stack.

### Phase F: add risk and backtesting

- Add risk engine.
- Build historical replay simulation.
- Produce real equity curve and performance metrics.

### Phase G: persistence, optimization, and validation

- Add SQLite store.
- Run objective testing and out-of-sample validation.
- Generate final reports for XAUUSD and compare before/after performance.

## Conclusion

The repository has a respectable foundation in the form of modular analyzers, strong dataclass modeling, and an SMC research mindset. However, the code is still a scanner prototype and not yet a professional, backtestable, risk-aware trading research platform.

The most important gaps are:

- structural validation discipline
- future-data safety
- true backtesting engine
- risk engine
- database layer
- testing and validation protocol

The architecture is salvageable, but it must be upgraded in phases with strict validation at every stage.
