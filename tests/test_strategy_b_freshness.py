from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.market_calendar import last_completed_xetra_session
from src.strategy_b_data import keep_completed_sessions


def test_xetra_session_before_close_uses_previous_session():
    now = datetime(2026, 8, 31, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert last_completed_xetra_session(now).isoformat() == "2026-08-28"


def test_xetra_session_after_close_uses_current_session():
    now = datetime(2026, 8, 31, 18, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert last_completed_xetra_session(now).isoformat() == "2026-08-31"


def test_incomplete_current_day_row_is_removed():
    df = pd.DataFrame({
        "date": ["2026-08-28", "2026-08-31"],
        "close": [98.0, 99.0],
    })
    out = keep_completed_sessions(df, "2026-08-28")
    assert out["date"].tolist() == ["2026-08-28"]
