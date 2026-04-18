"""End-to-end tests for conditional transition operators and activity behavior.
Tests the FSM workflow with various condition operators, HTTP status code routing,
and fallback behavior when no conditions match.
"""

import json

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from models import (
    QUERY_AVAILABLE_TRANSITIONS,
    QUERY_CURRENT_STATE,
    SIGNAL_NAME,
    TaskCallbackInput,
    TaskCallbackResult,
    WorkflowDefinition,
)
from workflows import FSMWorkflow


def _build_workflow_def(
    states: list[dict],
    transitions: list[dict],
    name: str = "test-workflow",
) -> dict:
    """Build a WorkflowDefinition dict from simplified state/transition dicts."""
    wf = WorkflowDefinition(name=name, states=states, transitions=transitions)
    return wf.model_dump()


def _make_mock_activity(status_code: int, body: dict):
    """Create a mock task callback activity returning the given status code and body."""
    @activity.defn(name="execute_task_callback")
    async def mock_callback(_input: TaskCallbackInput) -> TaskCallbackResult:
        return TaskCallbackResult(
            success=200 <= status_code < 300,
            status_code=status_code,
            body=json.dumps(body),
        )
    return mock_callback


STATES_WITH_TASK = [
    {"unique_identifier": "start", "display_label": "Start", "is_start": True,
     "task_callback_url": "http://mock/task"},
    {"unique_identifier": "approved", "display_label": "Approved", "is_end": True},
    {"unique_identifier": "rejected", "display_label": "Rejected", "is_end": True},
    {"unique_identifier": "error", "display_label": "Error", "is_end": True},
]

STATES_NO_TASK = [
    {"unique_identifier": "start", "display_label": "Start", "is_start": True},
    {"unique_identifier": "end", "display_label": "End", "is_end": True},
]


@pytest.mark.asyncio
async def test_exists_operator():
    """Condition with 'exists' matches when the field is present in task result."""
    transitions = [
        {"unique_identifier": "t1", "source_state": "start", "target_state": "approved",
         "condition": {"field": "approval", "operator": "exists"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "rejected"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(200, {"approval": "yes"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-exists", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "approved"


@pytest.mark.asyncio
async def test_not_exists_operator():
    """Condition with 'not_exists' matches when the field is absent from task result."""
    transitions = [
        {"unique_identifier": "t1", "source_state": "start", "target_state": "rejected",
         "condition": {"field": "approval", "operator": "not_exists"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "approved"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(200, {"message": "done"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-not-exists", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "rejected"


@pytest.mark.asyncio
async def test_status_code_range_4xx():
    """Condition with 'status_code_range' matches 4xx responses."""
    transitions = [
        {"unique_identifier": "t_error", "source_state": "start", "target_state": "error",
         "condition": {"field": "status_code", "operator": "status_code_range", "value": "4xx"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "approved"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(422, {"error": "validation_failed"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-4xx", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "error"


@pytest.mark.asyncio
async def test_4xx_returns_result_not_retry():
    """A 4xx response is returned as a result, not raised as an error for retry."""
    transitions = [
        {"unique_identifier": "t_error", "source_state": "start", "target_state": "error",
         "condition": {"field": "status_code", "operator": "status_code_range", "value": "4xx"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "approved"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(400, {"error": "bad_request"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-4xx-result", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "error"
            audit = result["audit_trail"]
            error_entry = [e for e in audit if e["to_state"] == "error"]
            assert len(error_entry) == 1
            assert "bad_request" in error_entry[0]["task_result"]


@pytest.mark.asyncio
async def test_5xx_routes_with_condition():
    """A 5xx response can route to error state when a matching condition exists."""
    transitions = [
        {"unique_identifier": "t_error", "source_state": "start", "target_state": "error",
         "condition": {"field": "status_code", "operator": "status_code_range", "value": "5xx"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "approved"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(500, {"error": "server_error"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-5xx-route", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "error"


@pytest.mark.asyncio
async def test_no_matching_condition_stays_in_state():
    """When task fails and no condition matches, workflow stays in current state."""
    transitions = [
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "approved"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    call_count = 0

    @activity.defn(name="execute_task_callback")
    async def counting_mock(_input: TaskCallbackInput) -> TaskCallbackResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return TaskCallbackResult(success=False, status_code=500, body='{"error": "fail"}')
        return TaskCallbackResult(success=True, status_code=200, body='{"message": "ok"}')

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[counting_mock]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-no-match", task_queue="test-q")

            await handle.signal(SIGNAL_NAME, "t_manual")
            import asyncio
            await asyncio.sleep(1)

            state = await handle.query(QUERY_CURRENT_STATE)
            assert state["state_id"] == "start"

            await handle.signal(SIGNAL_NAME, "t_manual")
            import asyncio
            await asyncio.sleep(1)

            state = await handle.query(QUERY_CURRENT_STATE)
            assert state["state_id"] == "approved"


@pytest.mark.asyncio
async def test_equals_operator():
    """Condition with 'equals' matches exact field value."""
    transitions = [
        {"unique_identifier": "t_approve", "source_state": "start", "target_state": "approved",
         "condition": {"field": "status", "operator": "equals", "value": "approved"}},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "rejected"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(200, {"status": "approved"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-equals", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "approved"


@pytest.mark.asyncio
async def test_auto_on_success():
    """auto_on_success routes to target on 2xx without explicit condition."""
    transitions = [
        {"unique_identifier": "t_auto", "source_state": "start", "target_state": "approved",
         "auto_on_success": True},
        {"unique_identifier": "t_manual", "source_state": "start", "target_state": "rejected"},
    ]
    wf_dict = _build_workflow_def(STATES_WITH_TASK, transitions)
    mock_activity = _make_mock_activity(200, {"message": "ok"})

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[mock_activity]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-auto", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t_manual")
            result = await handle.result()
            assert result["final_state"] == "approved"


@pytest.mark.asyncio
async def test_no_task_proceeds_normally():
    """States without task callbacks proceed directly to target."""
    transitions = [
        {"unique_identifier": "t1", "source_state": "start", "target_state": "end"},
    ]
    wf_dict = _build_workflow_def(STATES_NO_TASK, transitions)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="test-q", workflows=[FSMWorkflow], activities=[]):
            handle = await env.client.start_workflow(FSMWorkflow.run, wf_dict, id="test-no-task", task_queue="test-q")
            await handle.signal(SIGNAL_NAME, "t1")
            result = await handle.result()
            assert result["final_state"] == "end"
