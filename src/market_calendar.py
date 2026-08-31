from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


XNYS = xcals.get_calendar("XNYS")
XETR = xcals.get_calendar("XETR")


def last_completed_us_session(now: datetime | None = None) -> date:
    """Return the most recent completed NYSE trading session in New York time.

    On weekends/holidays this returns the previous trading day. During an open
    session it returns the previous completed session. After the regular close
    it returns the current session date.
    """
    now_ny = now.astimezone(ZoneInfo("America/New_York")) if now else datetime.now(ZoneInfo("America/New_York"))
    today = now_ny.date()

    start = today - timedelta(days=10)
    end = today + timedelta(days=1)
    sessions = XNYS.sessions_in_range(start.isoformat(), end.isoformat())

    candidates = []
    for session in sessions:
        session_date = session.date()
        close_ts = XNYS.session_close(session).to_pydatetime().astimezone(ZoneInfo("America/New_York"))
        if close_ts <= now_ny:
            candidates.append(session_date)

    if not candidates:
        raise RuntimeError(f"Could not determine a completed US trading session around {today}")
    return max(candidates)


def last_completed_xetra_session(now: datetime | None = None) -> date:
    """Return the most recent fully completed Xetra trading session."""
    now_berlin = now.astimezone(ZoneInfo("Europe/Berlin")) if now else datetime.now(ZoneInfo("Europe/Berlin"))
    today = now_berlin.date()

    start = today - timedelta(days=10)
    end = today + timedelta(days=1)
    sessions = XETR.sessions_in_range(start.isoformat(), end.isoformat())

    candidates = []
    for session in sessions:
        session_date = session.date()
        close_ts = XETR.session_close(session).to_pydatetime().astimezone(ZoneInfo("Europe/Berlin"))
        if close_ts <= now_berlin:
            candidates.append(session_date)

    if not candidates:
        raise RuntimeError(f"Could not determine a completed Xetra trading session around {today}")
    return max(candidates)


def is_us_trading_session(day: date) -> bool:
    sessions = XNYS.sessions_in_range(day.isoformat(), day.isoformat())
    return len(sessions) == 1
