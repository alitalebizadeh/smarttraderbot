# SmartTraderBot Complete Repository Analysis

## Scope

This analysis was completed before the next implementation changes. It covers the Python source tree, configuration, dependencies, tests, documentation, current data flow, trading logic, technical debt, and a staged migration strategy.

## Current Architecture

Runtime starts in `main.py`, which loads YAML configuration, validates symbols and timeframes, creates a candle provider, runs `TimeframeScanner` through `MarketScanner`, and renders dashboard, report, and JSON output.

The current layers are:

- `src/data/`: CSV and optional MetaTrader 5 loading, candle caching, symbol providers.
- `src/engine/`: market structure, liquidity, displacement, FVG, order block, supply/demand, POI, confluence, clustering, and entry-point heuristics.
- `src/models/`: dataclass contracts for several domain concepts.
- `src/scanner/`: one-timeframe and multi-symbol orchestration.
- `src/scoring/`: zone and result scoring.
- `src/dashboard/` and `src/output/`: terminal, HTML, report, and JSON presentation.
- `src/utils/`: validation, timestamps, price utilities, and logging.

The repository currently has no database, risk engine, historical replay engine, performance analytics layer, news/session filter, or formal decision gate.

## Existing Functionality

The project currently supports:

- OHLCV loading from CSV and optional MT5 integration.
- Basic timestamp parsing, delimiter detection, duplicate removal, and invalid-price filtering.
- Swing highs/lows and market-structure events.
- Liquidity levels, equal highs/lows, and sweep candidates.
- ATR/body-based displacement detection.
- FVG, order-block, supply/demand, POI, confluence, and zone clustering heuristics.
- Entry-point suggestions and fixed-RR target generation.
- Multi-symbol/timeframe scan orchestration.
- Dashboard, report, and JSON exports.
- Regression tests for market-structure validation and the new MTF alignment layer.

The current MTF implementation in `src/mtf_engine/` is a standalone utility and is not yet connected to the scanner or trade decision path.

## Trading Logic Problems

### Causal and look-ahead risks

- Swing pivots require right-side candles, but the current event loop makes the swing available at its pivot index rather than its confirmation index.
- Break scoring uses follow-through candles after the break while timestamping the event at the earlier candle.
- CHoCH validation checks the next candle for confirmation, which is not causal at the break timestamp.
- Liquidity analysis can receive swings identified from the complete dataset, including pivots not known at the evaluation time.
- FVG, order-block, and supply/demand lifecycle calculations inspect future candles when run over a historical dataset.
- MT5 loading includes the currently forming candle through position `0`, allowing signals to change before close.
- Current-price fallback uses the final close without a completed-bar policy.

### Domain-contract defects

- `zone_cluster_engine.py` expects legacy fields such as `fill_status`, `is_valid`, `candle_time`, and `status`, while active engines expose different names.
- `confluence_engine.py` checks `market_structure.has_bos`, which is not present on the current `MarketStructure` model.
- `htf_aligned` is consumed by scoring but is not populated by the scanner.
- Export and report code use legacy names such as `event_time` instead of `break_candle_time`.
- Several engines define local duplicate models instead of using one validated domain contract.

### Trading realism gaps

- Order blocks remain close to a last-opposite-candle heuristic and do not require liquidity, displacement, BOS/CHoCH, freshness, mitigation, or HTF alignment.
- Liquidity sweeps do not consistently require rejection and confirmation.
- Confluence scores can award sweep points without validating relevance to a POI.
- Entry generation has no spread, commission, slippage, tick-size, contract-size, or account-risk model.
- There is no formal `NO TRADE`, `BUY`, `SELL` decision gate.
- There is no historical execution simulator or realistic result calculation.

## Data and Configuration Weaknesses

- No candle-gap/completeness validator exists.
- Timestamp normalization can leave `NaT` rows and does not enforce one timezone policy throughout the pipeline.
- Duplicate handling is silent and not audited.
- Timeframe vocabularies are inconsistent (`MN` versus `MN1`).
- The default configuration includes a machine-specific output path.
- The documented runtime modes do not all match `main.py` behavior.
- Scanner configuration is partly ignored and important values are hardcoded.
- The default historical data directory is absent.
- MT5 dependencies are optional and live operation is platform constrained.
- Live loading can fall back to stale CSV data without a strong source-state signal.

## Dependencies and Quality Gaps

`requirements.txt` includes pandas, NumPy, PyYAML, Jinja2, pytest, and optional/unused packages. There is no formal packaging, linting, type-checking, formatting, CI, coverage gate, or schema versioning. Broad exception handling is common and sometimes turns invalid analysis into apparently successful empty results. Output rendering includes hardcoded language and instrument assumptions, and some dynamic report content needs escaping review.

## Tests and Validation Baseline

Current tests cover only a small set of market-structure validation cases and the MTF alignment scenarios. There are no causal replay tests, data-quality tests, engine contract tests, integration tests for the scanner, risk tests, backtest tests, persistence tests, or coverage enforcement. The current baseline test command passes, but that does not establish production readiness.

## Migration Strategy

The migration will be incremental and preserve the current scanner as a legacy path until replacement modules have contracts and tests:

1. Freeze the current baseline and document known behavior.
2. Create stable shared contracts for timestamps, candles, structure events, liquidity events, zones, setup decisions, orders, and trades.
3. Harden market-data normalization, completed-bar policy, gap detection, and point-in-time slicing.
4. Make market-structure and liquidity calculations causal by separating pivot time from confirmation time and removing future follow-through from historical decisions.
5. Rebuild order-block, FVG, supply/demand, and premium/discount logic around confirmed events and point-in-time lifecycle state.
6. Connect the Daily → H4 → H1 → M15 → M5 hierarchy to setup decisions, with conflict and neutral states producing `NO TRADE`.
7. Add a decision layer requiring HTF bias, liquidity, structure shift, POI, location, and confirmation.
8. Add risk sizing and execution assumptions for spread, commission, slippage, delay, partial exits, break-even, and trailing stops.
9. Add historical replay, SQLite persistence, analytics, session/news filters, train/validation/test splitting, Monte Carlo, and regime analysis.
10. Validate XAUUSD samples on H4/H1/M15/M5 with causal replay and chart-review artifacts.
11. Run the final quality audit only after all modules have focused tests and no known critical leakage remains.

Every migration step must have explicit contracts, focused tests, and a documented limitation list. No backtest statistic should be reported until it is generated from supplied historical data by the replay engine.
