# SmartTraderBot

A professional **Market Scanner & Confluence Engine** built on Smart Money Concepts (SMC/ICT).

> ⚠️ This bot does **NOT** place trades. It scans, analyzes, and displays opportunities. Final entry decision is always made by the trader.

---

## What It Does

- Scans financial instruments (Forex, Gold, Indices) across multiple timeframes
- Detects SMC/ICT zones: Order Blocks, FVGs, Liquidity, BOS/CHoCH, Supply & Demand
- Scores each zone by confluence (0–100)
- Displays the best setups on an auto-refreshing HTML dashboard

## Scoring System

| Factor | Points |
|--------|--------|
| Order Block | 20 |
| Fair Value Gap | 20 |
| Liquidity Sweep | 25 |
| Break of Structure | 15 |
| Premium / Discount | 10 |
| HTF Alignment | 10 |
| **Total** | **100** |

| Score | Grade | Label |
|-------|-------|-------|
| 80–100 | A+ | A+ Setup |
| 65–79 | A | Strong Setup |
| 50–64 | B | Good Setup |
| 35–49 | C | Weak Setup |
| 0–34 | D | Poor Setup |

---

## Project Structure SmartTraderBot/
├── main.py ← Entry point
├── config.yaml ← All settings
├── requirements.txt
├── .env ← Credentials (never commit)
├── src/
│ ├── models/ ← Pure dataclasses
│ ├── data/ ← MT5 connection & data loading
│ ├── engine/ ← SMC analysis engines
│ ├── scoring/ ← Scoring & classification
│ ├── scanner/ ← Orchestration
│ ├── dashboard/ ← HTML output
│ └── utils/ ← Shared utilities
├── data/ ← CSV files from MT5
├── output_files/ ← dasdashboard.html
└── logs/ ← Log files ---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your MT5 CSV data
# Place files in data/ as: SYMBOL_TIMEFRAME.csv
# Example: data/XAUUSD_M1.csv

# 3. Configure
# Edit config.yaml — set your symbols and timeframes

# 4. Run (single scan)
python main.py

# 5. Run (continuous loop)
python main.py --mode loop
```

---

## CLI Options

```bash
python main.py --mode single          # One scan then exit
python main.py --mode loop            # Continuous scanning
python main.py --symbol XAUUSD        # Override symbol
python main.py --timeframe H4         # Override timeframe
python main.py --interval 30          # Override scan interval
python main.py --log-level DEBUG      # Verbose logging
python main.py --config my.yaml       # Custom config file
```

---

## Data Format (MT5 CSV)

File naming: `SYMBOL_TIMEFRAME.csv` → `XAUUSD_M1.csv`

Required columns: time,open,high,low,close,tick_volume,spread,real_volume---

## Development

- Branch: `phase1-E1-scanner`
- Platform: Mac (development) → Windows VPS (production)
- Python: 3.9+

---

## Roadmap

- **Phase 1 — E1:** Market Scanner (current)
- **Phase 1 — E2:** Direct MT5 API connection
- **Phase 2:** Telegram alerts
- **Phase 3:** Session-based filtering (Asia/London/NY)
- **Phase 4:** Backtesting engine
