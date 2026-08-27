from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np
import pandas as pd

from .indicators import compute_strategy_c_indicators


def _finite(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


@dataclass
class LatestMetrics:
    ticker: str
    date: str
    close: float | None
    rsi14: float | None
    dynamic_rsi: float | None
    lower: float | None
    adaptive_midline: float | None
    upper: float | None
    sma200: float | None
    sma200_20d_ago: float | None
    midline_5d_ago: float | None
    atr14: float | None
    prev20_high: float | None
    volume: float | None
    prev20_volume_avg: float | None
    trend_filter: bool
    c1: bool
    c2: bool
    exit_condition_day: bool
    watch_reason: str | None


def evaluate_ticker(df: pd.DataFrame, ticker: str, cfg: dict) -> tuple[LatestMetrics | None, pd.DataFrame]:
    if len(df) < int(cfg["min_history_bars"]):
        return None, pd.DataFrame()

    x = compute_strategy_c_indicators(df, cfg)
    if len(x) < 3:
        return None, x
    cur = x.iloc[-1]
    prev = x.iloc[-2]

    slope_n = int(cfg["sma_slope_lookback"])
    mid_slope_n = int(cfg["midline_slope_lookback"])
    if len(x) <= max(slope_n, mid_slope_n):
        return None, x

    sma_ago = x["sma200"].iloc[-1 - slope_n]
    mid_ago = x["adaptive_midline"].iloc[-1 - mid_slope_n]

    required = [
        cur["close"], cur["rsi14"], cur["dynamic_rsi"], cur["lower"],
        cur["adaptive_midline"], cur["upper"], cur["sma200"], cur["atr14"],
        sma_ago, mid_ago, prev["dynamic_rsi"], prev["lower"], prev["upper"],
    ]
    if any(not np.isfinite(float(v)) for v in required):
        return None, x

    trend_filter = bool(
        cur["close"] > cur["sma200"]
        and cur["sma200"] > sma_ago
        and cur["adaptive_midline"] > 50.0
        and cur["adaptive_midline"] > mid_ago
    )

    c1 = bool(
        trend_filter
        and prev["dynamic_rsi"] <= prev["lower"]
        and cur["dynamic_rsi"] > cur["lower"]
        and cur["dynamic_rsi"] > prev["dynamic_rsi"]
    )

    c2 = bool(
        trend_filter
        and prev["dynamic_rsi"] <= prev["upper"]
        and cur["dynamic_rsi"] > cur["upper"]
        and np.isfinite(cur["prev20_high"])
        and cur["close"] > cur["prev20_high"]
        and np.isfinite(cur["prev20_volume_avg"])
        and cur["volume"] > cur["prev20_volume_avg"]
    )

    midline_cross = bool(
        trend_filter
        and prev["dynamic_rsi"] <= prev["adaptive_midline"]
        and cur["dynamic_rsi"] > cur["adaptive_midline"]
        and not c1
        and not c2
    )

    watch_reason: str | None = None
    if trend_filter and not c1 and not c2:
        distance = float(cfg.get("watch_distance_rsi_points", 2.5))
        if midline_cross:
            watch_reason = "dynamic_rsi_crossed_adaptive_midline"
        elif abs(float(cur["dynamic_rsi"] - cur["lower"])) <= distance:
            watch_reason = "near_lower_band"
        elif abs(float(cur["dynamic_rsi"] - cur["upper"])) <= distance:
            watch_reason = "near_upper_band"

    exit_condition_day = bool(
        cur["adaptive_midline"] < 50.0
        and cur["dynamic_rsi"] < cur["adaptive_midline"]
    )

    metrics = LatestMetrics(
        ticker=ticker,
        date=pd.Timestamp(cur["date"]).date().isoformat(),
        close=_finite(cur["close"]),
        rsi14=_finite(cur["rsi14"]),
        dynamic_rsi=_finite(cur["dynamic_rsi"]),
        lower=_finite(cur["lower"]),
        adaptive_midline=_finite(cur["adaptive_midline"]),
        upper=_finite(cur["upper"]),
        sma200=_finite(cur["sma200"]),
        sma200_20d_ago=_finite(sma_ago),
        midline_5d_ago=_finite(mid_ago),
        atr14=_finite(cur["atr14"]),
        prev20_high=_finite(cur["prev20_high"]),
        volume=_finite(cur["volume"]),
        prev20_volume_avg=_finite(cur["prev20_volume_avg"]),
        trend_filter=trend_filter,
        c1=c1,
        c2=c2,
        exit_condition_day=exit_condition_day,
        watch_reason=watch_reason,
    )
    return metrics, x


def build_signal(metrics: LatestMetrics, cfg: dict, name: str, sector: str) -> dict[str, Any]:
    if not (metrics.c1 or metrics.c2):
        raise ValueError("build_signal called without C1/C2")
    assert metrics.close is not None and metrics.atr14 is not None

    signal_type = "C1" if metrics.c1 else "C2"
    max_open = metrics.close + float(cfg["gap_filter_atr_multiple"]) * metrics.atr14
    initial_stop = metrics.close - float(cfg["initial_stop_atr_multiple"]) * metrics.atr14
    capital = float(cfg["capital_eur"])
    risk_eur = capital * float(cfg["risk_per_trade_pct"]) / 100.0
    risk_per_share = metrics.close - initial_stop
    shares_by_risk = risk_eur / risk_per_share if risk_per_share > 0 else 0.0
    max_position_eur = capital * float(cfg["max_position_pct"]) / 100.0
    shares_by_cap = max_position_eur / metrics.close if metrics.close > 0 else 0.0
    shares = max(0.0, min(shares_by_risk, shares_by_cap))
    position_eur = shares * metrics.close

    return {
        "ticker": metrics.ticker,
        "name": name,
        "sector": sector,
        "signal": signal_type,
        "signal_date": metrics.date,
        "close": metrics.close,
        "rsi14": metrics.rsi14,
        "dynamic_rsi": metrics.dynamic_rsi,
        "lower": metrics.lower,
        "adaptive_midline": metrics.adaptive_midline,
        "upper": metrics.upper,
        "sma200": metrics.sma200,
        "sma200_20d_ago": metrics.sma200_20d_ago,
        "atr14": metrics.atr14,
        "volume": metrics.volume,
        "prev20_volume_avg": metrics.prev20_volume_avg,
        "prev20_high": metrics.prev20_high,
        "max_next_open": max_open,
        "initial_stop_reference": initial_stop,
        "risk_budget_eur_reference": risk_eur,
        "position_shares_reference": shares,
        "position_eur_reference": position_eur,
        "position_size_note": "Reference only; ChatGPT should recompute from actual Strategy C capital and executable Scalable price before order preview."
    }


def metrics_to_dict(metrics: LatestMetrics) -> dict[str, Any]:
    return asdict(metrics)
