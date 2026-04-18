# Conditional Transition Operators -- Implementation Checklist

## Context

Extend the FSM engine's conditional routing so transitions can evaluate task results (HTTP response body and status code) to decide the next state. The activity returns all HTTP responses as results (no more raising on non-2xx). Transition conditions handle all routing logic.

## Current State

- `ConditionOperator` enum: `equals`, `not_equals`, `contains`
- `TransitionCondition.evaluate()` checks a single field in the task result body
- `find_auto_transition()` checks `auto_on_success` then `condition.evaluate()`
- `_resolve_target_state()` parses body as JSON, calls `find_auto_transition()`
- Activity raises RuntimeError on all non-2xx (triggers Temporal retry)

---

## Step 1: `models.py` -- Extend operators and evaluation

- [x] Add `EXISTS = "exists"` to `ConditionOperator`
- [x] Add `NOT_EXISTS = "not_exists"` to `ConditionOperator`
- [x] Add `STATUS_CODE_RANGE = "status_code_range"` to `ConditionOperator`
- [x] Change `TransitionCondition.value` from `value: str` to `value: str = ""` (optional for exists/not_exists)
- [x] Update `TransitionCondition.evaluate()`:
  - `exists`: return `task_result_body.get(self.field) is not None`
  - `not_exists`: return `task_result_body.get(self.field) is None`
  - `status_code_range`: parse `self.value` (e.g. `"4xx"`), check `int(actual) // 100 == int(value[0])`

## Step 2: `activities.py` -- Return results for all HTTP responses

- [x] Remove the `if not response.is_success: raise RuntimeError(...)` block
- [x] Return `TaskCallbackResult(success=response.is_success, status_code=response.status_code, body=response.text)` for all HTTP responses
- [x] Keep `httpx.HTTPError` exception handler (network errors still raise for Temporal retry)

## Step 3: `workflows.py` -- Inject status_code, update fallback behavior

- [x] In `_resolve_target_state()`, inject `status_code` into evaluation context:
  ```python
  task_body["status_code"] = task_result.status_code
  ```
- [x] Update fallback logic:
  - If `task_result.success == False` and no condition matches: stay in current state (skip transition), log warning
  - If `task_result.success == True` and no condition matches: proceed to default target (existing behavior)

## Step 4: `api_server.py` -- Validation update

- [x] Add validation check #7: "Condition operators are valid"
  - For each transition with a condition, verify `condition.operator` is a valid `ConditionOperator` value

## Step 5: `test_e2e.py` -- New test cases

- [x] Test `exists` operator: condition matches when field is present in task result
- [x] Test `not_exists` operator: condition matches when field is absent
- [x] Test `status_code_range` operator: condition matches `4xx` range
- [x] Test 4xx response: mock returns 400, condition routes to error state
- [x] Test 5xx response: mock returns 500, condition routes to error state
- [x] Test no-matching-condition on error: mock returns 500, no condition, workflow stays in current state

## Step 6: `ui/src/types/workflow.ts` -- Add condition types

- [x] Add `TransitionCondition` interface: `{ field: string; operator: string; value?: string }`
- [x] Update `TransitionDefinition` to include `auto_on_success?: boolean` and `condition?: TransitionCondition | null`

## Step 7: `ui/src/components/ConfigPanel.tsx` -- Condition editor

- [x] Add "Auto on success" checkbox when edge is selected
- [x] Add collapsible "Condition" section:
  - Field input (text)
  - Operator dropdown (equals, not_equals, contains, exists, not_exists, status_code_range)
  - Value input (hidden for exists/not_exists)
  - Remove condition button
- [x] Wire `onUpdateEdge` to include `auto_on_success` and `condition`

## Step 8: `ui/src/pages/WorkflowBuilderPage.tsx` -- Persist conditions

- [x] Update `buildImportJson()`: include `auto_on_success` and `condition` from edge data
- [x] Update `onConnect()`: initialize edges with `auto_on_success: false, condition: null`

---

## Verification

- [x] `pytest test_e2e.py` -- all 9 tests pass (exists, not_exists, status_code_range, 4xx routing, 5xx routing, no-match stays, equals, auto_on_success, no-task)
- [ ] Manual: workflow with condition `field=status, operator=equals, value=rejected` routes correctly
- [ ] Manual: 4xx response with `status_code_range` condition routes to error state
- [ ] Manual: 5xx with no matching condition keeps workflow in current state
- [ ] UI: edge condition editor appears, saves, persists on reload, exports in JSON
