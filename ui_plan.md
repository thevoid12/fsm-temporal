# UI Integration Plan

## Context

The `ui/` folder has a React + TypeScript + Vite workflow builder and runtime UI. It was built for a different REST API backend (JWT auth, UUIDs, tenants, database). We need to adapt it to work with our Temporal FSM engine where workflow definitions are JSON files on disk and runtime is driven by Temporal signals/queries.

## Architecture

```
Browser (port 3000)
   |
   | vite proxy /api -> localhost:8000
   v
api_server.py (FastAPI, port 8000)
   |
   |-- Template CRUD --> workflow_definitions/*.json (filesystem)
   |-- Runtime ops   --> Temporal server (signals, queries)
   v
worker.py + workflows.py + activities.py (Temporal, port 7233)
```

## Implementation Steps

### Step 1: Add new Pydantic models to `models.py`

Add these models for the API server to use:

```python
class TemplateSummary(BaseModel):
    """Summary of a workflow template for listing."""
    id: str
    name: str
    description: str | None = None

class ValidationCheck(BaseModel):
    """Single validation check result."""
    check: str
    passed: bool
    details: str | None = None

class ValidationResult(BaseModel):
    """Overall validation result with individual checks."""
    valid: bool
    checks: list[ValidationCheck]

class StartWorkflowRequest(BaseModel):
    """Request body to start a new workflow from a template."""
    template_id: str

class TransitionRequest(BaseModel):
    """Request body to trigger a transition on a running workflow."""
    transition_id: str
```

Also add `metadata: dict | None = None` to `StateDefinition` so the visual builder can store node positions (x, y) inside the workflow JSON files.

### Step 2: Add API server config to `config.py` and `config.json`

In `config.py`, add:
```python
class ApiServerConfig(BaseModel):
    """API server settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    workflow_definitions_dir: str = "workflow_definitions"
```

Add `api_server: ApiServerConfig = ApiServerConfig()` to `AppConfig`.

In `config.json`, add:
```json
"api_server": {
    "host": "0.0.0.0",
    "port": 8000,
    "workflow_definitions_dir": "workflow_definitions"
}
```

### Step 3: Create `api_server.py` (new file)

This is the bridge between the UI and Temporal + filesystem. FastAPI app with two sets of endpoints.

**Template endpoints** (read/write JSON files in `workflow_definitions/`):

- `GET /api/v1/templates` -- List all `.json` files in the directory. For each file, parse the JSON and return `{id: filename_without_ext, name, description}`.

- `POST /api/v1/templates` -- Accept a body with at minimum `{name: str}`. Slugify the name to create a filename (lowercase, spaces to hyphens). If the body has `states` and `transitions`, save the full definition. Otherwise create a minimal empty template. Write to `workflow_definitions/{slug}.json`. Return `{id: slug, name, description}`.

- `GET /api/v1/templates/{template_id}` -- Read `workflow_definitions/{template_id}.json`, return the parsed JSON with an added `id` field. This serves as both "get detail" and "export".

- `PUT /api/v1/templates/{template_id}` -- Overwrite `workflow_definitions/{template_id}.json` with the request body. Validate it parses as a `WorkflowDefinition`. Return the saved content.

- `DELETE /api/v1/templates/{template_id}` -- Delete the file.

- `POST /api/v1/templates/{template_id}/validate` -- Read the file, run validation checks:
  1. Parses as valid WorkflowDefinition
  2. Exactly one state with `is_start: true`
  3. At least one state with `is_end: true`
  4. All transition `source_state`/`target_state` refs point to existing state identifiers
  5. No duplicate state identifiers
  6. No duplicate transition identifiers
  Return `{valid: bool, checks: [{check, passed, details}]}`.

**Runtime endpoints** (talk to Temporal):

- `POST /api/v1/workflows` -- Body: `{template_id: str}`. Read the template JSON from disk. Generate workflow ID: `fsm-{slugified_name}-{uuid_hex[:8]}`. Start a Temporal workflow with `client.start_workflow(WORKFLOW_NAME, workflow_def_dict, id=workflow_id, task_queue=...)`. Query current state and available transitions. Return `{workflow_id, current_state: {state_id, display_label}, available_transitions: [...]}`.

- `GET /api/v1/workflows/{workflow_id}/state` -- Query Temporal: `handle.query(QUERY_CURRENT_STATE)`. Return the dict directly.

- `GET /api/v1/workflows/{workflow_id}/transitions` -- Query Temporal: `handle.query(QUERY_AVAILABLE_TRANSITIONS)`. Return the list directly.

- `POST /api/v1/workflows/{workflow_id}/transition` -- Body: `{transition_id: str}`. Send signal: `handle.signal(SIGNAL_NAME, transition_id)`. Wait 1 second for Temporal to process. Then query current state and transitions. Return `{current_state: {...}, available_transitions: [...]}`.

- `GET /api/v1/workflows/{workflow_id}/audit` -- Query Temporal: `handle.query(QUERY_AUDIT_TRAIL)`. Return the list directly.

**Temporal client**: Create once on FastAPI startup (lifespan), store in `app.state`. Use `pydantic_data_converter`.

### Step 4: Simplify `ui/src/api/client.ts`

Remove all auth logic. The new file should be:

```typescript
const API_BASE = "/api/v1";

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail)
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}
```

Remove: `TENANT_ID`, `TOKEN`, `cachedToken`, `getToken`, `setToken`, `callbackApi`.

### Step 5: Simplify `ui/src/types/workflow.ts`

Replace with types matching our Pydantic models:

```typescript
export interface TemplateSummary {
  id: string;
  name: string;
  description: string | null;
}

export interface StateResponse {
  unique_identifier: string;
  display_label: string;
  description?: string | null;
  is_start: boolean;
  is_end: boolean;
  metadata?: Record<string, unknown> | null;
  task_callback_url?: string | null;
  task_http_method?: string;
  task_timeout_minutes: number;
  max_retries: number;
  retry_interval_seconds: number;
}

export interface TransitionResponse {
  unique_identifier: string;
  display_label?: string | null;
  source_state: string;
  target_state: string;
  auto_on_success?: boolean;
  condition?: Record<string, unknown> | null;
}

export interface TemplateDetail {
  id: string;
  name: string;
  description: string | null;
  states: StateResponse[];
  transitions: TransitionResponse[];
}

export interface WorkflowImport {
  name: string;
  description?: string | null;
  states: StateResponse[];
  transitions: TransitionResponse[];
}

export interface ValidationCheck {
  check: string;
  passed: boolean;
  details: string | null;
}

export interface ValidationResult {
  valid: boolean;
  checks: ValidationCheck[];
}
```

Remove: `WorkflowResponse`, `WorkflowDetailResponse`, `StateImport`, `TransitionImport`, `VersionResponse`.

### Step 6: Replace `ui/src/types/entity.ts`

Replace with Temporal runtime types:

```typescript
export interface CurrentStateResponse {
  state_id: string | null;
  display_label: string | null;
}

export interface AvailableTransition {
  transition_id: string;
  display_label: string;
  target_state: string;
}

export interface AuditEntry {
  timestamp: string;
  from_state: string | null;
  to_state: string;
  transition_id: string | null;
  task_result: string | null;
}

export interface StartWorkflowResponse {
  workflow_id: string;
  current_state: CurrentStateResponse;
  available_transitions: AvailableTransition[];
}

export interface TransitionResponse {
  current_state: CurrentStateResponse;
  available_transitions: AvailableTransition[];
}
```

Remove: `EntityResponse`, `EventResponse`.

### Step 7: Update `ui/src/pages/WorkflowListPage.tsx`

Changes:
- Import `TemplateSummary` instead of `WorkflowResponse`
- `GET /definitions/workflows?page=1&size=50` -> `GET /templates`
- `POST /definitions/workflows` -> `POST /templates` with `{name: newName.trim()}`
- `POST /definitions/workflows/import` -> `POST /templates` with full JSON body
- Remove "Published" badge (`wf.current_version_id` no longer exists)
- Remove `wf.created_at` from display (just show description)
- `wf.id` is now a filename string (e.g., `e2e-test`) not a UUID

### Step 8: Update `ui/src/pages/WorkflowBuilderPage.tsx`

Changes:
- Import `TemplateDetail` instead of `WorkflowDetailResponse`
- `GET /definitions/workflows/${id}` -> `GET /templates/${id}`
- `PUT /definitions/workflows/${id}/import` -> `PUT /templates/${id}`
- `POST /definitions/workflows/${id}/validate` -> `POST /templates/${id}/validate`
- In `buildCanvasFromWorkflow`: remove `stateIdMap` UUID-to-identifier mapping. States now use `unique_identifier` directly as their node ID. Transitions use `source_state`/`target_state` (not `source_state_id`/`target_state_id`).
- Remove `publish` function and Publish button entirely (no versioning)
- Keep: Save, Validate, Export, JSON editor, Run buttons

### Step 9: Update `ui/src/pages/JsonEditorPage.tsx`

Changes:
- `GET /definitions/workflows/${id}/export` -> `GET /templates/${id}`
- `GET /definitions/workflows/${id}` -> `GET /templates/${id}`
- `PUT /definitions/workflows/${id}/import` -> `PUT /templates/${id}`
- `POST /definitions/workflows/${id}/validate` -> `POST /templates/${id}/validate`
- `POST /definitions/workflows/import` -> `POST /templates` (import as new)
- Remove the fallback logic that builds JSON from WorkflowDetailResponse (the template endpoint returns raw JSON directly)

### Step 10: Rework `ui/src/pages/EntityRuntimePage.tsx`

This is the biggest change. Replace the entity/polling/callback model with Temporal signal/query model.

**State changes:**
- Remove: `entity`, `polling`, `intervalRef`, `lastStatusRef`, `lastRetryRef`
- Add: `workflowId: string | null`, `currentState: CurrentStateResponse | null`, `auditTrail: AuditEntry[]`
- Keep: `workflow` (template definition for canvas), `available`, `logs`, `nodes`, `edges`, `status`

**loadWorkflow:**
- `GET /definitions/workflows/${id}` -> `GET /templates/${id}`

**buildCanvas:**
- Remove `stateIdMap` UUID mapping
- Compare `s.unique_identifier === currentStateId` for active state highlighting

**startWorkflow:**
- `POST /runtime/entities` -> `POST /workflows` with `{template_id: id}`
- Response gives `{workflow_id, current_state, available_transitions}`
- Store `workflowId`, `currentState`, `available`
- No polling needed at start (workflow enters start state and waits)

**triggerTransition:**
- `POST /runtime/entities/${entity.id}/transition` -> `POST /workflows/${workflowId}/transition` with `{transition_id}`
- Response gives `{current_state, available_transitions}`
- If the old state had a `task_callback_url` (exit task), the Temporal workflow executes it before moving. This takes time. The API server waits 1s then queries. If the state hasn't changed yet, the UI should poll:
  - Start polling `GET /workflows/${workflowId}/state` every 2 seconds
  - When `state_id` changes from the pre-transition state, stop polling and fetch transitions
  - Show "Processing task..." in the log while polling

**Remove entirely:**
- `simulateCallback` function (no manual callbacks)
- `callbackApi` import
- Task status badges (pending, dispatched, completed, failed)
- `taskBadge`, `maxRetries`, `currentMaxRetries` functions
- Manual override buttons (Success/Fail)

**Add audit trail display:**
- After workflow completes (end state reached), fetch `GET /workflows/${workflowId}/audit`
- Display in the activity log section

**End state detection:**
- Check if `available_transitions` is empty AND the current state is an end state (check `workflow.states` for `is_end`)

### Step 11: Update `makefile`

Add:
```makefile
api:
	$(PYTHON) -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Update `dev` target to start mock + worker + api server:
```makefile
dev:
	@echo "Starting mock server, API server, and worker..."
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999 & \
	$(PYTHON) -m uvicorn api_server:app --host 0.0.0.0 --port 8000 & \
	$(PYTHON) worker.py & \
	wait
```

### Step 12: Update `plan.md`

Add step 8 for UI integration and mark it as the current work.

## Verification

1. Run `make dev-setup` (Terminal 1) -- starts Temporal server
2. Run `make dev` (Terminal 2) -- starts mock server + API server + worker
3. Run `cd ui && bun dev` (Terminal 3) -- starts UI on port 3000
4. Open http://localhost:3000
5. Should see `e2e-test` template listed
6. Click it -> builder loads with states and transitions
7. Add a state, connect it, save -> verify `workflow_definitions/e2e-test.json` updated on disk
8. Click Validate -> should show all checks passing
9. Click Run -> click "Start Workflow" -> should see current state (Draft) highlighted
10. Click "Submit for Review" transition -> should show processing, then move to In Review
11. Continue through all transitions to Closed -> should show "Completed"
12. Check audit trail shows full history
