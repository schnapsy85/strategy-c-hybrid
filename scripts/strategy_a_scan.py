from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.storage import load_store
from src.universe import load_nasdaq100_members

STORE = ROOT / "data" / "ohlcv.csv.gz"
OUTPUT = ROOT / "docs" / "strategy_a_latest.json"


def atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def metrics_for(tdf: pd.DataFrame) -> dict | None:
    tdf = tdf.sort_values("date").drop_duplicates("date", keep="last").copy()
    if len(tdf) < 220:
        return None
    close = tdf["close"].astype(float)
    high = tdf["high"].astype(float)
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    sma200 = close.rolling(200).mean()
    atr20 = atr(tdf, 20)
    prior100_high = high.shift(1).rolling(100).max()
    if len(tdf) < 147 or pd.isna(atr20.iloc[-21]):
        return None
    perf126 = float(close.iloc[-1] / close.iloc[-127] - 1.0)
    return {
        "date": pd.Timestamp(tdf.iloc[-1]["date"]).date().isoformat(),
        "close": float(close.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "ema100": float(ema100.iloc[-1]),
        "sma200": float(sma200.iloc[-1]),
        "prior_100d_high": float(prior100_high.iloc[-1]),
        "atr20": float(atr20.iloc[-1]),
        "atr20_20d_ago": float(atr20.iloc[-21]),
        "performance_126d": perf126,
    }


def main() -> None:
    universe = load_nasdaq100_members()
    meta = universe.set_index("ticker").to_dict("index")
    tickers = set(universe["ticker"])
    store = load_store(STORE)

    metrics = {}
    for ticker in sorted(tickers):
        m = metrics_for(store[store["ticker"] == ticker])
        if m is not None:
            metrics[ticker] = m

    ranked = sorted(metrics, key=lambda t: metrics[t]["performance_126d"], reverse=True)
    top_count = max(1, (len(ranked) + 3) // 4)
    top_quartile = set(ranked[:top_count])
    rank_map = {ticker: i + 1 for i, ticker in enumerate(ranked)}

    raw_signals = []
    for ticker, m in metrics.items():
        conditions = {
            "close_gt_ema50": m["close"] > m["ema50"],
            "ema50_gt_ema100": m["ema50"] > m["ema100"],
            "ema100_gt_sma200": m["ema100"] > m["sma200"],
            "breakout_100d": m["close"] > m["prior_100d_high"],
            "atr_expanding": m["atr20"] > m["atr20_20d_ago"],
            "top_25pct_126d": ticker in top_quartile,
        }
        m["rank_126d"] = rank_map[ticker]
        m["percentile_126d"] = 1.0 - ((rank_map[ticker] - 1) / max(1, len(ranked)))
        m["conditions"] = conditions
        if all(conditions.values()):
            info = meta.get(ticker, {})
            raw_signals.append({
                "ticker": ticker,
                "name": info.get("security", ticker),
                "sector": info.get("sector", ""),
                **m,
            })

    raw_signals.sort(key=lambda x: x["performance_126d"], reverse=True)
    latest_date = max((m["date"] for m in metrics.values()), default=None)
    coverage = len(metrics) / len(tickers) if tickers else 0.0
    expected_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    freshness_pass = latest_date == expected_date
    signals = raw_signals if freshness_pass else []

    if not freshness_pass:
        status = "stale_data"
    elif coverage < 0.95:
        status = "partial_data"
    else:
        status = "ok"

    payload = {
        "generated_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "strategy": "Strategy A - Nasdaq-100 Trend",
        "status": status,
        "latest_data_date": latest_date,
        "freshness": {
            "expected_data_date": expected_date,
            "pass": freshness_pass,
            "reason": None if freshness_pass else f"Expected completed US session {expected_date}, but latest available data is {latest_date}. Cached prior-day candidates were suppressed.",
        },
        "coverage": {
            "members_total": len(tickers),
            "members_with_metrics": len(metrics),
            "ratio": coverage,
        },
        "ranking": {
            "method": "exact price performance over 126 trading days",
            "eligible_count": len(ranked),
            "top_quartile_count": top_count,
        },
        "signals": signals,
        "stale_cached_candidate_count": 0 if freshness_pass else len(raw_signals),
        "metrics_by_ticker": metrics,
        "important": "Research output only. Stale cached candidates are never published as current signals. Recheck current quote, portfolio limits, available capital and executable broker price before order preview."
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Strategy A coverage: {len(metrics)}/{len(tickers)} ({coverage:.1%})")
    print(f"Strategy A freshness: {freshness_pass} expected={expected_date} latest={latest_date}")
    print(f"Strategy A signals: {len(signals)}")
    if not freshness_pass and raw_signals:
        print(f"Suppressed {len(raw_signals)} stale cached Strategy A candidate(s).")
    for s in signals:
        print(f"SIGNAL A {s['ticker']} close={s['close']:.2f} rank126={s['rank_126d']}/{len(ranked)}")


if __name__ == "__main__":
    main()
