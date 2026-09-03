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
LATEST_FILE = DATA_DIR / "market_data_latest.json"

# Wir behalten rund 450 Kalendertage.
# Das ergibt deutlich mehr als die benötigten 200 Handelstage.
KEEP_DAYS = 450


def load_history():
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "meta": {},
        "symbols": {}
    }


def get_market_day(date_string):
    url = (
        f"{BASE_URL}/v2/aggs/grouped/locale/us/market/stocks/"
        f"{date_string}"
    )

    params = {
        "adjusted": "true",
        "include_otc": "false",
        "apiKey": API_KEY
    }

    response = requests.get(url, params=params, timeout=60)

    if response.status_code == 429:
        raise RuntimeError("Massive Rate Limit erreicht.")

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

        candles = history["symbols"].setdefault(ticker, [])

        # Vorhandenen Tag ersetzen, falls Workflow erneut läuft
        candles = [
            x for x in candles
            if x.get("date") != date_string
        ]

        candles.append(candle)
        candles.sort(key=lambda x: x["date"])

        history["symbols"][ticker] = candles


def trim_history(history):
    cutoff = (
        datetime.now(timezone.utc).date()
        - timedelta(days=KEEP_DAYS)
    ).isoformat()

    for ticker in list(history["symbols"].keys()):
        candles = history["symbols"][ticker]

        candles = [
            x for x in candles
            if x["date"] >= cutoff
        ]

        if candles:
            history["symbols"][ticker] = candles
        else:
            del history["symbols"][ticker]


def create_latest(history):
    latest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Massive",
        "adjusted": True,
        "symbols": {}
    }

    for ticker, candles in history["symbols"].items():
        if candles:
            latest["symbols"][ticker] = candles[-1]

    return latest


def save_json(path, payload):
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )


def main():
    history = load_history()

    # Gestern + heute testen.
    # Dadurch funktioniert der Workflow auch an Wochenenden,
    # Feiertagen oder falls Massive den letzten Handelstag
    # zeitverzögert bereitstellt.
    today = datetime.now(timezone.utc).date()

    candidate_dates = [
        today,
        today - timedelta(days=1),
        today - timedelta(days=2),
        today - timedelta(days=3)
    ]

    updated_dates = []

    for date_value in candidate_dates:
        date_string = date_value.isoformat()

        try:
            rows = get_market_day(date_string)
        except Exception as exc:
            print(f"{date_string}: Fehler: {exc}")
            continue

        if not rows:
            print(f"{date_string}: keine Marktdaten")
            continue

        print(
            f"{date_string}: "
            f"{len(rows)} US-Wertpapiere erhalten"
        )

        update_history(
            history,
            date_string,
            rows
        )

        updated_dates.append(date_string)

        time.sleep(1)

    trim_history(history)

    history["meta"] = {
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "source": "Massive",
        "updated_dates": updated_dates,
        "symbol_count":
            len(history["symbols"])
    }

    latest = create_latest(history)

    save_json(HISTORY_FILE, history)
    save_json(LATEST_FILE, latest)

    print(
        f"Fertig. "
        f"{len(history['symbols'])} Symbole gespeichert."
    )


if __name__ == "__main__":
    main()
