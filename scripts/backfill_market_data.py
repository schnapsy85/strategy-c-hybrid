import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests


API_KEY = os.environ["MASSIVE_API_KEY"]

BASE_URL = "https://api.massive.com"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

HISTORY_FILE = DATA_DIR / "history.json"
PROGRESS_FILE = DATA_DIR / "backfill_progress.json"

# Ziel:
# ca. 520 Kalendertage zurück.
# Das ergibt typischerweise deutlich mehr als 350 Handelstage.
BACKFILL_CALENDAR_DAYS = 520

# Massive Free: 5 Requests / Minute
REQUEST_SLEEP_SECONDS = 13

# Zur Sicherheit:
# maximal so viele API-Aufrufe pro Workflow-Lauf.
# Dadurch kann der Workflow bei Bedarf mehrfach gestartet werden.
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


def load_history():
    return load_json(
        HISTORY_FILE,
        {
            "meta": {},
            "symbols": {}
        }
    )


def load_progress():
    default_start = (
        datetime.now(timezone.utc).date()
        - timedelta(days=BACKFILL_CALENDAR_DAYS)
    )

    return load_json(
        PROGRESS_FILE,
        {
            "next_date": default_start.isoformat(),
            "completed": False
        }
    )


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

    return payload.get("results", [])


def update_history(history, date_string, rows):
    for row in rows:

        ticker = row.get("T")

        if not ticker:
            continue

        candle = {
            "date": date_string,
            "open": row.get("o"),
            "high": row.get("h"),
            "low": row.get("l"),
            "close": row.get("c"),
            "volume": row.get("v"),
            "vwap": row.get("vw")
        }

        candles = history["symbols"].setdefault(
            ticker,
            []
        )

        # Falls derselbe Tag bereits existiert:
        candles = [
            x
            for x in candles
            if x.get("date") != date_string
        ]

        candles.append(candle)

        candles.sort(
            key=lambda x: x["date"]
        )

        history["symbols"][ticker] = candles


def main():

    history = load_history()
    progress = load_progress()

    if progress.get("completed"):
        print("Backfill bereits abgeschlossen.")
        return

    current_date = datetime.fromisoformat(
        progress["next_date"]
    ).date()

    today = datetime.now(timezone.utc).date()

    request_count = 0
    trading_days_found = 0

    while current_date <= today:

        if request_count >= MAX_REQUESTS_PER_RUN:
            print(
                "Maximale Requests für diesen Lauf erreicht."
            )
            break

        date_string = current_date.isoformat()

        print(
            f"Lade {date_string}..."
        )

        try:

            rows = get_market_day(
                date_string
            )

            request_count += 1

        except Exception as exc:

            print(
                f"Fehler bei {date_string}: {exc}"
            )

            # Fortschritt speichern,
            # aber denselben Tag beim nächsten Lauf
            # erneut versuchen.
            progress["next_date"] = date_string

            save_json(
                HISTORY_FILE,
                history
            )

            save_json(
                PROGRESS_FILE,
                progress
            )

            raise

        if rows:

            print(
                f"{date_string}: "
                f"{len(rows)} Wertpapiere"
            )

            update_history(
                history,
                date_string,
                rows
            )

            trading_days_found += 1

        else:

            print(
                f"{date_string}: "
                f"kein Handel / keine Daten"
            )

        current_date += timedelta(days=1)

        progress["next_date"] = (
            current_date.isoformat()
        )

        # Nach JEDEM Tag speichern.
        # Dadurch ist ein Abbruch unkritisch.
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

    if current_date > today:

        progress["completed"] = True

        print(
            "Backfill vollständig abgeschlossen."
        )

    history["meta"] = {
        "generated_at":
            datetime.now(timezone.utc).isoformat(),

        "source":
            "Massive",

        "symbol_count":
            len(history["symbols"]),

        "backfill_completed":
            progress.get("completed", False),

        "next_date":
            progress.get("next_date")
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
    print("Backfill-Lauf beendet.")
    print(
        f"Requests: {request_count}"
    )
    print(
        f"Handelstage gefunden: "
        f"{trading_days_found}"
    )
    print(
        f"Symbole insgesamt: "
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


if __name__ == "__main__":
    main()
