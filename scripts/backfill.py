from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.massive_client import MassiveClient, MassiveAPIError
from src.storage import append_rows, load_store, save_store
from src.universe import load_sp500_members

STORE = ROOT / "data" / "ohlcv.csv.gz"
CONFIG = ROOT / "config.json"


def rows_from_grouped(results: list[dict], allowed: set[str], d: date) -> pd.DataFrame:
    rows = []
    for r in results:
        ticker = str(r.get("T", ""))
        if ticker not in allowed:
            continue
        values = [r.get(k) for k in ("o", "h", "l", "c", "v")]
        if any(v is None for v in values):
            continue
        rows.append({
            "date": d.isoformat(),
            "ticker": ticker,
            "open": r["o"],
            "high": r["h"],
            "low": r["l"],
            "close": r["c"],
            "volume": r["v"],
        })
    return pd.DataFrame(rows)


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    universe = load_sp500_members()
    tickers = set(universe["ticker"].tolist())
    tickers.add(str(cfg["market_proxy"]))

    client = MassiveClient.from_env(int(cfg["massive_calls_per_minute"]))
    store = load_store(STORE)
    existing_dates = set(pd.to_datetime(store["date"]).dt.date.tolist()) if not store.empty else set()

    end = date.today()
    start = end - timedelta(days=int(cfg["backfill_calendar_days"]))
    weekdays = [d.date() for d in pd.bdate_range(start=start, end=end)]
    pending = [d for d in weekdays if d not in existing_dates]

    print(f"Universe: {len(universe)} S&P 500 securities + {cfg['market_proxy']} market proxy")
    print(f"Backfill window: {start} to {end}; pending weekdays: {len(pending)}")

    added = 0
    for i, d in enumerate(pending, 1):
        try:
            results = client.grouped_daily(d)
        except MassiveAPIError as exc:
            print(f"WARN {d}: {exc}")
            continue
        rows = rows_from_grouped(results, tickers, d)
        if rows.empty:
            print(f"{i}/{len(pending)} {d}: no market data (holiday or unavailable)")
            continue
        store = append_rows(store, rows)
        added += len(rows)
        print(f"{i}/{len(pending)} {d}: +{len(rows)} rows")

    save_store(store, STORE)

    counts = store[store["ticker"].isin(tickers)].groupby("ticker").size()
    min_bars = int(cfg["min_history_bars"])
    good = int((counts.reindex(sorted(tickers), fill_value=0) >= min_bars).sum())
    coverage = good / len(tickers) if tickers else 0.0
    print(f"Added rows: {added}")
    print(f"History coverage >= {min_bars} bars: {good}/{len(tickers)} ({coverage:.1%})")


if __name__ == "__main__":
    main()
