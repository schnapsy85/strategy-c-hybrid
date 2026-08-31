from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 strategy-c-hybrid/1.0"}


class StrategyBDataError(RuntimeError):
    pass


def fetch_yahoo_daily(symbol: str = "IS3R.DE", range_: str = "3y") -> pd.DataFrame:
    """Fetch daily OHLCV for Strategy B from Yahoo Finance's chart endpoint."""
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"range": range_, "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"},
        headers=HEADERS,
        timeout=30,
    )
    if response.status_code != 200:
        raise StrategyBDataError(f"Yahoo Finance HTTP {response.status_code}: {response.text[:300]}")
    try:
        chart = response.json()["chart"]
        if chart.get("error"):
            raise StrategyBDataError(str(chart["error"]))
        result = chart["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise StrategyBDataError(f"Unexpected Yahoo Finance response for {symbol}: {exc}") from exc

    rows = []
    tz = ZoneInfo("Europe/Berlin")
    for i, ts in enumerate(timestamps):
        values = {k: quote.get(k, [None] * len(timestamps))[i] for k in ("open", "high", "low", "close", "volume")}
        if any(values[k] is None for k in ("open", "high", "low", "close")):
            continue
        rows.append({
            "date": datetime.fromtimestamp(int(ts), tz=ZoneInfo("UTC")).astimezone(tz).date().isoformat(),
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": int(values["volume"] or 0),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise StrategyBDataError(f"No daily OHLCV returned for {symbol}")
    return df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
