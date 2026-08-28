from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

WIKIPEDIA_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKIPEDIA_NASDAQ100 = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
HEADERS = {"User-Agent": "strategy-c-hybrid/1.0"}


def _read_tables(url: str) -> list[pd.DataFrame]:
    html = requests.get(url, headers=HEADERS, timeout=30)
    html.raise_for_status()
    return pd.read_html(StringIO(html.text))


def _flat_columns(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    if isinstance(out.columns, pd.MultiIndex):
        cols = []
        for col in out.columns:
            parts = [str(x).strip() for x in col if str(x).strip() and not str(x).startswith("Unnamed")]
            cols.append(parts[-1] if parts else str(col[-1]).strip())
        out.columns = cols
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def _find_col(columns, names):
    normalized = {str(c).strip().lower(): c for c in columns}
    for name in names:
        if name.lower() in normalized:
            return normalized[name.lower()]
    return None


def load_sp500_members() -> pd.DataFrame:
    tables = _read_tables(WIKIPEDIA_SP500)
    if not tables:
        raise RuntimeError("Could not read the S&P 500 constituents table")
    table = _flat_columns(tables[0])
    required = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}
    if not required.issubset(table.columns):
        raise RuntimeError(f"Unexpected S&P 500 table columns: {list(table.columns)}")
    out = table[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    out.columns = ["ticker", "security", "sector", "sub_industry"]
    out["ticker"] = out["ticker"].astype(str).str.strip().map(normalize_massive_ticker)
    return out.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)


def load_nasdaq100_members() -> pd.DataFrame:
    tables = _read_tables(WIKIPEDIA_NASDAQ100)
    table = None
    ticker_col = company_col = None
    for raw in tables:
        candidate = _flat_columns(raw)
        ticker = _find_col(candidate.columns, ["Ticker", "Ticker symbol", "Symbol"])
        company = _find_col(candidate.columns, ["Company", "Company name", "Security"])
        if ticker is not None and company is not None and len(candidate) >= 90:
            table = candidate
            ticker_col = ticker
            company_col = company
            break
    if table is None:
        available = [list(_flat_columns(t).columns) for t in tables]
        raise RuntimeError(f"Could not identify the Nasdaq-100 constituents table. Tables found: {available}")
    sector_col = _find_col(table.columns, ["GICS Sector", "ICB Industry", "Sector"])
    sub_col = _find_col(table.columns, ["GICS Sub-Industry", "ICB Subsector", "Subsector", "Industry"])
    out = pd.DataFrame({
        "ticker": table[ticker_col].astype(str).str.strip().map(normalize_massive_ticker),
        "security": table[company_col].astype(str).str.strip(),
        "sector": table[sector_col].astype(str).str.strip() if sector_col else "",
        "sub_industry": table[sub_col].astype(str).str.strip() if sub_col else "",
    })
    out = out[out["ticker"].str.match(r"^[A-Z0-9.]+$", na=False)]
    if len(out) < 90:
        raise RuntimeError(f"Nasdaq-100 constituent list unexpectedly short: {len(out)} rows")
    return out.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)


def load_combined_members() -> pd.DataFrame:
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
    return ticker.strip().upper().replace("-", ".")
