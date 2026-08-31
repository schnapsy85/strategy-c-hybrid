import numpy as np
import pandas as pd

from src.strategy_b import compute_strategy_b_metrics, evaluate_strategy_b


def sample_df(n=320, drift=0.25):
    rng = np.random.default_rng(11)
    close = 100 + np.cumsum(rng.normal(drift, 0.7, n))
    high = close + rng.uniform(0.2, 1.1, n)
    low = close - rng.uniform(0.2, 1.1, n)
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.integers(100_000, 500_000, n)
    return pd.DataFrame({
        "date": pd.bdate_range("2025-01-01", periods=n),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def test_strategy_b_metrics_present():
    metrics = compute_strategy_b_metrics(sample_df())
    for key in ["close", "sma200", "sma200_20d_ago", "adx14", "rsi14", "atr20", "performance_6m", "performance_12m"]:
        assert key in metrics
        assert metrics[key] is not None


def test_strategy_b_buy_requires_all_three_conditions():
    decision = evaluate_strategy_b({
        "close": 120.0,
        "sma200": 110.0,
        "sma200_20d_ago": 108.0,
        "adx14": 31.0,
        "below_sma200_10d": False,
    })
    assert decision["buy_signal"] is True


def test_strategy_b_exit_on_ten_closes_below_sma200():
    decision = evaluate_strategy_b({
        "close": 100.0,
        "sma200": 105.0,
        "sma200_20d_ago": 104.0,
        "adx14": 20.0,
        "below_sma200_10d": True,
    })
    assert decision["exit_signal"] is True
    assert "10_consecutive_closes_below_sma200" in decision["exit_reasons"]


def test_strategy_b_exit_on_falling_sma200():
    decision = evaluate_strategy_b({
        "close": 100.0,
        "sma200": 103.0,
        "sma200_20d_ago": 104.0,
        "adx14": 20.0,
        "below_sma200_10d": False,
    })
    assert decision["exit_signal"] is True
    assert "sma200_falling" in decision["exit_reasons"]
