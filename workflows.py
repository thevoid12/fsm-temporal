"""Temporal workflow implementing a JSON-driven finite state machine.
Manages state transitions, task callback execution, conditional auto-transitions,
and exposes queries for current state, available transitions, and audit trail.
"""

import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from activities import execute_task_callback
    from models import (
        AuditEntry,
        AutoTransitionLogContext,
        AvailableTransitionResponse,
        CurrentStateResponse,
        FSMWorkflowResult,
        InvalidTransitionLogContext,
        StateEntryLogContext,
        TaskCallbackInput,
        TaskCallbackResult,
        WorkflowDefinition,
    )


@workflow.defn
class FSMWorkflow:
    """Generic FSM workflow driven by a WorkflowDefinition."""

    def __init__(self) -> None:
        self._current_state_id: str | None = None
        self._definition: WorkflowDefinition | None = None
        self._audit_trail: list[AuditEntry] = []
        self._transition_queue: list[str] = []
        self._completed: bool = False

    @workflow.run
    async def run(self, workflow_def_dict: dict) -> dict:
        """Run the FSM from start state to end state. Tasks execute on exit from a state."""
        self._definition = WorkflowDefinition.model_validate(workflow_def_dict)

        start_state = self._definition.get_start_state()
        self._enter_state(start_state.unique_identifier, transition_id=None)

        while not self._completed:
            await workflow.wait_condition(lambda: len(self._transition_queue) > 0)

            transition_id = self._transition_queue.pop(0)
            transition = self._definition.get_transition(transition_id)

            if transition.source_state != self._current_state_id:
                log_ctx = InvalidTransitionLogContext(
                    transition_id=transition_id,
                    current_state=self._current_state_id,
                    expected_source=transition.source_state,
                )
                workflow.logger.warning(
                    "Ignoring invalid transition",
                    extra=log_ctx.model_dump(),
                )
                continue

            try:
                task_result = await self._execute_exit_task()
            except ActivityError as e:
                workflow.logger.error(
                    "Exit task failed, staying in current state",
                    extra={"state_id": self._current_state_id, "transition_id": transition_id, "error": str(e)},
                )
                continue

            target_state = self._resolve_target_state(
                transition.target_state, transition_id, task_result
            )
            if target_state is None:
                continue
            self._enter_state(target_state, transition_id=transition_id, task_result=task_result)

        result = FSMWorkflowResult(
            final_state=self._current_state_id,
            audit_trail=self._audit_trail,
        )
        return result.model_dump()

    def _enter_state(
        self, state_id: str, transition_id: str | None, task_result: TaskCallbackResult | None = None
    ) -> None:
        """Set the current state and record an audit entry. No task execution happens here."""
        previous_state = self._current_state_id
        self._current_state_id = state_id
        state_def = self._definition.get_state(state_id)

        log_ctx = StateEntryLogContext(
            state_id=state_id,
            display_label=state_def.display_label,
        )
        workflow.logger.info("Entering state", extra=log_ctx.model_dump())

        audit_entry = AuditEntry(
            timestamp=workflow.now().isoformat(),
            from_state=previous_state,
            to_state=state_id,
            transition_id=transition_id,
            task_result=task_result.body if task_result else None,
        )
        self._audit_trail.append(audit_entry)

        if state_def.is_end:
            self._completed = True

    async def _execute_exit_task(self) -> TaskCallbackResult | None:
        """Run the current state's task callback before leaving it."""
        state_def = self._definition.get_state(self._current_state_id)
        if not state_def.task_callback_url:
            return None

        activity_input = TaskCallbackInput(
            callback_url=state_def.task_callback_url,
            http_method=state_def.task_http_method,
            state_id=self._current_state_id,
            workflow_id=workflow.info().workflow_id,
        )

        return await workflow.execute_activity(
            execute_task_callback,
            activity_input,
            schedule_to_close_timeout=timedelta(minutes=state_def.task_timeout_minutes),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=state_def.retry_interval_seconds),
                maximum_attempts=state_def.max_retries + 1,
                backoff_coefficient=2.0,
            ),
        )

    def _resolve_target_state(
        self, default_target: str, transition_id: str, task_result: TaskCallbackResult | None
    ) -> str | None:
        """Resolve target state based on task result. Returns None if workflow should stay in current state."""
        if not task_result:
            return default_target

        try:
            task_body = json.loads(task_result.body)
        except (json.JSONDecodeError, TypeError):
            task_body = {}

        task_body["status_code"] = task_result.status_code

        auto_transition = self._definition.find_auto_transition(
            self._current_state_id, task_result.success, task_body
        )
        if auto_transition:
            auto_log = AutoTransitionLogContext(
                transition_id=auto_transition.unique_identifier,
                target_state=auto_transition.target_state,
            )
            workflow.logger.info("Auto-transition override", extra=auto_log.model_dump())
            return auto_transition.target_state

        if not task_result.success:
            workflow.logger.warning(
                "No matching condition for non-success task result, staying in current state",
                extra={"state_id": self._current_state_id, "status_code": task_result.status_code},
            )
            return None

        return default_target

    @workflow.signal
    async def transition(self, transition_id: str) -> None:
        """Receive a transition signal and queue it for processing."""
        try:
            self._definition.get_transition(transition_id)
        except KeyError:
            workflow.logger.warning(
                "Unknown transition signal received",
                extra={"transition_id": transition_id},
            )
            return
        self._transition_queue.append(transition_id)

    @workflow.query
    def current_state(self) -> dict:
        """Return the current state identifier and display label."""
        if not self._definition or not self._current_state_id:
            response = CurrentStateResponse(state_id=None, display_label=None)
            return response.model_dump()
        state = self._definition.get_state(self._current_state_id)
        response = CurrentStateResponse(
            state_id=state.unique_identifier,
            display_label=state.display_label,
        )
        return response.model_dump()

    @workflow.query
    def available_transitions(self) -> list[dict]:
        """Return all valid transitions from the current state."""
        if not self._definition or not self._current_state_id:
            return []
        transitions = self._definition.get_transitions_from(self._current_state_id)
        return [
            AvailableTransitionResponse(
                transition_id=t.unique_identifier,
                display_label=t.display_label,
                target_state=t.target_state,
            ).model_dump()
            for t in transitions
        ]

    @workflow.query
    def audit_trail(self) -> list[dict]:
        """Return the full history of state transitions."""
        return [entry.model_dump() for entry in self._audit_trail]
