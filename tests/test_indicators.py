import numpy as np
import pandas as pd

from src.indicators import compute_strategy_c_indicators, wilder_atr, wilder_rsi


def sample_df(n=320):
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0.12, 1.0, n))
    high = close + rng.uniform(0.2, 1.5, n)
    low = close - rng.uniform(0.2, 1.5, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1_000_000, 3_000_000, n)
    return pd.DataFrame({
        "date": pd.bdate_range("2025-01-01", periods=n),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def test_wilder_rsi_bounds():
    rsi = wilder_rsi(sample_df()["close"], 14).dropna()
    assert not rsi.empty
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_wilder_atr_positive():
    atr = wilder_atr(sample_df(), 14).dropna()
    assert not atr.empty
    assert (atr > 0).all()


def test_strategy_columns_present():
    cfg = {
        "rsi_period": 14,
        "adaptive_lookback": 60,
        "wma_period": 14,
        "sma_period": 200,
        "breakout_lookback": 20,
        "volume_lookback": 20,
    }
    out = compute_strategy_c_indicators(sample_df(), cfg)
    for col in ["rsi14", "dynamic_rsi", "adaptive_midline", "upper", "lower", "sma200", "atr14"]:
        assert col in out.columns
        assert out[col].notna().sum() > 0
