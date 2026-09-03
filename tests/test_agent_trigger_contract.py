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


def test_workflow_scans_and_stamps_the_exact_request_commit():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "ref: ${{ github.sha }}" in workflow
    assert "git reset --hard origin/main" not in workflow
    assert "python scripts/stamp_scan_outputs.py ${{ github.sha }}" in workflow
    assert workflow.index("Sync scan outputs to data") < workflow.index("Stamp scan outputs")
    assert workflow.index("Stamp scan outputs") < workflow.index("Commit cache and A/B/C results")


def test_manual_dispatch_is_fail_closed_to_main():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    guard = (
        "if: github.event_name == 'push' || "
        "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')"
    )
    assert guard in workflow
    assert workflow.index("scan:") < workflow.index(guard) < workflow.index("runs-on:")
