# Running the FSM Engine (E2E Test)

## Prerequisites

- Temporal CLI installed (`brew install temporal`)
- Python dependencies installed via `uv`

## Setup (2 terminals)

### Terminal 1 -- Temporal server
```bash
make dev-setup
```
Opens the Temporal UI at http://localhost:8080.

### Terminal 2 -- Mock server + Worker
```bash
make dev
```
Starts the mock server (port 9999) and the FSM worker together. Both processes run in the background of this shell; `Ctrl+C` stops them.

## Running the workflow

All commands below run in a 3rd terminal.

### 1. Start the workflow
```bash
make start
```
Prints a workflow ID like `fsm-E2E Test Workflow-a1b2c3d4`. Copy this ID for subsequent commands.

**What to observe:**
- Worker logs show the workflow entering state `Draft` (state-1).
- The `instant-success` callback fires immediately and returns 200.
- Mock server logs a POST to `/task/instant-success`.

### 2. Query state
```bash
make state WF_ID=<workflow_id>
```
**Expected:** `state_id: state-1`, `display_label: Draft`.

### 3. Submit for review
```bash
make transition WF_ID=<workflow_id> T_ID=submit
```
**What to observe:**
- Worker logs show transition from `Draft` to `In Review` (state-2).
- The `slow-success` callback takes ~15 seconds before returning 200.
- During those 15 seconds, the Temporal UI (http://localhost:8080) shows the activity as running.
- Mock server logs a POST to `/task/slow-success`.

### 4. Pass review
```bash
make transition WF_ID=<workflow_id> T_ID=pass_review
```
**What to observe:**
- Worker logs transition from `In Review` to `Retry Check` (state-3).
- The `fail-then-succeed` callback returns 500 on the first attempt.
- Temporal retries the activity after ~5 seconds (configured `retry_interval_seconds`).
- Second attempt returns 200.
- Mock server logs show two POSTs to `/task/fail-then-succeed`.
- In the Temporal UI, the activity shows 2 attempts.

### 5. Approve
```bash
make transition WF_ID=<workflow_id> T_ID=approve
```
**What to observe:**
- Worker transitions to `Approved` (state-4).
- No task callback fires (state-4 has no `task_callback_url`).
- Workflow stays running, waiting for the next signal.

### 6. Close
```bash
make transition WF_ID=<workflow_id> T_ID=close
```
**What to observe:**
- Worker transitions to `Closed` (state-5, `is_end: true`).
- Workflow completes. The Temporal UI shows the workflow as "Completed".
- Worker logs the final `FSMWorkflowResult` with `final_state: state-5`.

### 7. Audit trail
```bash
make audit WF_ID=<workflow_id>
```
**Expected output:** A list of all state transitions with timestamps, from/to states, transition IDs, and task results. Should contain 6 entries (initial entry + 5 transitions).

## Temporal UI observations

Throughout the run, visit http://localhost:8080 and find the workflow by its ID. Key things to check:

- **Event History:** Every signal, activity start, activity completion, and query is recorded.
- **Pending Activities:** While `slow-success` runs, you will see a pending activity with a countdown.
- **Activity Retries:** On the `fail-then-succeed` state, the activity detail shows attempt count > 1.
- **Workflow Result:** After `close`, the result tab shows the `FSMWorkflowResult` JSON with `final_state` and the full `audit_trail`.

## Query helpers

```bash
make transitions WF_ID=<workflow_id>   # available transitions from current state
make state WF_ID=<workflow_id>         # current state
make audit WF_ID=<workflow_id>         # full audit trail
```
