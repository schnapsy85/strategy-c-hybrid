from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.massive_client import MassiveClient, MassiveAPIError
from src.scanner import build_signal, evaluate_ticker, metrics_to_dict
from src.storage import append_rows, load_store, save_store
from src.universe import load_sp500_members

STORE = ROOT / "data" / "ohlcv.csv.gz"
CONFIG = ROOT / "config.json"
OUTPUT = ROOT / "docs" / "latest.json"


def scheduled_time_guard(cfg: dict) -> bool:
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return True
    now = datetime.now(ZoneInfo(str(cfg["timezone"])))
    return now.hour == 22


def rows_from_grouped(results: list[dict], allowed: set[str], d: date) -> pd.DataFrame:
    rows = []
    for r in results:
        ticker = str(r.get("T", ""))
        if ticker not in allowed:
            continue
        if any(r.get(k) is None for k in ("o", "h", "l", "c", "v")):
            continue
        rows.append({
            "date": d.isoformat(), "ticker": ticker,
            "open": r["o"], "high": r["h"], "low": r["l"],
            "close": r["c"], "volume": r["v"],
        })
    return pd.DataFrame(rows)


def rows_from_range(results: list[dict], ticker: str) -> pd.DataFrame:
    rows = []
    for r in results:
        if any(r.get(k) is None for k in ("o", "h", "l", "c", "v", "t")):
            continue
        d = pd.to_datetime(int(r["t"]), unit="ms", utc=True).date().isoformat()
        rows.append({
            "date": d, "ticker": ticker,
            "open": r["o"], "high": r["h"], "low": r["l"],
            "close": r["c"], "volume": r["v"],
        })
    return pd.DataFrame(rows)


def ensure_short_tickers(client: MassiveClient, store: pd.DataFrame, tickers: set[str], cfg: dict) -> pd.DataFrame:
    min_bars = int(cfg["min_history_bars"])
    counts = store.groupby("ticker").size().to_dict() if not store.empty else {}
    missing = [t for t in sorted(tickers) if int(counts.get(t, 0)) < min_bars]
    if not missing:
        return store

    end = date.today()
    start = end - timedelta(days=int(cfg["backfill_calendar_days"]))
    print(f"Backfilling {len(missing)} new/short ticker(s): {', '.join(missing[:20])}")
    for ticker in missing:
        try:
            results = client.daily_range(ticker, start, end)
        except MassiveAPIError as exc:
            print(f"WARN range {ticker}: {exc}")
            continue
        rows = rows_from_range(results, ticker)
        store = append_rows(store, rows)
        print(f"{ticker}: +{len(rows)} range rows")
    return store


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    if not scheduled_time_guard(cfg):
        print("Skipping duplicate UTC cron; not 22:xx Europe/Berlin.")
        return

    universe = load_sp500_members()
    meta = universe.set_index("ticker").to_dict("index")
    sp_tickers = set(universe["ticker"].tolist())
    proxy = str(cfg["market_proxy"])
    index_ticker = str(cfg.get("market_index_ticker", "I:SPX"))
    requested_tickers = set(sp_tickers) | {proxy, index_ticker}

    client = MassiveClient.from_env(int(cfg["massive_calls_per_minute"]))
    store = load_store(STORE)

    ny_today = datetime.now(ZoneInfo("America/New_York")).date()
    grouped = []
    last_current_day_error = None
    for attempt in range(1, 5):
        try:
            grouped = client.grouped_daily(ny_today)
            last_current_day_error = None
        except MassiveAPIError as exc:
            last_current_day_error = str(exc)
            print(f"WARN current grouped day attempt {attempt}: {exc}")
            grouped = []
        if grouped:
            break
        if attempt < 4:
            print(f"No EOD payload yet for {ny_today}; retrying in 60 seconds ({attempt}/4).")
            time.sleep(60)

    current_rows = rows_from_grouped(grouped, requested_tickers, ny_today)
    current_day_available = not current_rows.empty
    if current_day_available:
        store = append_rows(store, current_rows)
        print(f"Updated {ny_today}: {len(current_rows)} rows")
    else:
        print(f"No grouped rows for {ny_today}; cached history may be stale. Signals will not be published as current.")

    store = ensure_short_tickers(client, store, requested_tickers, cfg)
    save_store(store, STORE)

    min_bars = int(cfg["min_history_bars"])
    counts = store[store["ticker"].isin(sp_tickers)].groupby("ticker").size()
    eligible = [t for t in sorted(sp_tickers) if int(counts.get(t, 0)) >= min_bars]
    missing = [t for t in sorted(sp_tickers) if t not in eligible]

    market_ticker = index_ticker if bool(cfg.get("prefer_exact_index", True)) else proxy
    market_df = store[store["ticker"] == market_ticker].sort_values("date")
    if len(market_df) < int(cfg["sma_period"]):
        market_ticker = proxy
        market_df = store[store["ticker"] == market_ticker].sort_values("date")

    proxy_market_filter = False
    proxy_close = None
    proxy_sma200 = None
    proxy_date = None
    if len(market_df) >= int(cfg["sma_period"]):
        proxy_close = float(market_df.iloc[-1]["close"])
        proxy_sma200 = float(market_df["close"].rolling(int(cfg["sma_period"])).mean().iloc[-1])
        proxy_date = pd.Timestamp(market_df.iloc[-1]["date"]).date().isoformat()
        proxy_market_filter = bool(proxy_close > proxy_sma200)

    raw_signals = []
    raw_watches = []
    all_metrics = {}
    for ticker in eligible:
        tdf = store[store["ticker"] == ticker].sort_values("date").copy()
        metrics, _ = evaluate_ticker(tdf, ticker, cfg)
        if metrics is None:
            continue
        all_metrics[ticker] = metrics_to_dict(metrics)
        if not proxy_market_filter:
            continue
        if metrics.c1 or metrics.c2:
            m = meta.get(ticker, {})
            raw_signals.append(build_signal(metrics, cfg, m.get("security", ticker), m.get("sector", "")))
        elif metrics.watch_reason:
            m = meta.get(ticker, {})
            raw_watches.append({
                "ticker": ticker,
                "name": m.get("security", ticker),
                "sector": m.get("sector", ""),
                "date": metrics.date,
                "reason": metrics.watch_reason,
                "close": metrics.close,
                "dynamic_rsi": metrics.dynamic_rsi,
                "lower": metrics.lower,
                "adaptive_midline": metrics.adaptive_midline,
                "upper": metrics.upper,
                "sma200": metrics.sma200,
                "atr14": metrics.atr14,
            })

    raw_signals.sort(key=lambda s: (0 if s["signal"] == "C1" else 1, s["ticker"]))
    raw_watches = raw_watches[:30]

    coverage = len(eligible) / len(sp_tickers) if sp_tickers else 0.0
    latest_data_date = None
    if not store.empty:
        latest_data_date = pd.to_datetime(store["date"]).max().date().isoformat()

    expected_date = ny_today.isoformat()
    freshness_pass = latest_data_date == expected_date and current_day_available
    stale_reason = None
    if not freshness_pass:
        stale_reason = (
            f"Expected completed US session {expected_date}, but latest available data is {latest_data_date}. "
            "Current-day EOD data was unavailable from the configured Massive entitlement."
        )

    # Critical safety rule: never expose cached prior-day candidates as current signals.
    signals = raw_signals if freshness_pass else []
    watches = raw_watches if freshness_pass else []

    if not freshness_pass:
        status = "stale_data"
    elif coverage < 0.98:
        status = "partial_data"
    else:
        status = "ok"

    payload = {
        "generated_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "strategy": cfg["strategy_name"],
        "status": status,
        "data_source": {
            "primary": "Massive Stocks Daily Market Summary (adjusted OHLCV)",
            "constituents": "Current S&P 500 table from Wikipedia",
            "market_filter_ticker_used": market_ticker,
            "market_filter_note": "Uses I:SPX when Massive Indices Basic is active; otherwise falls back to SPY."
        },
        "latest_data_date": latest_data_date,
        "freshness": {
            "expected_data_date": expected_date,
            "current_day_payload_available": current_day_available,
            "pass": freshness_pass,
            "reason": stale_reason,
            "provider_error": last_current_day_error,
        },
        "coverage": {
            "members_total": len(sp_tickers),
            "members_with_min_history": len(eligible),
            "ratio": coverage,
            "min_history_bars": min_bars,
            "missing_or_short": missing,
        },
        "market_filter": {
            "ticker_used": market_ticker,
            "date": proxy_date,
            "close": proxy_close,
            "sma200": proxy_sma200,
            "pass": proxy_market_filter if freshness_pass else None,
        },
        "signals": signals,
        "watch": watches,
        "stale_cached_candidate_count": 0 if freshness_pass else len(raw_signals),
        "metrics_by_ticker": all_metrics,
        "capital_reference_eur": float(cfg["capital_eur"]),
        "important": "Signals are research output, not orders. Stale cached candidates are never published as current signals. Recheck actual Strategy C capital, next-session gap filter and executable Scalable quote before any order preview."
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Coverage: {len(eligible)}/{len(sp_tickers)} ({coverage:.1%})")
    print(f"Freshness: {freshness_pass} expected={expected_date} latest={latest_data_date}")
    print(f"Market filter ({market_ticker} > SMA200): {proxy_market_filter if freshness_pass else 'NOT CURRENT'}")
    print(f"Signals: {len(signals)} | Watch: {len(watches)}")
    if not freshness_pass and raw_signals:
        print(f"Suppressed {len(raw_signals)} stale cached candidate(s).")
    for s in signals:
        print(f"SIGNAL {s['signal']} {s['ticker']} close={s['close']:.2f} max_next_open={s['max_next_open']:.2f}")


if __name__ == "__main__":
    main()
