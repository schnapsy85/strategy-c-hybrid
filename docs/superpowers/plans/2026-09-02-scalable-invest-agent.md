# Automated Scalable Invest Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekday agent that triggers, monitors, validates, and reports every Strategy A/B/C GitHub scan and prepares confirmation-gated Scalable orders when action is required.

**Architecture:** A scheduled ChatGPT automation writes a unique, non-sensitive request marker to GitHub. A path-filtered push trigger starts `daily_scan.yml`; the same agent correlates the resulting workflow run by commit SHA, monitors it to completion, validates all three result files, and filters Scalable state through a private allowlist backed by exact broker provenance. No broker data is persisted in the public repository.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, JSON control files, GitHub connector, Scalable connector, ChatGPT Automations with iCalendar scheduling.

**Spec:** `docs/superpowers/specs/2026-09-02-scalable-invest-agent-design.md`

## Global Constraints

- Schedule exactly Monday through Friday at 08:30, 12:30, 15:30, 18:30, and 22:30 in `Europe/Berlin`.
- The agent must initiate every scheduled run; remove the existing GitHub cron schedule and retain manual `workflow_dispatch`.
- Never write portfolio IDs, holdings, quantities, broker prices, order IDs, transaction details, budgets, or private performance data to the public repository.
- Preserve all existing Strategy A, B, and C trading rules.
- Suppress signals from stale, partial, or otherwise invalid data.
- Never touch a holding unless a private allowlist entry and its Scalable order/transaction provenance identify it unambiguously as a strategy position.
- Never submit a trade without a current complete preview and a separate explicit confirmation for that individual preview.
- Never retry an order blindly after a timeout or unknown outcome.
- Provide a complete report after every scheduled run, including no-signal and error outcomes.
- Run repository tests before treating any GitHub result as valid.
- Treat a result file as usable only when its top-level `request_commit_sha` equals the monitored request commit.

---

### Task 1: Add the non-sensitive trigger and deduplication contract

**Files:**
- Create: `.automation/run-request.json`
- Create: `.automation/signal-state.json`
- Create: `tests/test_agent_trigger_contract.py`

**Interfaces:**
- Consumes: repository root and `.github/workflows/daily_scan.yml`.
- Produces: a stable request-marker schema and a public signal-key ledger containing no broker data.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_agent_trigger_contract.py` with:

```python
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
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
PYTHONPATH=. pytest tests/test_agent_trigger_contract.py -q
```

Expected: FAIL because the two `.automation` JSON files do not exist and `daily_scan.yml` still contains a schedule instead of the required push contract.

- [ ] **Step 3: Create the initial request marker**

Create `.automation/run-request.json` with exactly:

```json
{
  "request_id": "bootstrap",
  "requested_at_utc": null,
  "scheduled_slot_local": null,
  "source": "initial_setup"
}
```

- [ ] **Step 4: Create the initial public signal-key ledger**

Create `.automation/signal-state.json` with exactly:

```json
{
  "version": 1,
  "evaluated_signals": []
}
```

- [ ] **Step 5: Verify privacy and JSON validity**

Run:

```bash
python -m json.tool .automation/run-request.json
python -m json.tool .automation/signal-state.json
```

Expected: both commands exit successfully and neither file contains broker or portfolio fields.

- [ ] **Step 6: Commit the control contract on the implementation branch**

```bash
git add .automation/run-request.json .automation/signal-state.json tests/test_agent_trigger_contract.py
git commit -m "test: define agent trigger contract"
```

Expected: one commit containing only the two non-sensitive control files and their contract test.

---

### Task 2: Make the daily scanner agent-triggered

**Files:**
- Modify: `.github/workflows/daily_scan.yml`
- Modify: `README.md`
- Test: `tests/test_agent_trigger_contract.py`

**Interfaces:**
- Consumes: changes to `.automation/run-request.json` on `main`.
- Produces: exactly one `Daily Strategy A/B/C Scan` workflow run whose `head_sha` equals the request commit SHA.

- [ ] **Step 1: Replace the workflow event block**

Replace the current `on` block in `.github/workflows/daily_scan.yml` with exactly:

```yaml
on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - '.automation/run-request.json'
```

Keep the existing workflow name, permissions, concurrency group, job, timeout, tests, A/B/C scan steps, output synchronization, and result commit steps unchanged.

- [ ] **Step 2: Document the new ownership of scheduling**

In `README.md`, replace the description of the GitHub cron schedule with:

```markdown
## Agent-triggered weekday runs

Scheduled Strategy A/B/C runs are initiated by the private ChatGPT automation.
At each configured weekday slot, the agent updates
`.automation/run-request.json`. The path-filtered push starts
`Daily Strategy A/B/C Scan`.

GitHub no longer owns the recurring clock schedule. Manual
`workflow_dispatch` remains available for diagnostics. Updates to scan output
files and `.automation/signal-state.json` do not trigger another scan.
```

- [ ] **Step 3: Run the focused contract test**

Run:

```bash
PYTHONPATH=. pytest tests/test_agent_trigger_contract.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the complete repository test suite**

Run:

```bash
PYTHONPATH=. pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Review the diff for accidental strategy changes**

Run:

```bash
git diff --check HEAD~1
git diff HEAD~1 -- .github/workflows/daily_scan.yml README.md .automation tests/test_agent_trigger_contract.py
```

Expected: the workflow event block, documentation, control files, and contract test are the only behavior changes; scanner scripts and strategy configuration are unchanged.

- [ ] **Step 6: Commit the workflow change**

```bash
git add .github/workflows/daily_scan.yml README.md
git commit -m "feat: trigger strategy scan from agent requests"
```

Expected: one commit that removes the cron schedule and adds only the path-filtered push trigger.

---

### Task 3: Establish the private allowlist lifecycle

**Files:**
- No repository files.
- Private broker and automation state only.

**Interfaces:**
- Consumes: authenticated Scalable holdings, orders, and transactions plus privately approved provenance records.
- Produces: an initial private allowlist resolved during automation setup. Public files contain no member count, strategy allocation, instrument identity, or current/historical position state.

- [ ] **Step 1: Re-read the accessible portfolio and current broker state**

List accessible portfolios, holdings, transactions, open orders, and portfolio groups. Confirm exactly one authenticated portfolio is selected. Record identifiers only in private working context.

Expected: the connector succeeds and the current state can be reconciled without writing private data to GitHub or the worktree.

- [ ] **Step 2: Resolve approved provenance privately**

Resolve each privately approved entry to its exact Scalable security identifier and matching broker order or transaction provenance. Determine its lifecycle solely from verified broker evidence. Do not infer membership from ticker similarity, security type, or being ungrouped.

Expected: only entries with unambiguous provenance are included in the private resolution.

- [ ] **Step 3: Build the private allowlist payload**

Prepare a private prompt fragment with entries containing the strategy mapping, security identifier, instrument key, lifecycle state, and matching broker order or transaction provenance. Do not persist the fragment, its membership, its allocation, or its resolved state in any public or local repository file.

Expected: the fragment is sufficient to distinguish strategy holdings from any later private purchase of the same ticker.

- [ ] **Step 4: Verify the private lifecycle and isolation**

Re-read holdings, transactions, open orders, and organizational metadata. Confirm that each private allowlist entry still matches its stored provenance and that unrelated broker state remains excluded. Block any ambiguous entry.

Expected: the private resolution is internally consistent and no holding, order, savings plan, group, or cash state changes.

---

### Task 4: Create the scheduled investment agent

**Files:**
- No public repository files.
- One private ChatGPT Automation task.

**Interfaces:**
- Consumes: GitHub repository `schnapsy85/strategy-c-hybrid`, the three scan JSON files, the private allowlist fragment from Task 3, and private capital and provenance baselines.
- Produces: five weekday runs and five complete reports per weekday, with individual confirmation-gated order previews when required.

- [ ] **Step 1: Perform required connector preflight checks**

Immediately before creating the task:

1. read the GitHub repository or `.automation/run-request.json`;
2. list accessible Scalable portfolios, holdings, transactions, and open orders.

Expected: both connectors return successfully without a Connect, Reconnect, approval, or authorization error. Stop task creation if either preflight fails.

- [ ] **Step 2: Create one exact-time recurring automation**

Use title:

```text
A/B/C Investment Agent
```

Use timezone:

```text
Europe/Berlin
```

Use exact schedule:

```text
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20260903T083000
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8,12,15,18,22;BYMINUTE=30;BYSECOND=0
END:VEVENT
```

Use `exact_schedule`.

- [ ] **Step 3: Set the complete automation prompt**

The prompt must instruct each run to perform this exact sequence:

1. Run harmless read-only GitHub and Scalable preflight checks.
2. Fetch `.automation/run-request.json` and retain its current blob SHA.
3. Generate a unique request ID and replace the file with `request_id`, current UTC `requested_at_utc`, the current Europe/Berlin slot as `scheduled_slot_local`, and `source: "chatgpt_automation"`.
4. Retry GitHub access or the file update at most twice for transient failures.
5. Capture the request commit SHA.
6. Query GitHub workflow runs filtered to `daily_scan.yml`, `push`, `main`, creation time, and the request commit SHA.
7. Poll no more often than once per minute for at most 45 minutes.
8. On failure, read jobs, steps, and available logs; rerun failed jobs once; monitor the new attempt; report and stop if it fails again.
9. On success, freshly read `data/strategy_a_latest.json`, `data/strategy_b_latest.json`, and `data/latest.json`.
10. Verify every file's top-level `request_commit_sha` equals the monitored request commit, then verify generation time, completed-session freshness, status, universe completeness, coverage, market filter, suppressed signals, signals, watch candidates, and exit conditions for every strategy. A file with a missing or mismatched request commit is unusable.
11. Suppress only the affected strategy when its independent data is stale or partial; suppress all strategies if the shared cache is invalid.
12. Read the private allowlist embedded in this task, then read Scalable holdings, current quotes, relevant transactions, active stops, and strategy-only capital state. Retry read failures at most twice.
13. Include a position only when its private allowlist entry and broker order/transaction provenance match unambiguously. Exclude every other holding, including a same-ticker holding with a different or missing provenance.
14. Reconcile existing strategy holdings with A/B/C exit and stop rules.
15. For new signals, check `.automation/signal-state.json`, existing holdings, open orders, current broker quote, gap filter, tradability, venue, available strategy capital, risk sizing, and initial stop.
16. Update `.automation/signal-state.json` only with public keys `strategy`, `ticker`, `signal_type`, and `signal_date`, and only after a complete broker evaluation. Never place broker data in that file.
17. Produce a complete German report after every run, including run identity and duration, A/B/C status and freshness, coverage, filters, signals, watch and exits, strategy-only positions, current prices, P/L, stops, stop distances, pending strategy orders, free strategy capital, strategy equity, actions, retries, and errors.
18. When an action is valid, create the matching Scalable preview and present the complete human-readable review. Stop and request a separate explicit confirmation for that individual preview.
19. Never submit automatically, reuse confirmation, touch non-strategy holdings, use stale data, duplicate a signal, or blindly retry an order with an unknown outcome.
20. After a separately confirmed submission, add the returned broker reference to this task's private allowlist. Advance its private lifecycle only after a later Scalable read proves the outcome, and retain prior provenance after a fully executed exit so later private buys remain excluded.
21. If allowlist persistence, provenance matching, or mixed private/strategy lots are ambiguous, block every action for that instrument and report the conflict.

The private prompt may contain the approved capital and provenance baselines but must not copy them into GitHub.

- [ ] **Step 4: Verify the created task**

Inspect the returned task record.

Expected:

- task is enabled;
- timezone is `Europe/Berlin`;
- timing mode is exact;
- recurrence is Monday through Friday;
- all five requested times are present;
- prompt names both required connectors, the exact repository, and the private allowlist/provenance rule;
- no automatic order submission is authorized.

---

### Task 5: Run an end-to-end verification without trading

**Files:**
- Modify: `.automation/run-request.json`
- Read: `.automation/signal-state.json`
- Read: `data/strategy_a_latest.json`
- Read: `data/strategy_b_latest.json`
- Read: `data/latest.json`

**Interfaces:**
- Consumes: implemented trigger contract, updated workflow, private allowlist lifecycle, and scheduled agent logic.
- Produces: evidence that one request creates one workflow run and one complete post-run evaluation without submitting an order.

- [ ] **Step 1: Trigger a supervised test request**

Update `.automation/run-request.json` with a unique request ID, current UTC timestamp, `scheduled_slot_local: "supervised_test"`, and `source: "chatgpt_supervised_test"`.

Expected: GitHub returns one new commit SHA.

- [ ] **Step 2: Locate exactly one correlated workflow run**

Query recent workflow runs and select the run whose path is `.github/workflows/daily_scan.yml`, event is `push`, branch is `main`, and `head_sha` equals the request commit SHA.

Expected: exactly one matching run.

- [ ] **Step 3: Monitor completion**

Poll the selected run no more often than once per minute.

Expected: `status: completed` and `conclusion: success`. If it fails, exercise the approved single failed-job rerun and capture diagnostic evidence.

- [ ] **Step 4: Validate the generated outputs**

Freshly read all three result files and verify:

- generation timestamps are after the supervised request;
- each top-level `request_commit_sha` equals the supervised request commit;
- each file reports its explicit status and freshness;
- coverage and suppressed-signal fields are present;
- signals are not silently emitted from stale data.

Expected: all valid strategies are usable; any invalid strategy is visibly suppressed.

- [ ] **Step 5: Verify Scalable isolation and report composition**

Read the private allowlist and Scalable broker state, match provenance, and generate the complete strategy-only report. Confirm unrelated holdings and any unmatched same-ticker lots are absent from every strategy total and action.

Expected: the report contains all required sections and no unrelated position is modified.

- [ ] **Step 6: Verify the order safety boundary**

If the test produces an actionable signal, stop after creating and displaying the complete preview. Do not confirm or submit it during the verification.

Expected: no new buy, sell, stop, cancellation, savings-plan change, or cash movement is submitted by the test.

- [ ] **Step 7: Confirm the next scheduled executions**

Inspect the automation task’s next-run information.

Expected: the next five occurrences follow the approved weekday times in `Europe/Berlin`, with no Saturday or Sunday occurrence.
