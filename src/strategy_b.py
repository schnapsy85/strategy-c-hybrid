from __future__ import annotations

import math

import pandas as pd


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(100.0).where(avg_gain.notna())


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = _wilder(_true_range(df), period)
    plus_di = 100.0 * _wilder(plus_dm, period) / atr
    minus_di = 100.0 * _wilder(minus_dm, period) / atr
    denominator = (plus_di + minus_di).replace(0.0, float("nan"))
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    return _wilder(dx, period)


def compute_strategy_b_metrics(df: pd.DataFrame) -> dict:
    """Calculate the Strategy B end-of-day metrics for the momentum ETF."""
    required = {"date", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing Strategy B columns: {sorted(missing)}")

    work = df.sort_values("date").drop_duplicates("date", keep="last").copy()
    if len(work) < 253:
        raise ValueError(f"Strategy B requires at least 253 daily bars, got {len(work)}")

    close = work["close"].astype(float)
    sma200 = close.rolling(200).mean()
    rsi14 = _rsi(close, 14)
    atr20 = _wilder(_true_range(work), 20)
    adx14 = _adx(work, 14)

    latest = len(work) - 1
    values = {
        "date": pd.Timestamp(work.iloc[-1]["date"]).date().isoformat(),
        "close": float(close.iloc[latest]),
        "sma200": float(sma200.iloc[latest]),
        "sma200_20d_ago": float(sma200.iloc[-21]),
        "adx14": float(adx14.iloc[latest]),
        "rsi14": float(rsi14.iloc[latest]),
        "atr20": float(atr20.iloc[latest]),
        "performance_6m": float(close.iloc[-1] / close.iloc[-127] - 1.0),
        "performance_12m": float(close.iloc[-1] / close.iloc[-253] - 1.0),
        "below_sma200_10d": bool((close.iloc[-10:].to_numpy() < sma200.iloc[-10:].to_numpy()).all()),
    }
    if any(isinstance(v, float) and (math.isnan(v) or math.isinf(v)) for v in values.values()):
        raise ValueError("Strategy B metrics contain non-finite values")
    return values


def evaluate_strategy_b(metrics: dict) -> dict:
    """Apply the fixed Strategy B entry and exit rules to precomputed metrics."""
    conditions = {
        "close_gt_sma200": float(metrics["close"]) > float(metrics["sma200"]),
        "sma200_rising_20d": float(metrics["sma200"]) > float(metrics["sma200_20d_ago"]),
        "adx_gt_30": float(metrics["adx14"]) > 30.0,
    }
    exit_reasons = []
    if bool(metrics.get("below_sma200_10d", False)):
        exit_reasons.append("10_consecutive_closes_below_sma200")
    if float(metrics["sma200"]) < float(metrics["sma200_20d_ago"]):
        exit_reasons.append("sma200_falling")
    return {
        "conditions": conditions,
        "buy_signal": all(conditions.values()),
        "exit_signal": bool(exit_reasons),
        "exit_reasons": exit_reasons,
    }
