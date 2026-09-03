import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_market_snapshot_and_strategy_c_result_have_distinct_targets(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    updater = importlib.import_module("scripts.update_market_data")

    market_snapshot = updater.LATEST_FILE.resolve()
    strategy_c_result = (ROOT / "data" / "latest.json").resolve()

    assert market_snapshot == (ROOT / "data" / "market_data_latest.json").resolve()
    assert market_snapshot != strategy_c_result


def test_daily_workflow_keeps_data_latest_as_strategy_c_mirror():
    workflow = (ROOT / ".github" / "workflows" / "daily_scan.yml").read_text(encoding="utf-8")
    assert "cp docs/latest.json data/latest.json" in workflow
    assert "market_data_latest.json" not in workflow
