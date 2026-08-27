from __future__ import annotations

import numpy as np
import pandas as pd


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce").astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return out

    avg_gain = gain.iloc[1 : period + 1].mean()
    avg_loss = loss.iloc[1 : period + 1].mean()

    def to_rsi(g: float, l: float) -> float:
        if np.isnan(g) or np.isnan(l):
            return np.nan
        if l == 0 and g == 0:
            return 50.0
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)

    out.iloc[period] = to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(close)):
        avg_gain = ((period - 1) * avg_gain + gain.iloc[i]) / period
        avg_loss = ((period - 1) * avg_loss + loss.iloc[i]) / period
        out.iloc[i] = to_rsi(avg_gain, avg_loss)
    return out


def wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(df["high"], errors="coerce").astype(float)
    low = pd.to_numeric(df["low"], errors="coerce").astype(float)
    close = pd.to_numeric(df["close"], errors="coerce").astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    out = pd.Series(np.nan, index=df.index, dtype=float)
    if len(df) < period:
        return out
    atr = tr.iloc[:period].mean()
    out.iloc[period - 1] = atr
    for i in range(period, len(df)):
        atr = ((period - 1) * atr + tr.iloc[i]) / period
        out.iloc[i] = atr
    return out


def rolling_wma(series: pd.Series, period: int = 14) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    denominator = weights.sum()
    return series.rolling(period).apply(lambda x: float(np.dot(x, weights) / denominator), raw=True)


def compute_strategy_c_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    x = df.sort_values("date").copy().reset_index(drop=True)
    rsi_period = int(cfg["rsi_period"])
    lookback = int(cfg["adaptive_lookback"])
    wma_period = int(cfg["wma_period"])
    sma_period = int(cfg["sma_period"])
    breakout_lookback = int(cfg["breakout_lookback"])
    volume_lookback = int(cfg["volume_lookback"])

    x["rsi14"] = wilder_rsi(x["close"], rsi_period)
    x["dynamic_rsi"] = (
        0.4 * x["rsi14"]
        + 0.3 * x["rsi14"].shift(1)
        + 0.2 * x["rsi14"].shift(2)
        + 0.1 * x["rsi14"].shift(3)
    )
    x["highest_rsi_60"] = x["rsi14"].rolling(lookback).max()
    x["lowest_rsi_60"] = x["rsi14"].rolling(lookback).min()
    rsi_range = x["highest_rsi_60"] - x["lowest_rsi_60"]
    x["adaptive_midline"] = 0.5 * rolling_wma(rsi_range, wma_period) + rolling_wma(
        x["lowest_rsi_60"], wma_period
    )
    x["upper"] = x["highest_rsi_60"] - 0.20 * x["adaptive_midline"]
    x["lower"] = x["lowest_rsi_60"] + 0.20 * x["adaptive_midline"]
    x["sma200"] = x["close"].rolling(sma_period).mean()
    x["atr14"] = wilder_atr(x, rsi_period)
    x["prev20_high"] = x["high"].shift(1).rolling(breakout_lookback).max()
    x["prev20_volume_avg"] = x["volume"].shift(1).rolling(volume_lookback).mean()
    return x
