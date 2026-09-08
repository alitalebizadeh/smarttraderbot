# Production Readiness Report

## Status: NOT READY FOR LIVE TRADING

## What is complete and tested
- Causal market-structure validation: BOS, CHoCH, displacement, confirmation, and look-ahead tests.
- Liquidity levels and sweep detection: PDH, PDL, WH, WL, EQH, EQL, wick rejection, and next-candle confirmation.
- Smart Money Concept zones: order blocks, FVGs, freshness, mitigation, fills, inversion, and scoring.
- Multi-timeframe bias and alignment.
- Decision engine with explicit no-trade gates and explainable reasoning.
- Instrument-aware position sizing and trade-state management.
- Historical replay, batch backtesting, and performance metrics.
- SQLite setup and backtest-result persistence.
- End-to-end pipeline orchestration and synthetic smoke tests.
- Full automated suite: 95 tests passing.

## What is missing before live trading
1. Live MT5 data integration
2. Real historical backtest (minimum 1 year XAUUSD)
3. Slippage and spread simulation
4. News/session filter
5. Multi-symbol validation

## Known limitations
- The current validation evidence is synthetic and does not replace real-market validation.
- Existing legacy modules still contain deprecated `utcfromtimestamp()` usage.
- Some compatibility facades intentionally preserve older permissive behavior.
- Pip and lot conventions are configured for supported instruments but require broker-specific verification.
- The pipeline does not yet provide a production MT5 execution adapter.

## How to run
- Install dependencies:
  ```bash
  python3 -m pip install -r requirements.txt
  ```
- Run the complete test suite:
  ```bash
  pytest -q
  ```
- Run the pipeline with CSV data by loading UTC-indexed OHLCV DataFrames and calling:
  ```python
  from src.core.pipeline import run_full_pipeline

  signal = run_full_pipeline(
      symbol="XAUUSD",
      df_ltf=df_ltf,
      df_htf=df_htf,
      account_balance=10000.0,
      risk_pct=1.0,
      pip_value=1.0,
      db_path="research.sqlite",
  )
  print(signal.direction, signal.reasoning)
  ```
  CSV inputs must provide `open`, `high`, `low`, and `close` columns with a chronological timestamp index.

## Risk warning
This system is for research purposes only.
Past performance does not guarantee future results.
Never risk money you cannot afford to lose.
