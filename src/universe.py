from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

WIKIPEDIA_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def load_sp500_members() -> pd.DataFrame:
    """Return current S&P 500 members from Wikipedia.

    Columns: ticker, security, sector, sub_industry.
    """
    headers = {"User-Agent": "strategy-c-hybrid/1.0"}
    html = requests.get(WIKIPEDIA_SP500, headers=headers, timeout=30)
    html.raise_for_status()
    tables = pd.read_html(StringIO(html.text))
    if not tables:
        raise RuntimeError("Could not read the S&P 500 constituents table")
    table = tables[0].copy()
    required = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}
    if not required.issubset(table.columns):
        raise RuntimeError(f"Unexpected S&P 500 table columns: {list(table.columns)}")

    out = table[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    out.columns = ["ticker", "security", "sector", "sub_industry"]
    out["ticker"] = out["ticker"].astype(str).str.strip().map(normalize_massive_ticker)
    out = out.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)
    return out


def normalize_massive_ticker(ticker: str) -> str:
    # Massive/Polygon convention uses a dot for class shares (e.g. BRK.B, BF.B).
    return ticker.strip().upper().replace("-", ".")
