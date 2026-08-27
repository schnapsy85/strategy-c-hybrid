from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]


def load_store(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(p, compression="gzip", parse_dates=["date"])
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["ticker"] = df["ticker"].astype(str)
    return df[COLUMNS].sort_values(["ticker", "date"]).reset_index(drop=True)


def save_store(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = df[COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out.drop_duplicates(subset=["ticker", "date"], keep="last")
    out = out.sort_values(["ticker", "date"])
    out.to_csv(p, index=False, compression="gzip")


def append_rows(existing: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return existing.copy()
    combined = pd.concat([existing, rows], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    return combined.sort_values(["ticker", "date"]).reset_index(drop=True)
