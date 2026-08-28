import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from io import StringIO

import requests
import pandas as pd


API_KEY = os.environ["MASSIVE_API_KEY"]

BASE_URL = "https://api.massive.com"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

HISTORY_FILE = DATA_DIR / "history.json"
PROGRESS_FILE = DATA_DIR / "backfill_progress.json"
UNIVERSE_FILE = DATA_DIR / "universe.json"

# Ca. 520 Kalendertage ergeben deutlich über 300 Handelstage
BACKFILL_CALENDAR_DAYS = 520

# Free-Tier schonen
REQUEST_SLEEP_SECONDS = 13

# Anzahl Massive-Requests pro Workflow-Lauf
MAX_REQUESTS_PER_RUN = 120


def load_json(path, default):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    return default


def save_json(path, payload):
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )


def normalize_ticker(ticker):
    """
    Vereinheitlicht Ticker-Schreibweisen.
    Beispiel:
    BRK-B -> BRK.B
    """
    ticker = str(ticker).strip().upper()
    ticker = ticker.replace("-", ".")
    return ticker


# ---------------------------------------------------------
# S&P 500 LADEN
# ---------------------------------------------------------

def fetch_sp500():
    print("Lade aktuelle S&P-500-Mitglieder...")

    url = (
        "https://en.wikipedia.org/wiki/"
        "List_of_S%26P_500_companies"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 strategy-c-hybrid-market-data"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    df = tables[0]

    tickers = set(
        normalize_ticker(x)
        for x in df["Symbol"].dropna().tolist()
    )

    print(
        f"S&P 500: {len(tickers)} Ticker"
    )

    return tickers


# ---------------------------------------------------------
# NASDAQ 100
# ---------------------------------------------------------

def fetch_nasdaq100():
    print("Lade Nasdaq-100-Mitglieder...")

    #
    # Feste Bootstrap-Liste.
    #
    # Hintergrund:
    # Die automatische Wikipedia-/CSV-Erkennung war
    # in GitHub Actions nicht stabil genug.
    #
    # Diese Liste dient zunächst als robuste technische Basis.
    # Später kann sie separat automatisiert aktualisiert werden.
    #

    tickers = {
        "AAPL",
        "ABNB",
        "ADBE",
        "ADI",
        "ADP",
        "ADSK",
        "AEP",
        "ALAB",
        "ALNY",
        "AMAT",
        "AMD",
        "AMGN",
        "AMZN",
        "APP",
        "ARM",
        "ASML",
        "AVGO",
        "AXON",
        "BKNG",
        "BKR",
        "CCEP",
        "CDNS",
        "CEG",
        "CMCSA",
        "COST",
        "CPRT",
        "CRWD",
        "CSCO",
        "CSX",
        "CTAS",
        "DASH",
        "DDOG",
        "DXCM",
        "EA",
        "EXC",
        "FANG",
        "FAST",
        "FTNT",
        "GEHC",
        "GFS",
        "GILD",
        "GOOG",
        "GOOGL",
        "HON",
        "IDXX",
        "INTC",
        "INTU",
        "ISRG",
        "KDP",
        "KHC",
        "KLAC",
        "LIN",
        "LRCX",
        "MAR",
        "MCHP",
        "MDB",
        "MDLZ",
        "MELI",
        "META",
        "MNST",
        "MRVL",
        "MSFT",
        "MSTR",
        "MU",
        "NBIS",
        "NFLX",
        "NVDA",
        "NXPI",
        "ODFL",
        "ON",
        "ORLY",
        "PANW",
        "PAYX",
        "PCAR",
        "PDD",
        "PEP",
        "PLTR",
        "PYPL",
        "QCOM",
        "REGN",
        "RKLB",
        "ROP",
        "ROST",
        "SBUX",
        "SNPS",
        "SPCX",
        "TEAM",
        "TER",
        "TMUS",
        "TSLA",
        "TTD",
        "TTWO",
        "TXN",
        "VRTX",
        "WBD",
        "WDAY",
        "XEL"
    }

    tickers = {
        normalize_ticker(x)
        for x in tickers
    }

    print(
        f"Nasdaq-100: {len(tickers)} Ticker"
    )

    if len(tickers) < 95:
        raise RuntimeError(
            f"Zu wenige Nasdaq-100-Ticker: {len(tickers)}"
        )

    return tickers


# ---------------------------------------------------------
# GESAMTUNIVERSUM
# ---------------------------------------------------------

def build_universe():

    sp500 = fetch_sp500()
    nasdaq100 = fetch_nasdaq100()

    combined = sp500 | nasdaq100

    universe = {
        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "sp500":
            sorted(sp500),

        "nasdaq100":
            sorted(nasdaq100),

        "combined":
            sorted(combined),

        "counts": {
            "sp500":
                len(sp500),

            "nasdaq100":
                len(nasdaq100),

            "combined":
                len(combined)
        }
    }

    save_json(
        UNIVERSE_FILE,
        universe
    )

    print()
    print(
        f"Gesamtuniversum: "
        f"{len(combined)} eindeutige Ticker"
    )
    print()

    return combined


# ---------------------------------------------------------
# HISTORIE
# ---------------------------------------------------------

def load_history():
    return load_json(
        HISTORY_FILE,
        {
            "meta": {},
            "symbols": {}
        }
    )


# ---------------------------------------------------------
# BACKFILL-FORTSCHRITT
# ---------------------------------------------------------

def load_progress():

    default_start = (
        datetime.now(
            timezone.utc
        ).date()
        - timedelta(
            days=BACKFILL_CALENDAR_DAYS
        )
    )

    return load_json(
        PROGRESS_FILE,
        {
            "next_date":
                default_start.isoformat(),

            "completed":
                False
        }
    )


# ---------------------------------------------------------
# MASSIVE DAILY MARKET SUMMARY
# ---------------------------------------------------------

def get_market_day(date_string):

    url = (
        f"{BASE_URL}/v2/aggs/grouped/"
        f"locale/us/market/stocks/{date_string}"
    )

    params = {
        "adjusted": "true",
        "include_otc": "false",
        "apiKey": API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    if response.status_code == 429:
        raise RuntimeError(
            "Massive Rate Limit erreicht."
        )

    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "OK":
        return []

    return payload.get(
        "results",
        []
    )


# ---------------------------------------------------------
# MARKTDATEN FILTERN UND SPEICHERN
# ---------------------------------------------------------

def update_history(
    history,
    date_string,
    rows,
    universe
):

    stored = 0

    for row in rows:

        ticker = normalize_ticker(
            row.get("T", "")
        )

        if not ticker:
            continue

        #
        # Nur Nasdaq-100 oder S&P 500 speichern
        #
        if ticker not in universe:
            continue

        candle = {
            "date":
                date_string,

            "open":
                row.get("o"),

            "high":
                row.get("h"),

            "low":
                row.get("l"),

            "close":
                row.get("c"),

            "volume":
                row.get("v"),

            "vwap":
                row.get("vw")
        }

        candles = history[
            "symbols"
        ].setdefault(
            ticker,
            []
        )

        #
        # Falls der Tag schon existiert:
        # vorhandenen Eintrag ersetzen
        #
        candles = [
            x
            for x in candles
            if x.get("date")
            != date_string
        ]

        candles.append(
            candle
        )

        candles.sort(
            key=lambda x:
                x["date"]
        )

        history[
            "symbols"
        ][ticker] = candles

        stored += 1

    return stored


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print()
    print(
        "===================================="
    )
    print(
        "NASDAQ-100 + S&P-500 BACKFILL"
    )
    print(
        "===================================="
    )
    print()

    universe = build_universe()

    history = load_history()
    progress = load_progress()

    #
    # Falls eine alte history.json aus dem ersten
    # Test mit >14.000 Symbolen existieren sollte:
    # nur relevante Aktien behalten.
    #
    history["symbols"] = {
        normalize_ticker(ticker): candles
        for ticker, candles
        in history.get(
            "symbols",
            {}
        ).items()
        if normalize_ticker(
            ticker
        ) in universe
    }

    if progress.get(
        "completed"
    ):

        print(
            "Backfill bereits abgeschlossen."
        )

        return

    current_date = (
        datetime.fromisoformat(
            progress[
                "next_date"
            ]
        ).date()
    )

    today = datetime.now(
        timezone.utc
    ).date()

    request_count = 0
    trading_days_found = 0

    while (
        current_date
        <= today
    ):

        if (
            request_count
            >= MAX_REQUESTS_PER_RUN
        ):

            print()
            print(
                "Maximale Requests für "
                "diesen Lauf erreicht."
            )

            break

        date_string = (
            current_date.isoformat()
        )

        print(
            f"Lade {date_string}..."
        )

        try:

            rows = get_market_day(
                date_string
            )

            request_count += 1

        except Exception as exc:

            print()
            print(
                f"Fehler bei "
                f"{date_string}: "
                f"{exc}"
            )

            #
            # Fortschritt speichern
            #
            progress[
                "next_date"
            ] = date_string

            save_json(
                HISTORY_FILE,
                history
            )

            save_json(
                PROGRESS_FILE,
                progress
            )

            #
            # Nicht hart abbrechen.
            # Dadurch kann GitHub anschließend
            # die Dateien noch committen.
            #
            break

        if rows:

            stored = (
                update_history(
                    history,
                    date_string,
                    rows,
                    universe
                )
            )

            print(
                f"{date_string}: "
                f"{len(rows)} Marktwerte, "
                f"{stored} relevante gespeichert"
            )

            trading_days_found += 1

        else:

            print(
                f"{date_string}: "
                "kein Handel / keine Daten"
            )

        current_date += (
            timedelta(
                days=1
            )
        )

        progress[
            "next_date"
        ] = (
            current_date.isoformat()
        )

        #
        # Nach jedem Tag speichern.
        # Dadurch geht bei Abbruch
        # kein Fortschritt verloren.
        #
        save_json(
            HISTORY_FILE,
            history
        )

        save_json(
            PROGRESS_FILE,
            progress
        )

        time.sleep(
            REQUEST_SLEEP_SECONDS
        )

    #
    # Ziel erreicht
    #
    if (
        current_date
        > today
    ):

        progress[
            "completed"
        ] = True

    #
    # Metadaten aktualisieren
    #
    history[
        "meta"
    ] = {

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "Massive",

        "symbol_count":
            len(
                history[
                    "symbols"
                ]
            ),

        "universe_size":
            len(
                universe
            ),

        "backfill_completed":
            progress.get(
                "completed",
                False
            ),

        "next_date":
            progress.get(
                "next_date"
            )
    }

    save_json(
        HISTORY_FILE,
        history
    )

    save_json(
        PROGRESS_FILE,
        progress
    )

    print()
    print(
        "===================================="
    )
    print(
        "BACKFILL STATUS"
    )
    print(
        "===================================="
    )

    print(
        f"Requests: "
        f"{request_count}"
    )

    print(
        f"Handelstage gefunden: "
        f"{trading_days_found}"
    )

    print(
        f"Gespeicherte Symbole: "
        f"{len(history['symbols'])}"
    )

    print(
        f"Nächster Tag: "
        f"{progress.get('next_date')}"
    )

    print(
        f"Fertig: "
        f"{progress.get('completed')}"
    )

    print()
    print(
        "Backfill-Lauf beendet."
    )


if __name__ == "__main__":
    main()
