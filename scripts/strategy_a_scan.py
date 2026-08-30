from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_calendar import last_completed_us_session
from src.storage import load_store
from src.universe import load_nasdaq100_members

STORE = ROOT / "data" / "ohlcv.csv.gz"
OUTPUT = ROOT / "docs" / "strategy_a_latest.json"
MIN_BARS_FOR_A = 220


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
    if len(tdf) < MIN_BARS_FOR_A:
        return None
    close = tdf["close"].astype(float)
    high = tdf["high"].astype(float)
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    sma200 = close.rolling(200).mean()
    atr20 = atr(tdf, 20)
    prior100_high = high.shift(1).rolling(100).max()
    if pd.isna(atr20.iloc[-21]) or pd.isna(sma200.iloc[-1]) or pd.isna(prior100_high.iloc[-1]):
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

    bar_counts = {}
    metrics = {}
    for ticker in sorted(tickers):
        tdf = store[store["ticker"] == ticker]
        bar_count = int(tdf["date"].nunique()) if not tdf.empty else 0
        bar_counts[ticker] = bar_count
        m = metrics_for(tdf)
        if m is not None:
            metrics[ticker] = m

    insufficient_history = [
        {"ticker": t, "bars": bar_counts[t]}
        for t in sorted(tickers)
        if t not in metrics
    ]

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
    analysis_coverage = len(metrics) / len(tickers) if tickers else 0.0
    expected_date = last_completed_us_session().isoformat()
    freshness_pass = latest_date == expected_date
    signals = raw_signals if freshness_pass else []

    if not freshness_pass:
        status = "stale_data"
    elif analysis_coverage < 0.95:
        status = "partial_history"
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
            "reason": None if freshness_pass else f"Expected last completed US trading session {expected_date}, but latest available data is {latest_date}. Cached candidates were suppressed.",
        },
        "universe": {
            "source": "Current Nasdaq-100 constituents table from Wikipedia; component count cross-check against Nasdaq official NDX component count",
            "components_loaded": len(tickers),
            "expected_component_count": 102,
            "complete": len(tickers) == 102,
            "note": "Nasdaq-100 represents 100 companies but currently has 102 securities/components because some companies have multiple share classes.",
        },
        "analysis_coverage": {
            "components_total": len(tickers),
            "components_with_required_history": len(metrics),
            "ratio": analysis_coverage,
            "minimum_bars_required": MIN_BARS_FOR_A,
            "insufficient_history": insufficient_history,
            "note": "A component can be present in the Nasdaq-100 universe but not yet analyzable when fewer than 220 daily bars are available for SMA200/EMA/ATR/ranking calculations.",
        },
        "ranking": {
            "method": "exact price performance over 126 trading days",
            "eligible_count": len(ranked),
            "top_quartile_count": top_count,
        },
        "signals": signals,
        "stale_cached_candidate_count": 0 if freshness_pass else len(raw_signals),
        "metrics_by_ticker": metrics,
        "important": "Research output only. Universe completeness and indicator-history coverage are reported separately. Stale cached candidates are never published as current signals. Recheck current quote, portfolio limits, available capital and executable broker price before order preview."
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Strategy A universe: {len(tickers)}/102 components loaded")
    print(f"Strategy A analyzable history: {len(metrics)}/{len(tickers)} ({analysis_coverage:.1%})")
    if insufficient_history:
        print("Insufficient history: " + ", ".join(f"{x['ticker']}({x['bars']})" for x in insufficient_history))
    print(f"Strategy A freshness: {freshness_pass} expected={expected_date} latest={latest_date}")
    print(f"Strategy A signals: {len(signals)}")
    if not freshness_pass and raw_signals:
        print(f"Suppressed {len(raw_signals)} stale cached Strategy A candidate(s).")
    for s in signals:
        print(f"SIGNAL A {s['ticker']} close={s['close']:.2f} rank126={s['rank_126d']}/{len(ranked)}")


if __name__ == "__main__":
    main()
