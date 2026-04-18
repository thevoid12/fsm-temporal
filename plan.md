# Temporal FSM Engine - Implementation Plan

## Context

 We need to transform it into a **JSON-driven Finite State Machine engine** that reads a workflow definition (like `workflow.json`) and executes it using Temporal workflows, signals, and activities. States can optionally trigger HTTP callbacks (with retries/timeouts), and transitions are triggered via Temporal signals. A v1 UI will be added later.

## Files to Create/Modify

### New Files
1. **`models.py`** - Pydantic models, enums, and constants for the FSM engine
2. **`config.py`** + **`config.json`** - Typed application configuration (Temporal server, mock server settings)
3. **`workflow_definitions/e2e_test.json`** - Workflow JSON definition adapted for this temporal implementation

### Modified Files
4. **`activities.py`** - Replace `greet` with `execute_task_callback` activity (HTTP POST to callback URL, raises on non-2xx for Temporal retry)
5. **`workflows.py`** - Replace `SayHelloWorkflow` with `FSMWorkflow`:
   - purely use most of the inbuilt temporal features
   - Receives workflow definition struct (model) as input, parses into dataclasses. dont use dict
   - Enters start state, executes task callback if defined
   - Main loop: waits for transition signals, validates, enters target state
   - Uses a signal queue (list) to avoid lost signals
   - Queries: `current_state`, `available_transitions`, `audit_trail`
   - Completes when reaching `is_end: true` state
   - Maps `max_retries` / `retry_interval_seconds` to Temporal `RetryPolicy` on activity calls
   - After entering a state and running its task, evaluates conditional transitions: if a transition from the current state has a `condition` matching the task result, auto-transitions without waiting for a signal
6. **`worker.py`** - Register `FSMWorkflow` + `execute_task_callback`, task queue `fsm-task-queue`
7. **`main.py`** - CLI with commands: `start <json>`, `transition <wf_id> <id>`, `state <wf_id>`, `transitions <wf_id>`, `audit <wf_id>`
8. **`mock_environment/main.py`** - Updated `TaskPayload` to match `TaskCallbackRequestBody`
9. **`makefile`** - Add targets for workflow commands


## Conditional Transitions

Transitions can optionally have `auto_on_success` or a `condition` to enable automatic transitions after a task completes:

1. **`auto_on_success: true`** - auto-transitions if the task callback returns success (no condition needed)
2. **`condition`** - evaluates a specific field in the task result body for finer control

```json
{"unique_identifier": "submit", "source_state": "state-1", "target_state": "state-2", "auto_on_success": true}

{"unique_identifier": "auto_reject", "source_state": "state-2", "target_state": "state-1",
 "condition": {"field": "status", "operator": "equals", "value": "rejected"}}
```

Supported operators: `equals`, `not_equals`, `contains`

Task callbacks run **on exit** from a state (not on entry). Flow when a transition signal is received:
1. Run current state's task callback (if defined)
2. Check `auto_on_success` / `condition` transitions against task result -- if matched, override the signal's target state
3. Enter the resolved target state (audit entry records the task result)
4. If no task on the state -> transition directly to the target

## Key Design Decisions

- **Workflow def passed as dict input** (not loaded from file inside workflow) to maintain Temporal determinism
- **Temporal RetryPolicy** used for callback retries (`max_retries+1` = `maximum_attempts`, `backoff_coefficient=1.0` for flat intervals)
- **`httpx`** for async HTTP in the activity; existing **`mock_environment/`** (FastAPI) for mock server
- **Transition queue** (list) instead of single pending variable to handle rapid signals
- **Activity failure propagates** to workflow failure for now (can add error handling later)

## Implementation Order

1. `models.py` - data foundation
2. `activities.py` - HTTP callback activity
3. `workflows.py` - FSM workflow
4. `worker.py` - wire up
5. `main.py` - CLI
6. `mock_environment/main.py` - update payload model
7. `workflow_definitions/e2e_test.json` + `makefile` make dev to run the mock and run the code write run.md what all need to be observed and how [DONE]

## UI Integration

### Architecture
```
UI (React, port 3000) --vite proxy--> API Server (FastAPI, port 8000) --> Temporal + workflow_definitions/*.json
```

### New Files
- **`api_server.py`** - FastAPI server bridging UI to Temporal and filesystem templates

### API Endpoints

**Template CRUD** (filesystem on `workflow_definitions/`):
- `GET /api/v1/templates` - List templates
- `POST /api/v1/templates` - Create template (name or full JSON import)
- `GET /api/v1/templates/{id}` - Read template
- `PUT /api/v1/templates/{id}` - Update template
- `DELETE /api/v1/templates/{id}` - Delete template
- `POST /api/v1/templates/{id}/validate` - Validate template structure

**Runtime** (Temporal operations):
- `POST /api/v1/workflows` - Start workflow from template
- `GET /api/v1/workflows/{wf_id}/state` - Query current state
- `GET /api/v1/workflows/{wf_id}/transitions` - Query available transitions
- `POST /api/v1/workflows/{wf_id}/transition` - Trigger transition
- `GET /api/v1/workflows/{wf_id}/audit` - Query audit trail

### Model Additions
- `metadata: dict | None` on `StateDefinition` for node position data
- `TemplateSummary`, `ValidationCheck`, `ValidationResult` for API responses
- `StartWorkflowRequest`, `TransitionRequest` for API requests
- `ApiServerConfig` in config for host/port/definitions_dir

### UI Adaptations
- Removed JWT auth, tenant IDs, UUID mappings from API client
- Simplified types to match backend models directly (no DB-backed UUIDs)
- Removed Publish button (no versioning)
- Runtime page uses Temporal signal/query model instead of entity/callback model
- Audit trail from Temporal queries instead of client-side logs

### Running
1. `make dev` - starts mock server, worker, and API server
2. `cd ui && bun dev` - starts UI on port 3000
3. Vite proxies `/api` to API server on port 8000

## Verification

### CLI Verification
1. `temporal server start-dev --ui-port 8080`
2. `make mock` (port 9999)
3. `python3 worker.py`
4. `python3 main.py start workflow_definitions/e2e_test.json` - should enter Draft, call instant-success
5. `python3 main.py state <wf_id>` - should show Draft
6. `python3 main.py transition <wf_id> submit` - enters In Review, calls slow-success (~3s)
7. `python3 main.py transition <wf_id> pass_review` - enters Retry Check, first callback fails, retries after 5s, succeeds
8. `python3 main.py transition <wf_id> approve` - enters Approved (no task, waits)
9. `python3 main.py transition <wf_id> close` - enters Closed, workflow completes
10. `python3 main.py audit <wf_id>` - shows full transition history

### UI Verification
1. `make dev` starts Temporal worker, mock server, and API server
2. `cd ui && bun dev` starts the UI on port 3000
3. Open http://localhost:3000 -- should see existing `e2e_test` template listed
4. Click it -> builder loads with states and transitions on canvas
5. Edit and Save -> JSON file updated on disk
6. Click Run -> start workflow -> see current state highlighted
7. Click transitions -> workflow progresses through states
8. Audit trail shows full history
