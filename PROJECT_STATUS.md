# SmartTraderBot — Project Status

## Test Coverage
- Total tests: 95
- Passing: 95
- Failing: 0
- Quality score: 90/100

## Architecture
### New modules (production-quality)
- market_structure/causal.py — BOS/CHoCH causal validation
- liquidity_engine/levels.py — PDH/PDL/WH/WL/EQH/EQL detection
- liquidity_engine/sweep_detector.py — 3-condition sweep validation
- smc_engine/order_block.py — OB with liquidity+displacement+BOS
- smc_engine/fvg.py — FVG with ATR threshold + inversion detection
- mtf_engine/bias.py — timeframe bias computation
- mtf_engine/alignment.py — HTF/LTF alignment validation
- decision_engine/signal.py — TradeSignal dataclass
- decision_engine/engine.py — full condition gate
- risk_engine/position_sizer.py — percentage risk sizing
- risk_engine/trade_manager.py — breakeven + trailing stop
- backtester/replay.py — conservative candle-by-candle replay
- backtester/metrics.py — win rate, PF, drawdown, Sharpe
- database/repository.py — SQLite persistence
- core/pipeline.py — full integration pipeline
- core/instrument_config.py — symbol-specific pip configuration

### Legacy modules (preserved, not modified)
- src/engine/ — original scanner engines
- src/scanner/ — original market scanner
- src/dashboard/ — HTML dashboard
- src/output/ — report generator

## Known limitations
1. Live MT5 integration not productionized
2. Real historical backtest not yet run (needs 1yr+ data)
3. Spread/slippage not simulated
4. No session/news filter
5. Multi-symbol validation pending

## How to run
```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest -q

# Run original scanner
python3 main.py

# Run pipeline (requires CSV data)
python3 -c "
from core.pipeline import run_full_pipeline
import pandas as pd
df = pd.read_csv('data/XAUUSD_M1.csv')
# ... setup and run
"
```
