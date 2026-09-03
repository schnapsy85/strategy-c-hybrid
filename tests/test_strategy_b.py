import numpy as np
import pandas as pd

from datetime import date

import scripts.strategy_b_scan as strategy_b_scan
from src.strategy_b import compute_strategy_b_metrics, evaluate_strategy_b
from src.strategy_b_data import StrategyBDataError


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


def test_stale_strategy_b_payload_reports_coverage_and_suppressed_raw_candidate(monkeypatch):
    captured = []
    metrics = {
        "date": "2026-09-01",
        "close": 100.0,
        "sma200": 90.0,
        "sma200_20d_ago": 89.0,
        "adx14": 31.0,
        "rsi14": 55.0,
        "atr20": 2.0,
        "performance_6m": 0.1,
        "performance_12m": 0.2,
        "below_sma200_10d": False,
    }
    raw_buy = {
        "conditions": {"close_gt_sma200": True, "sma200_rising_20d": True, "adx_gt_30": True},
        "buy_signal": True,
        "exit_signal": False,
        "exit_reasons": [],
    }

    monkeypatch.setattr(strategy_b_scan, "write_payload", captured.append)
    monkeypatch.setattr(strategy_b_scan, "last_completed_xetra_session", lambda: date(2026, 9, 2))
    monkeypatch.setattr(strategy_b_scan, "fetch_yahoo_daily", lambda *_args: pd.DataFrame({"date": ["2026-09-01"]}))
    monkeypatch.setattr(strategy_b_scan, "keep_completed_sessions", lambda raw, _expected: raw)
    monkeypatch.setattr(strategy_b_scan, "compute_strategy_b_metrics", lambda _df: metrics)
    monkeypatch.setattr(strategy_b_scan, "evaluate_strategy_b", lambda _metrics: raw_buy)

    strategy_b_scan.main()

    payload = captured[0]
    assert payload["signal"]["buy_signal"] is False
    assert payload["signal"]["exit_signal"] is False
    assert payload["coverage"] == {
        "instruments_total": 1,
        "instruments_with_required_history": 1,
        "ratio": 1.0,
        "minimum_bars_required": 253,
        "missing_or_short": [],
    }
    assert payload["stale_cached_candidate_count"] == 1


def test_fresh_strategy_b_payload_reports_coverage_and_zero_suppression(monkeypatch):
    captured = []
    metrics = {
        "date": "2026-09-02",
        "close": 100.0,
        "sma200": 90.0,
        "sma200_20d_ago": 89.0,
        "adx14": 20.0,
        "rsi14": 55.0,
        "atr20": 2.0,
        "performance_6m": 0.1,
        "performance_12m": 0.2,
        "below_sma200_10d": False,
    }
    no_candidate = {
        "conditions": {"close_gt_sma200": True, "sma200_rising_20d": True, "adx_gt_30": False},
        "buy_signal": False,
        "exit_signal": False,
        "exit_reasons": [],
    }

    monkeypatch.setattr(strategy_b_scan, "write_payload", captured.append)
    monkeypatch.setattr(strategy_b_scan, "last_completed_xetra_session", lambda: date(2026, 9, 2))
    monkeypatch.setattr(strategy_b_scan, "fetch_yahoo_daily", lambda *_args: pd.DataFrame({"date": ["2026-09-02"]}))
    monkeypatch.setattr(strategy_b_scan, "keep_completed_sessions", lambda raw, _expected: raw)
    monkeypatch.setattr(strategy_b_scan, "compute_strategy_b_metrics", lambda _df: metrics)
    monkeypatch.setattr(strategy_b_scan, "evaluate_strategy_b", lambda _metrics: no_candidate)

    strategy_b_scan.main()

    payload = captured[0]
    assert payload["coverage"] == {
        "instruments_total": 1,
        "instruments_with_required_history": 1,
        "ratio": 1.0,
        "minimum_bars_required": 253,
        "missing_or_short": [],
    }
    assert payload["stale_cached_candidate_count"] == 0


def test_data_unavailable_strategy_b_payload_reports_zero_suppression(monkeypatch):
    captured = []

    def unavailable(*_args):
        raise StrategyBDataError("unavailable fixture")

    monkeypatch.setattr(strategy_b_scan, "write_payload", captured.append)
    monkeypatch.setattr(strategy_b_scan, "last_completed_xetra_session", lambda: date(2026, 9, 2))
    monkeypatch.setattr(strategy_b_scan, "fetch_yahoo_daily", unavailable)

    strategy_b_scan.main()

    payload = captured[0]
    assert payload["coverage"] == {
        "instruments_total": 1,
        "instruments_with_required_history": 0,
        "ratio": 0.0,
        "minimum_bars_required": 253,
        "missing_or_short": ["IS3R"],
    }
    assert payload["stale_cached_candidate_count"] == 0
