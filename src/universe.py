from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

WIKIPEDIA_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKIPEDIA_NASDAQ100 = "https://en.wikipedia.org/wiki/Nasdaq-100"
HEADERS = {"User-Agent": "strategy-c-hybrid/1.0"}


def _read_tables(url: str) -> list[pd.DataFrame]:
    html = requests.get(url, headers=HEADERS, timeout=30)
    html.raise_for_status()
    return pd.read_html(StringIO(html.text))


def load_sp500_members() -> pd.DataFrame:
    """Return current S&P 500 members.

    Columns: ticker, security, sector, sub_industry.
    """
    tables = _read_tables(WIKIPEDIA_SP500)
    if not tables:
        raise RuntimeError("Could not read the S&P 500 constituents table")
    table = tables[0].copy()
    required = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}
    if not required.issubset(table.columns):
        raise RuntimeError(f"Unexpected S&P 500 table columns: {list(table.columns)}")

    out = table[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    out.columns = ["ticker", "security", "sector", "sub_industry"]
    out["ticker"] = out["ticker"].astype(str).str.strip().map(normalize_massive_ticker)
    return out.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)


def load_nasdaq100_members() -> pd.DataFrame:
    """Return current Nasdaq-100 members.

    Wikipedia occasionally changes the exact table position, so select the
    constituents table by its columns rather than by a fixed index.
    Columns returned: ticker, security, sector, sub_industry.
    """
    tables = _read_tables(WIKIPEDIA_NASDAQ100)
    table = None
    for candidate in tables:
        cols = {str(c).strip() for c in candidate.columns}
        if "Ticker" in cols and ("Company" in cols or "Company name" in cols):
            table = candidate.copy()
            break
    if table is None:
        raise RuntimeError("Could not identify the Nasdaq-100 constituents table")

    company_col = "Company" if "Company" in table.columns else "Company name"
    sector_col = "GICS Sector" if "GICS Sector" in table.columns else ("Sector" if "Sector" in table.columns else None)
    sub_col = "GICS Sub-Industry" if "GICS Sub-Industry" in table.columns else ("Subsector" if "Subsector" in table.columns else None)

    out = pd.DataFrame({
        "ticker": table["Ticker"].astype(str).str.strip().map(normalize_massive_ticker),
        "security": table[company_col].astype(str).str.strip(),
        "sector": table[sector_col].astype(str).str.strip() if sector_col else "",
        "sub_industry": table[sub_col].astype(str).str.strip() if sub_col else "",
    })
    return out.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)


def load_combined_members() -> pd.DataFrame:
    """Union used by the shared OHLCV store for Strategies A and C."""
    sp = load_sp500_members().assign(in_sp500=True, in_nasdaq100=False)
    ndx = load_nasdaq100_members().assign(in_sp500=False, in_nasdaq100=True)
    combined = pd.concat([sp, ndx], ignore_index=True)
    combined = combined.groupby("ticker", as_index=False).agg({
        "security": "first",
        "sector": "first",
        "sub_industry": "first",
        "in_sp500": "max",
        "in_nasdaq100": "max",
    })
    return combined.sort_values("ticker").reset_index(drop=True)


def normalize_massive_ticker(ticker: str) -> str:
    # Massive/Polygon convention uses a dot for class shares (e.g. BRK.B, BF.B).
    return ticker.strip().upper().replace("-", ".")
