from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests


class MassiveAPIError(RuntimeError):
    pass


@dataclass
class MassiveClient:
    api_key: str
    calls_per_minute: int = 5
    base_url: str = "https://api.massive.com"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("MASSIVE_API_KEY is missing")
        self._last_call_at = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "strategy-c-hybrid/1.0"})

    @classmethod
    def from_env(cls, calls_per_minute: int = 5) -> "MassiveClient":
        return cls(
            api_key=os.environ.get("MASSIVE_API_KEY", "").strip(),
            calls_per_minute=calls_per_minute,
        )

    def _throttle(self) -> None:
        if self.calls_per_minute <= 0:
            return
        min_interval = 60.0 / float(self.calls_per_minute)
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._throttle()
        params = dict(params or {})
        params["apiKey"] = self.api_key
        url = f"{self.base_url}{path}"
        response = self._session.get(url, params=params, timeout=45)
        self._last_call_at = time.monotonic()

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "15"))
            time.sleep(max(retry_after, 15.0))
            return self._get(path, params={k: v for k, v in params.items() if k != "apiKey"})

        if response.status_code >= 400:
            raise MassiveAPIError(
                f"Massive API {response.status_code} for {path}: {response.text[:500]}"
            )
        payload = response.json()
        if payload.get("status") not in (None, "OK", "DELAYED"):
            raise MassiveAPIError(f"Unexpected Massive status: {payload}")
        return payload

    def grouped_daily(self, trading_date: date | str) -> list[dict[str, Any]]:
        d = trading_date.isoformat() if isinstance(trading_date, date) else str(trading_date)
        payload = self._get(
            f"/v2/aggs/grouped/locale/us/market/stocks/{d}",
            params={"adjusted": "true", "include_otc": "false"},
        )
        return payload.get("results") or []

    def daily_range(self, ticker: str, start: date | str, end: date | str) -> list[dict[str, Any]]:
        s = start.isoformat() if isinstance(start, date) else str(start)
        e = end.isoformat() if isinstance(end, date) else str(end)
        payload = self._get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{s}/{e}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        return payload.get("results") or []
