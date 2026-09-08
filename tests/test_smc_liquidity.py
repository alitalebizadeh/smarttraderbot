import pandas as pd

from src.liquidity_engine import LiquidityEngine
from src.smc_engine import FVGEngine, OrderBlockEngine


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 100.5, 101.1, 101.6, 102.2, 102.8],
            "high": [100.8, 101.0, 101.7, 102.2, 103.0, 103.5],
            "low": [99.7, 99.9, 100.9, 101.1, 101.8, 102.3],
            "close": [100.2, 100.7, 101.3, 101.9, 102.6, 103.1],
        },
        index=pd.date_range("2024-01-01", periods=6, freq="5min", tz="UTC"),
    )


def test_liquidity_engine_detects_sweeps_and_levels() -> None:
    engine = LiquidityEngine()
    result = engine.analyze(_df())

    assert result["external"]
    assert result["sweeps"]


def test_fvg_and_order_block_modules_create_real_zones() -> None:
    df = _df()
    fvg = FVGEngine().detect(df)
    blocks = OrderBlockEngine().detect(df)

    assert fvg
    assert blocks
