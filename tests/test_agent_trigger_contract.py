import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / ".automation" / "run-request.json"
STATE_PATH = ROOT / ".automation" / "signal-state.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "daily_scan.yml"


def test_run_request_is_non_sensitive_and_has_stable_schema():
    payload = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    assert set(payload) == {
        "request_id",
        "requested_at_utc",
        "scheduled_slot_local",
        "source",
    }
    forbidden = {
        "portfolio_id",
        "budget",
        "holdings",
        "quantity",
        "order_id",
        "stop_price",
        "entry_price",
    }
    assert forbidden.isdisjoint(payload)


def test_signal_state_contains_only_public_signal_keys():
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert isinstance(payload["evaluated_signals"], list)
    for item in payload["evaluated_signals"]:
        assert set(item) == {"strategy", "ticker", "signal_type", "signal_date"}


def test_workflow_contract_has_agent_push_trigger_without_cron():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "paths:" in workflow
    assert "- '.automation/run-request.json'" in workflow
    assert "schedule:" not in workflow
    assert "cron:" not in workflow
