from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_calendar import last_completed_xetra_session
from src.strategy_b import compute_strategy_b_metrics, evaluate_strategy_b
from src.strategy_b_data import StrategyBDataError, fetch_yahoo_daily, keep_completed_sessions

DOCS_OUTPUT = ROOT / "docs" / "strategy_b_latest.json"
DATA_OUTPUT = ROOT / "data" / "strategy_b_latest.json"
MIN_HISTORY_BARS = 253

ETF = {
    "name": "iShares Edge MSCI World Momentum Factor UCITS ETF",
    "isin": "IE00BP3QZ825",
    "wkn": "A12ATF",
    "xetra_ticker": "IS3R",
    "data_symbol": "IS3R.DE",
}


def coverage_payload(has_required_history: bool) -> dict:
    return {
        "instruments_total": 1,
        "instruments_with_required_history": int(has_required_history),
        "ratio": 1.0 if has_required_history else 0.0,
        "minimum_bars_required": MIN_HISTORY_BARS,
        "missing_or_short": [] if has_required_history else [ETF["xetra_ticker"]],
    }


def write_payload(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    DOCS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DOCS_OUTPUT.write_text(text, encoding="utf-8")
    DATA_OUTPUT.write_text(text, encoding="utf-8")


def main() -> None:
    generated_at = datetime.now(ZoneInfo("UTC")).isoformat()
    expected_date = last_completed_xetra_session().isoformat()

    try:
        raw_df = fetch_yahoo_daily(ETF["data_symbol"], "3y")
        df = keep_completed_sessions(raw_df, expected_date)
        if df.empty:
            raise StrategyBDataError(f"No completed Xetra daily bars available through {expected_date}")
        metrics = compute_strategy_b_metrics(df)
    except (StrategyBDataError, ValueError, RuntimeError) as exc:
        payload = {
            "generated_at_utc": generated_at,
            "strategy": "Strategy B - MSCI World Momentum",
            "status": "data_unavailable",
            "instrument": ETF,
            "data_source": "Yahoo Finance chart API (Xetra symbol IS3R.DE)",
            "freshness": {"expected_data_date": expected_date, "latest_data_date": None, "pass": False},
            "coverage": coverage_payload(False),
            "signal": {"buy_signal": False, "exit_signal": False, "exit_reasons": []},
            "stale_cached_candidate_count": 0,
            "error": str(exc),
            "important": "No Strategy B signal is published when the data feed is unavailable or invalid.",
        }
        write_payload(payload)
        print(f"Strategy B data unavailable: {exc}")
        return

    latest_date = metrics["date"]
    freshness_pass = latest_date == expected_date
    decision = evaluate_strategy_b(metrics)
    stale_cached_candidate_count = int(decision["buy_signal"] or decision["exit_signal"])
    if not freshness_pass:
        decision = {
            **decision,
            "buy_signal": False,
            "exit_signal": False,
            "exit_reasons": [],
        }

    initial_stop_reference = metrics["close"] - 2.5 * metrics["atr20"]
    payload = {
        "generated_at_utc": generated_at,
        "strategy": "Strategy B - MSCI World Momentum",
        "status": "ok" if freshness_pass else "stale_data",
        "instrument": ETF,
        "data_source": "Yahoo Finance chart API (Xetra symbol IS3R.DE)",
        "latest_data_date": latest_date,
        "freshness": {
            "expected_data_date": expected_date,
            "expected_session_rule": "Most recent fully completed Xetra session; an intraday Yahoo daily bar for the current session is ignored until Xetra has closed.",
            "latest_data_date": latest_date,
            "pass": freshness_pass,
            "reason": None if freshness_pass else f"Expected completed Xetra session {expected_date}, but latest completed Strategy B data is {latest_date}. Signals suppressed.",
        },
        "coverage": coverage_payload(True),
        "metrics": metrics,
        "signal": decision,
        "stale_cached_candidate_count": 0 if freshness_pass else stale_cached_candidate_count,
        "risk_reference": {
            "risk_per_trade_pct_of_ab_capital": 0.5,
            "initial_stop_formula": "entry - 2.5 * ATR20",
            "initial_stop_reference_from_latest_close": initial_stop_reference,
        },
        "rules": {
            "entry": ["close > SMA200", "SMA200 today > SMA200 20 trading days ago", "ADX14 > 30"],
            "exit": ["10 consecutive closes below SMA200", "SMA200 today < SMA200 20 trading days ago"],
        },
        "important": "Research output only. A buy is only actionable when no Strategy B position exists and broker price/capital checks are passed. Only fully completed Xetra daily bars may create signals; stale data never creates a signal.",
    }
    write_payload(payload)
    print(f"Strategy B freshness: {freshness_pass} expected_xetra={expected_date} latest={latest_date}")
    print(f"Strategy B buy={decision['buy_signal']} exit={decision['exit_signal']}")


if __name__ == "__main__":
    main()
